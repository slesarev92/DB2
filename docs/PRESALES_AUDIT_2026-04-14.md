# Аудит готовности к продажам — Цифровой паспорт проекта

**Дата:** 2026-04-14
**Версия:** git tip после коммита `98971dc` (v0.3.0 + Client Feedback v1 — 38/40 закрыто)
**Цель:** оценить готовность продукта для enterprise-продаж FMCG-клиентам.
**Формат:** 5 фаз аудита, каждая завершается findings + блокеры.
**Связанные документы:**
- [`docs/ENGINE_AUDIT_REPORT.md`](ENGINE_AUDIT_REPORT.md) — математика ядра
- [`docs/SECURITY_AUDIT_2026-04-14.md`](SECURITY_AUDIT_2026-04-14.md) — security
- [`docs/TZ_VS_EXCEL_DISCREPANCIES.md`](TZ_VS_EXCEL_DISCREPANCIES.md) — D-01..D-22 формулы
- [`docs/CLIENT_FEEDBACK_v1.md`](CLIENT_FEEDBACK_v1.md) — 40 замечаний заказчика
- [`docs/ERRORS_AND_ISSUES.md`](ERRORS_AND_ISSUES.md) — журнал проблем

---

## Executive summary

_(раздел наполняется по мере закрытия фаз)_

| Фаза | Scope | Статус | Блокеры |
|---|---|---|---|
| 1 | Математика + security | ✅ закрыта | 🔴 IDOR, 🔴 admin/admin123 |
| 2 | Invalidation после PATCH | ✅ закрыта | 🟡 нет staleness UI (F-01/F-02), AI cache OK через context hash |
| 3 | Dropdowns/labels | ✅ закрыта | 🟡 L-01..L-06 неконсистентная русификация (fix ~1.5ч) |
| 4 | Usability + export quality | ⏳ | — |
| 5 | HelpButton (реализация) | ⏳ | — |

---

## Фаза 1 — Математика + security

**Результат:** ✅ pipeline корректен. См. ENGINE_AUDIT_REPORT § "Update 2026-04-14"
и SECURITY_AUDIT_2026-04-14.md.

**Блокеры продаж (из Фазы 1):**
1. 🔴 **S-01 IDOR** — `project_service.get_project()` не фильтрует по
   `created_by`; любой юзер читает/меняет/удаляет чужие проекты. Fix 3-5ч.
2. 🔴 **S-02 admin/admin123 на prod** — `scripts/seed_demo_project.py`
   бьёт по проду с тривиальным паролем. Fix 30 мин.

**Известные ограничения (не блокеры):**
- Нет ценовой эластичности / каннибализации / промо-лифта (Phase 3-4 roadmap).
- Нет loss carryforward в налогах (quick win, 2 часа).
- Rate limiting только на AI endpoints.

---

## Фаза 2 — Invalidation после PATCH

**Scope:** проверить что изменение editable полей (ProjectSKU rates, PSC
channel params, PeriodValue fine-tuning, Project параметры, BOMItem,
Scenario deltas) помечает ScenarioResult как устаревший и уведомляет
пользователя.

### Архитектура (как есть сейчас)

```
PATCH /api/project-skus/{id}           ◁── user меняет rate
    └─ project_sku_service.update()
         └─ UPDATE project_skus SET ..., updated_at=NOW()  ← триггер onupdate
         └─ session.commit()
         └─ return updated row                  ◁── НЕТ invalidation

scenario_results — без изменений:
    npv, irr, roi, calculated_at = вчерашний timestamp
    go_no_go = True (возможно теперь False)
    is_stale: колонки нет

AI cache в Redis:
    ai_cache:{project_id}:{feature}:{input_hash} — живёт 24ч
    (никто не удаляет при PATCH)
```

### Findings

**🟡 F-01 (MEDIUM) — ScenarioResult не имеет флага staleness**

`backend/app/models/entities.py:756` (class ScenarioResult) содержит:
- `calculated_at: datetime` — timestamp последнего расчёта
- НЕТ `is_stale: bool` или `invalidated_at: datetime | None`

Ни один из 12 PATCH-файлов в `backend/app/api/` не делает:
- `DELETE FROM scenario_results WHERE scenario_id IN (SELECT FROM scenarios WHERE project_id = ?)`
- `UPDATE scenario_results SET is_stale = true WHERE ...`
- Redis AI cache `DEL ai_cache:{project_id}:*`

**Означает:** пользователь меняет любое поле → результаты в БД остаются
старыми, UI показывает их как актуальные. Пользователь должен **вручную**
нажать "Пересчитать".

