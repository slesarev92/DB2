# План исправлений по результатам аудита

**Дата создания:** 2026-04-15
**Источники:** `ENGINE_AUDIT_REPORT.md`, `SECURITY_AUDIT_2026-04-14.md`, `PRESALES_AUDIT_2026-04-14.md`.
**Контекст:** часть findings уже закрыта (S-01 IDOR, S-02 prod creds, U-03 empty SKU layout,
Phase 5 HelpButton, L-01..L-06 русификация labels). Этот документ — трекер того, что осталось.

---

## Верификация оставшихся пунктов (проведена 2026-04-15 через code audit)

| ID | Scope | Статус | Effort | Evidence |
|----|-------|--------|--------|----------|
| F-01 | `ScenarioResult.is_stale` колонка | OPEN | ~1ч | `models/entities.py:756` — колонки нет |
| F-02 | Staleness badge в results/scenarios/pnl/value-chain tabs | OPEN | ~2ч | нет Alert в `*-tab.tsx` |
| F-05 | `watchmedo auto-restart` для celery-worker dev | OPEN | 15м | `infra/docker-compose.dev.yml:126` — нет |
| S-04 | Rate limit на `/auth/login`, `/recalculate`, `/export/*` | OPEN | 1ч | только `api/ai.py` имеет `@limiter.limit` |
| U-01 | Sonner Toaster + `toast.success/error` во всех save-хэндлерах | PARTIAL | 1-1.5ч | добавлен только для export (f17b2fa) |
| U-04 | `Loader2` spinner + "Генерирую XLSX…" в export button | PARTIAL | 15м | сейчас просто текст "Экспорт…" |
| U-05 | Typing indicator / skeleton в AI panel chat | OPEN | 15м | пустой экран во время pending |
| U-06 | `Tooltip` на truncate channel name | OPEN | 10м | `channels-panel.tsx:171` |
| U-07 | `focus-visible:ring-2` на sortable headers | OPEN | 30м | |
| U-08 | `overflow-x-auto` на `financial-plan-editor` | OPEN | 15м | |
| BUG-01 | Prod export silent fail | PARTIAL | 30м | diagnostics есть (f17b2fa), но ошибка не видна — зависит от U-01 |
| 4.1 | Loss carryforward в `s08_tax.py` (ст.283 НК РФ) | OPEN | 2ч | сейчас `tax = max(0, contribution*rate)` без accumulated loss |
| 4.3 | Validation вводных (shelf_price>0, universe>0, margin<1.0, bom>0) в `calculation_service._build_line_input` | OPEN | 2ч | |
| 4.4 | Дробный Payback (линейная интерполяция) | OPEN | 1ч | `s11_kpi.py` возвращает целые годы |
| 4.5 | `ScenarioChannelDelta` расширить на `delta_shelf_price`, `delta_bom_cost`, `delta_logistics` | OPEN | 4-6ч | сейчас только `delta_nd/delta_offtake/delta_opex` |

**Закрыто (не делаем):** S-01, S-02, S-03, L-01..L-06, U-03, F-03 (через context hash), Phase 5 HelpButton.

---

## Фазы — линейный порядок выполнения

### Фаза A — Демо-ready quick wins (~3ч, 1-2 коммита)

Низкий риск, визуальные мелочи + dev QoL.

1. **U-04** — Export button: `<Loader2 className="animate-spin" />` + динамический текст "Генерирую {format.toUpperCase()}…". Файл: `frontend/components/projects/results-tab.tsx:345+`.
2. **U-06** — Channel name truncate → shadcn `Tooltip`. Файл: `frontend/components/projects/channels-panel.tsx:171`.
3. **U-07** — `focus-visible:ring-2 ring-ring ring-offset-2` на sortable headers. Файлы: `channels-panel.tsx:148-162`, где ещё клики по TH.
4. **U-08** — `overflow-x-auto` на wrapper `financial-plan-editor.tsx:169+`.
5. **U-05** — Typing bubble в `ai-panel-chat.tsx` во время pending (три точки с CSS-анимацией).
6. **F-05** — `watchmedo auto-restart --directory=/app --pattern=*.py --recursive -- celery -A app.worker worker --loglevel=info` в `docker-compose.dev.yml`, добавить `watchdog` в `requirements-dev.txt`.

**Commit:** `feat(ui): demo polish — export progress, tooltips, focus rings, AI typing + dev: celery auto-reload`.

### Фаза B — Toast system + BUG-01 закрытие (~1.5ч)

7. **U-01** — Sonner `<Toaster position="top-right" richColors />` в `frontend/app/layout.tsx`.
8. **U-01b** — `toast.success("Сохранено")` + `toast.error(err.message)` во всех save-хэндлерах:
   - `sku-panel.tsx`, `channel-form.tsx`, `bom-panel.tsx`, `project-form.tsx`, `scenarios-tab.tsx`, `financial-plan-editor.tsx`, `obppc-tab.tsx`, `akb-tab.tsx`, `content-tab.tsx`, `media-tab.tsx`, `value-history-dialog.tsx`.
   - Убрать устаревшие error Card где toast их заменяет.
9. **BUG-01** — после U-01 export ошибка видна через toast (уже есть в `export.ts` от f17b2fa). Проверить на prod через Chrome DevTools.