**🟡 F-02 (MEDIUM) — нет UI-индикатора "результаты устарели"**

Frontend:
- `frontend/types/api.ts:506` — `calculated_at: string` передаётся, но
  не используется.
- Нет React Query / SWR → нет автоматического staleTime.
- Нет логики сравнения `calculated_at` vs `updated_at` (ни на бэке,
  ни на фронте).
- В результатных табах (Results, Scenarios, P&L, ValueChain) нет badge
  "⚠️ Расчёт устарел на N минут".

**Пример риска:** аналитик поменял VAT rate на 10%, посмотрел на старый
KPI-экран, скопировал NPV в презентацию клиенту, **забыл пересчитать**.
В проде: NPV в презентации — неверный.

**🟢 F-03 (LOW) — AI cache: TTL-only, но `input_hash` включает ScenarioResult**

`ai_cache.py:112-125` — `hash_context(context: dict)` вычисляет SHA-256
от **всего** context dict (sorted JSON). `AIContextBuilder` кладёт туда
актуальные NPV/IRR/ROI/margins из ScenarioResult. Значит:
- После recalculate → новые scenario_results → новый context → новый хэш →
  cache miss → свежий AI-комментарий. ✅
- PATCH без recalc → старые scenario_results → старый хэш → cache hit →
  старый комментарий. Но это абсурдный flow (KPI-комментарий по устаревшим
  данным бессмыслен для UX), и после обязательного recalc инвалидация
  происходит автоматически через diff хэша.

Комментарий в ai_cache.py (Phase 7.5 TODO) неточный — explicit
invalidation **не требуется** для корректности при типичном flow
(PATCH → recalc → AI). Но безвредна как belt-and-suspenders.

**🟢 F-04 (OK) — `updated_at` обновляется автоматически**

`TimestampMixin` использует `server_default=func.now(), onupdate=func.now()`
— при любом UPDATE БД автоматически обновляет `updated_at`. Инфраструктура
для staleness проверки есть (только не используется).

**🟡 F-05 (MEDIUM) — Celery-worker без auto-reload**

CLAUDE.md явно указывает:
> Restart celery-worker — ОБЯЗАТЕЛЬНО после изменений в calculation_service,
> engine/, sensitivity_service. Celery НЕ имеет auto-reload.
> Признак проблемы: API работает, recalculate возвращает 200, но в БД
> старые значения / новые поля = NULL.

В `infra/docker-compose.dev.yml` нет `watchmedo auto-restart` для celery-worker.
Это чисто dev-issue (prod деплой всегда пересобирает образ), но в dev
приводит к "работает на моём браузере, а в БД чушь" моментам.

### Рекомендации для Фазы 2

**Минимальный fix (3-4 часа):**

1. **Backend** (`calculation_service.py`, все PATCH endpoints):
   - При PATCH любого entity, которое влияет на pipeline — вызывать
     `await invalidation_service.mark_project_stale(session, project_id)`:
     ```python
     await session.execute(
         update(ScenarioResult)
         .where(ScenarioResult.scenario_id.in_(
             select(Scenario.id).where(Scenario.project_id == project_id)
         ))
         .values(is_stale=True)
     )
     await ai_cache.invalidate_project(redis, project_id)
     ```
   - Добавить колонку `is_stale: bool` на ScenarioResult (миграция
     с `server_default='false'`).
   - После успешного recalculate — сбросить `is_stale=False`.

2. **Frontend:**
   - В results-tab / scenarios-tab / pnl-tab читать `scenario_result.is_stale`,
     показывать badge:
     ```tsx
     {result.is_stale && (
       <Alert variant="warning">
         <AlertTitle>Расчёт устарел</AlertTitle>
         <AlertDescription>
           Данные проекта были изменены после последнего пересчёта.
           <Button onClick={recalculate}>Пересчитать сейчас</Button>
         </AlertDescription>
       </Alert>
     )}
     ```

3. **AI cache invalidation** (`ai_cache.py`):
   - Функция `invalidate_project(redis, project_id)`:
     ```python
     pattern = f"ai_cache:{project_id}:*"
     async for key in redis.scan_iter(pattern):
         await redis.delete(key)
     ```
   - Вызывается из PATCH endpoints и /recalculate.

4. **Celery-worker dev auto-reload** (optional, quality-of-life):
   - В `docker-compose.dev.yml` заменить команду на:
     `watchmedo auto-restart --directory=/app --pattern=*.py --recursive
     -- celery -A app.worker worker --loglevel=info`
   - Добавить `watchdog` в `requirements-dev.txt`.