**Commit:** `feat(ui): sonner toasts for save/export flows (closes U-01, makes BUG-01 visible)`.

### Фаза C — Staleness invalidation (~5ч, enterprise must-have)

10. Alembic миграция: `scenario_results.is_stale BOOLEAN NOT NULL DEFAULT FALSE`, seed существующих строк через `server_default='false'`.
11. `backend/app/services/invalidation_service.py` — `async def mark_project_stale(session, project_id)`:
    ```python
    await session.execute(
        update(ScenarioResult)
        .where(ScenarioResult.scenario_id.in_(
            select(Scenario.id).where(Scenario.project_id == project_id)
        ))
        .values(is_stale=True)
    )
    ```
12. Вызов `mark_project_stale` во всех PATCH/POST/DELETE, меняющих pipeline input:
    - `api/projects.py` PATCH (wacc/wc_rate/tax_rate/vat_rate/cm_threshold)
    - `api/project_skus.py` PATCH/POST/DELETE
    - `api/project_sku_channels.py` PATCH/POST/DELETE
    - `api/period_values.py` PATCH/POST/DELETE
    - `api/bom.py` PATCH/POST/DELETE
    - `api/scenarios.py` PATCH/POST/DELETE + ScenarioChannelDelta
    - `api/financial_plan.py` PATCH/POST/DELETE
13. В `calculation_service.recalculate_project` — `is_stale=False` после успешного пересчёта.
14. Frontend: компонент `<StalenessBadge result={scenarioResult} onRecalculate={...} />`, показать в `results-tab.tsx`, `scenarios-tab.tsx`, `pnl-tab.tsx`, `value-chain-tab.tsx`.
15. Тесты: 3-5 integration (PATCH project → is_stale=True; recalculate → is_stale=False; PATCH psk_channel → is_stale=True; и т.д.).

**Commits:**
- `feat(backend): staleness flag — ScenarioResult.is_stale + invalidation_service + PATCH hooks`
- `feat(ui): staleness badge in results/scenarios/pnl tabs with recalculate CTA`

### Фаза D — Engine quick wins (~9-11ч, 4 коммита)

16. **4.3 Input validation** — первое, потому что предохранит от мусорных данных при остальных изменениях.
    - Dataclass `PipelineInputValidation` или inline checks в `_build_line_input`.
    - Поднимать `DomainValidationError` с полем и причиной.
    - API возвращает 422 с `{field, reason}`.
17. **4.1 Loss carryforward** — ст.283 НК РФ, cap 50% прибыли.
    - В `s08_tax.py` ввести `cumulative_loss` аккумулятор.
    - Acceptance перепрогон (ожидаем drift на launch-проектах).
    - Задокументировать в `TZ_VS_EXCEL_DISCREPANCIES.md` как D-23 (Excel этого не делает — наша модель корректнее).
18. **4.4 Fractional payback** — линейная интерполяция между последним отрицательным и первым положительным кумулятивным FCF. Коснётся `s11_kpi.py` и schema `Payback: float`.
19. **4.5 Scenario deltas price/COGS/logistics** — самое тяжёлое:
    - Миграция `ALTER TABLE scenario_channel_deltas ADD COLUMN delta_shelf_price NUMERIC DEFAULT 0, ADD COLUMN delta_bom_cost NUMERIC DEFAULT 0, ADD COLUMN delta_logistics NUMERIC DEFAULT 0;`
    - `_build_line_input` применяет дельты к `shelf_price_reg`, `bom_unit_cost`, `logistics_cost_per_kg` аналогично `delta_nd/delta_offtake`.
    - UI: `channel-deltas-editor.tsx` — добавить 3 поля + HelpButton для каждого.
    - Тесты: scenario с `delta_bom_cost=+0.15` → Contribution ниже на ожидаемую величину.

**Commits:** каждый пункт — свой.

---

## S-04 Rate limiting (можно приклеить к Фазе B)

- `@limiter.limit("5/minute", key_func=get_remote_address)` на `/api/auth/login` (per IP).
- `@limiter.limit("5/minute", key_func=lambda r: str(r.state.user.id))` на `/api/projects/{id}/recalculate`.
- `@limiter.limit("10/minute", key_func=<user_id>)` на `/api/projects/{id}/export/*`.
- 3 regression теста (429 после лимита).

**Commit:** `fix(security): S-04 rate limit on auth/recalc/export`.

---

## Оценка общего effort

| Фаза | Effort | Риск | Когда |
|------|--------|------|-------|
| A | ~3ч | 🟢 низкий | сейчас |
| B + S-04 | ~2.5ч | 🟢 низкий | после A |
| C | ~5ч | 🟡 миграция БД + много touch-points | после B |
| D | ~9-11ч | 🟡 формулы + миграция + acceptance | после C |

**Всего:** ~20-22ч до полностью enterprise-ready состояния.

---

## Правила при выполнении

- Линейно: не параллелить задачи из разных фаз, даже если зависимости позволяют.
- Каждый коммит — зелёные тесты (pytest + tsc --noEmit).
- После Фазы C (invalidation) — перепрогон acceptance `pytest -m acceptance` обязателен.
- После Фазы D (engine) — перепрогон acceptance + сверка с Excel эталоном, обновить `TZ_VS_EXCEL_DISCREPANCIES.md` если дрейф.
- Деплой на prod — только по явной команде пользователя.