**Estimated total effort:** 4-5 часов + 5-6 integration-тестов.

### Блокеры продаж из Фазы 2

- 🟡 **F-01/F-02 (UX)** — средний приоритет. Для enterprise-продаж
  клиент **будет** спрашивать "а если я поменял данные, мне покажут что
  нужно пересчитать?". Если нет — выглядит как "сырой продукт".
  **Не блокер**, но сильно понижает impression на демо.

- 🟡 **F-03 (AI staleness)** — низкий-средний приоритет. AI-комментарии
  маркетинговая фича, не data integrity. Но клиент может скриншотить
  противоречие "KPI NPV = 50М, AI-комментарий: 'проект выглядит слабо
  с NPV 20М'" — плохой look.

---

## Фаза 3 — Dropdowns / labels

**Scope:** все Select / option компоненты в `frontend/components/projects/`,
все enum values из backend (ScenarioType, PeriodScope, PeriodType, SourceType,
PriceTier, PackFormat, GateStage, FunctionReadinessStatus, UserRole,
OpexCategory), консистентность русских переводов.

### Coverage matrix

| Enum | Backend values | Frontend LABELS map | Покрытие | Комментарий |
|---|---|---|---|---|
| ScenarioType | base / conservative / aggressive | ❌ **расхождение** | 33% | Три разных map в разных tabs |
| PeriodScope | y1y3 / y1y5 / y1y10 | SCOPE_LABELS ✅ | 100% | "Y1-Y3 / Y1-Y5 / Y1-Y10" (аббр ок) |
| PeriodType | monthly / annual | ❌ нет map | 0% | Raw values в SelectItem |
| GateStage | G0-G5 | GATE_LABELS ✅ | 100% | "Идея/Концепция/.../Масштабирование" |
| FunctionReadinessStatus | green / yellow / red | FUNCTION_STATUS_LABELS ✅ | 100% | Ок |
| PriceTier | premium / mainstream / value | ❌ нет map | 0% | `obppc-tab.tsx:236-238` hardcoded английский |
| PackFormat | "bottle" (только это используется) | ❌ нет map и нет enum | 0% | `obppc-tab.tsx:92` raw "bottle" |
| OpexCategory | 14 значений | OPEX_CATEGORY_LABELS ⚠️ | 50% | **Смешаны:** "Digital"/"PR"/"SMM" + "ПОСМ"/"Листинги" |
| SourceType | predict / finetuned / actual | SOURCE_LABELS ❌ | 0% | `value-history-dialog.tsx:34-37` на английском |
| ViewMode (P&L) | monthly / quarterly / annual | MODE_LABELS ✅ | 100% | Ок |

### Findings

**🟡 L-01 (MEDIUM) — SCENARIO_LABELS расходятся в 3 файлах**

Один и тот же enum `ScenarioType` переводится по-разному:
- `scenarios-tab.tsx:45-49` → "Base" / "Conservative" / "Aggressive" 🔴
- `periods-tab.tsx:38-42` → "Base" / "Conservative" / "Aggressive" 🔴
- `results-tab.tsx:50-54` → "Базовый" / "Консервативный" / "Агрессивный" ✅

На экране **Сценарии** (scenarios-tab) показано "Base", на экране
**Результаты** (results-tab) то же самое называется "Базовый". Для
enterprise-клиента это выглядит как "разные разработчики писали, никто
не проверил согласованность" — первый красный флажок на демо.

**Fix:** вынести единый `SCENARIO_LABELS` в `frontend/types/api.ts`
с русскими значениями, импортировать во все 3 файла (plus
`channel-deltas-editor.tsx:231`). **15 минут.**

**🟡 L-02 (MEDIUM) — PriceTier / PackFormat / SourceType без LABELS**

- `obppc-tab.tsx:236-238` — `<SelectItem value="premium">Premium</SelectItem>`
  — английский захардкожен.
- `obppc-tab.tsx:92` — `pack_format === "bottle"` без перевода → в UI
  отображается сырое `"bottle"`.
- `value-history-dialog.tsx:34-37` — `SOURCE_LABELS = {predict: "Predict",
  finetuned: "Fine-tuned", actual: "Actual"}` — **весь history-диалог
  на английском.**

**Fix:** создать PRICE_TIER_LABELS, PACK_FORMAT_LABELS, SOURCE_LABELS
в `types/api.ts`, заменить raw values на `LABELS[value] ?? value`. **30 мин.**

**🟡 L-03 (MEDIUM) — OpexCategory смешанный язык**

`types/api.ts:607-622`:
```typescript
OPEX_CATEGORY_LABELS = {
  digital: "Digital",        // ← англ
  pr: "PR",                  // ← англ (аббр)
  smm: "SMM",                // ← англ (аббр)
  design: "Design",          // ← англ
  posm: "ПОСМ",              // ← рус
  listings: "Листинги",      // ← рус
  other: "Другое",           // ← рус
  ...
}
```

В одном выпадающем списке маркетинговых категорий пользователь видит
"Digital / PR / SMM / Design / ПОСМ / Листинги / Другое" — half-and-half.
**Fix:** единообразно все по-русски: "Диджитал / PR / СММ / Дизайн /
ПОСМ / Листинги / Другое". Аббревиатуры PR/SMM можно оставить латиницей
(индустриальный стандарт), но тогда последовательно везде. **15 мин.**

**🟢 L-04 (LOW) — fallback к raw enum**

`scenarios-tab.tsx:231`, `periods-tab.tsx:224`, `channel-deltas-editor.tsx:231`:
```tsx
{SCENARIO_LABELS[s.type] ?? s.type}   // fallback показывает "base"/"aggressive"
```

Если backend вернёт новый тип сценария (например `"custom"`), UI покажет
сырой enum. Это на будущее — сейчас enum стабилен. **Fix:** fallback
на `"—"`. 5 минут.

**🟡 L-05 (MEDIUM) — tornado chart без русификации**

`tornado-chart.tsx:30-34`:
```typescript
PARAM_LABELS = { nd: "ND", offtake: "Off-take", shelf_price: "Shelf price", cogs: "COGS" }
```

Tornado chart — визуальный ключевой артефакт на демо (sensitivity analysis).
"Off-take" и "Shelf price" — английский. "ND" и "COGS" — аббревиатуры
можно оставить с подсказкой в HelpButton (Phase 5), но "Off-take" должно
стать "Отгрузка" (или оставить "Off-take" как индустриальный термин
с подсказкой).

**🟡 L-06 (MEDIUM) — AI panel history endpoint labels**

`ai-panel-history.tsx:14-26`:
```typescript
ENDPOINT_LABELS = {
  explain_kpi: "Explain KPI",
  sensitivity: "Sensitivity",
  executive_summary: "Executive Summary",
  ...
}
```

Весь history-просмотр AI-запросов на английском. **Fix:** "Объяснение KPI /
Анализ чувствительности / Executive summary / ...". 10 минут.

### Untranslated placeholders / UI strings (не критично)

✅ Good:
- Все form placeholders: "Выберите SKU", "Выберите канал", "Нет данных".
- Заголовки карточек, labels, кнопки — русские.
- Validation messages базовые ("Обязательное поле").

🟡 Minor:
- `content-tab.tsx:361` — `<SelectValue placeholder="—" />` для G0-G5
  (placeholder norm, но можно "Выберите стадию").
- Validation "Score 0-100" hardcoded где-то в формах.

### Рекомендации по Фазе 3

**Total effort:** ~1.5 часа для полного fix всех 6 labels issues.

Приоритет:
1. **L-01** SCENARIO_LABELS — видно на каждом табе. Fix first.
2. **L-02** PriceTier/PackFormat/SourceType — видно при opening value history.
3. **L-03** OpexCategory смешанный — видно в финплане.
4. **L-05** Tornado chart — важно для demo по sensitivity.
5. **L-06** AI history — менее заметно, но нужно для полноты.
6. **L-04** fallback — defensive, можно отложить.

### Блокеры продаж из Фазы 3

**Нет 🔴 блокеров.** Но 🟡 **L-01/L-02/L-03/L-05** суммарно создают
впечатление "русификация не доведена" — для enterprise-клиента это
аргумент снизить цену / попросить "доделать перед оплатой". **Fix
перед первой продажей.**

## Фаза 4 — Usability + export quality

_(ещё не проходили)_

## Фаза 5 — HelpButton (реализация)

_(ещё не проходили)_

---

## Итоги по готовности к продажам (обновляется)

### 🔴 Блокеры (не продавать enterprise до fix)
1. S-01 IDOR — 3-5 часов.
2. S-02 admin/admin123 на prod — 30 минут.

### 🟡 Средние (заметны на демо, но не блокируют)
1. F-01/F-02 — invalidation + staleness UI.
2. F-03 — AI cache invalidation.
3. S-03 — CORS verify на prod.
4. S-04 — rate limit на критичных endpoints.

### 🟢 Готово к продажам (прошло аудит)
1. Математика pipeline — D-01..D-22 верифицированы.
2. XSS в PDF защищён.
3. SQL-injection защита (ORM).
4. Raw SQL — только в тестах.
