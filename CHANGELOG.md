# Changelog

Все заметные изменения проекта фиксируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
проект следует [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

Фаза B (MEMO v2.1 — архитектурные изменения). В работе.

### Changed (Phase B)

- **B.8 production_mode по годам (Q1, 2026-05-15).** Режим производства
  (копакинг / своё) теперь переключается **по годам**. Пример: Y1=копак,
  Y2=своё, Y3+=копак. Гранулярность годовая (10 значений). Хранение —
  JSONB `production_mode_by_year` на `ProjectSKU` (пустой объект = override
  выключен, используется скаляр).
  - Миграция `c3d4e5f6a7b8`: ADD COLUMN production_mode_by_year JSONB
    с default '{}'.
  - Engine: `PipelineInput.production_mode_by_period: tuple[str, ...]`
    (per-period). `calculation_service` строит tuple из годового JSONB
    с fallback на скаляр. `s03_cogs` проверяет per-period и применяет
    взаимоисключение own/copacking в каждом периоде.
  - UI: новый компонент `ProductionModeByYearEditor` в `bom-panel.tsx` —
    чекбокс "Переключать режим по годам" + Select-сетка Y1..Y10.
  - Тесты: 472/472 passed (including 4 acceptance GORJI — числовые
    результаты эталона не изменились, default = "own" для всех годов).
- **B.7 CA&M и Marketing → per-channel (Q6, 2026-05-15).** Поля
  `ca_m_rate` и `marketing_rate` перенесены с `ProjectSKU` на
  `ProjectSKUChannel` — в HM/SM/TT/E-COM маркетинг разный,
  унификация per-SKU искажала экономику каналов.
  - Миграция `b2c3d4e5f6a7`: ADD на PSC + COPY значений с PS + DROP с PS.
  - Engine: `calculation_service._build_line_input` берёт ставки
    с PSC; `pricing_service.build_value_chain` per-канал.
  - UI: убрано из `bom-panel.tsx`, добавлено в `channel-form.tsx`
    (дилог редактирования канала).
  - Excel-экспорт: CA&M/Marketing колонки переехали из листа SKU
    в лист "КАНАЛЫ × SKU".
  - GORJI acceptance 4/4 passed — числовые результаты идентичны
    (миграция копирует значения с PS на каждую дочернюю PSC).
- **B.10 VAT dropdown + дефолт 22% (Q7, 2026-05-15).** Новые проекты
  создаются с `vat_rate=0.22` (РФ с 01.01.2026). Существующие проекты
  не трогаем (миграция `a1b2c3d4e5f6` меняет только `server_default`).
  UI new-проекта: Select с пресетами 22% / 20% / 10% / 0% + custom.
  Tooltip уточнён: НДС применяется только для пересчёта shelf→ex_factory,
  на BOM не влияет (см. Q8).

---

## Phase A 

Фаза A (MEMO v2.1 — регрессии и блокеры). 6 пунктов, все закрыты.
Источник решений — `docs/CLIENT_FEEDBACK_v2_DECISIONS.md` (10 ответов
заказчика на блокирующие вопросы от 2026-05-12, зафиксированы
2026-05-15).

### Added

- **A.1 Diagnostic logging для финплана:** `financial_plan_service.replace_plan`
  пишет `logger.info` с payload (year, capex, opex, len(opex_items))
  на входе — без изменения behaviour. Поможет ловить интермиттирующие
  ошибки сохранения CAPEX/OPEX (MEMO 1.1, D-2/D-3).
- **A.6 Diagnostic logging для recalculate task:** `calculate_project_task`
  пишет `logger.info` на START/OK, `logger.warning` на bad-request
  (ProjectNotFound / NoLines / LineValidation), `logger.exception` на
  любое другое падение pipeline (MEMO 5.3, D-7).

### Changed

- **A.3 Roadmap status → dropdown:** в `content-tab.tsx` поле "Статус"
  задачи заменено с свободного `<Input>` на `<Select>` с фиксированными
  ключами `planned/in_progress/done/blocked`. Старые проекты с
  русскими значениями ("готово", "в работе") нормализуются legacy-map'ом.
  Закрывает баг "Gantt не перестраивается при смене статуса"
  (корневая причина — рассинхрон языка ввода и `STATUS_COLORS`) и
  попутно MEMO 1.2 "Статус проекта = dropdown".
- **A.6 Scenarios polling resilience:** `pollTaskStatus` в `scenarios-tab.tsx`
  ретраит при network glitch до 5 раз подряд, TIMEOUT увеличен 60s→180s,
  console.warn/error на каждом сбое для диагностики.
- **A.5 D-12 финально: 5 лет (60 мес).** Заказчик повторно подтвердил
  семантику Y1-Y5 (с начала проекта по конец 5-го года включительно).
  `SCOPE_BOUNDS["y1y5"] = (5, 5)` остаётся; docstring
  `s11_kpi.py`, `TZ_VS_EXCEL_DISCREPANCIES.md` D-12 и
  `ROADMAP.md` синхронизированы. Excel-тайпо ("6 столбцов")
  окончательно отклонён.

### Docs

- **`docs/CLIENT_FEEDBACK_v2_DECISIONS.md`** — финальные решения по
  10 вопросам MEMO v2.1 + план Фазы A/B/C (30 пунктов).
- **`docs/QUESTIONS_FOR_CLIENT_2026-05-12.md`** — исходный вопросник
  (архивный).
- **`docs/TO_DIAGNOSE_LATER.md`** — 8 технических диагностик для фазы
  тестирования (экспорт, finplan save, CAPEX=0, gantt, SKU images,
  лого, сценарии, SKU cascade). Закрыты A.2 + A.4 — заказчик
  подтвердил работоспособность.

---

## [2.4.0] — 2026-04-15

Post-audit remediation + engine quick wins. 4 фазы из
[`docs/archive/AUDIT_FIX_PLAN.md`](docs/archive/AUDIT_FIX_PLAN.md)
закрыты. Полный отчёт по аудиту — в
[`docs/ENGINE_AUDIT_REPORT.md`](docs/ENGINE_AUDIT_REPORT.md),
[`docs/PRESALES_AUDIT_2026-04-14.md`](docs/PRESALES_AUDIT_2026-04-14.md),
[`docs/SECURITY_AUDIT_2026-04-14.md`](docs/SECURITY_AUDIT_2026-04-14.md).

> **NB о промежуточных версиях:** между `v0.3.0` и `v2.4.0` в git
> tags были `v2.1.0`, `v2.2.0`, `v2.2.1`, `v2.3.0`, `v2.3.1`
> (клиентский milestone-релизы без подробных entries здесь). История
> коммитов полная в git log.

### Added (UI — demo polish)
- **U-04 Export spinner:** Loader2 + "Генерирую XLSX/PPTX/PDF…"
  в results-tab вместо текста "Экспорт…".
- **U-05 AI typing indicator:** анимированные точки в ai-panel-chat
  во время streaming до первого токена.
- **U-06 Channel Tooltip:** новый `components/ui/tooltip.tsx`
  (обёртка над @base-ui/react/tooltip); truncate названия канала
  раскрывается полным кодом + именем на hover.
- **U-07 Sortable headers a11y:** helper `sortableHeaderProps`
  в `use-sortable-table.ts` — focus-visible:ring, tabIndex=0,
  onKeyDown для Enter/Space. Применён в 5 таблицах.
- **U-08 financial-plan overflow:** горизонтальный скролл таблицы
  CAPEX/OPEX на узких экранах.
- **Sonner toasts:** `<Toaster />` в `app/layout.tsx`
  + `toast.success/error` в 14 save/delete хэндлерах
  (SKU, channel, BOM, finplan, scenarios, OBPPC, АКБ, ингредиенты,
  content, period-values batch, project create/patch, exports).
  Закрывает `U-01` + `BUG-01` (prod export silent fail теперь
  видимый через toast).
- **HelpButton для новых полей:** tax_loss_carryforward +
  3× scenario deltas (price/COGS/logistics) с формулами и
  defaults (parameter-help.ts + inline HelpButton в scenarios-tab
  и new/page.tsx).

### Added (backend — security)
- **S-04 Rate limiting:** slowapi `@limiter.limit` применён к:
  `POST /api/auth/login` (10/min per IP, защита от brute-force),
  `POST /api/projects/{id}/recalculate` (10/min, защита Celery
  worker'ов), `GET /api/projects/{id}/export/*` (20/min, защита
  от DoS на тяжёлой PPT/PDF генерации). Smoke tests в
  `tests/api/test_security_rate_limit.py`.

### Added (backend — staleness invalidation F-01/F-02)
- **`scenario_results.is_stale` BOOLEAN NOT NULL DEFAULT FALSE**
  (миграция `c30b0e3ac9bb`). Флаг "параметры проекта изменились,
  но пересчёт не выполнялся".
- **`services/invalidation_service.py`** —
  `mark_project_stale(session, project_id)` bulk UPDATE + 3
  convenience-хелпера (`mark_stale_by_psc/scenario/fp`).
- **Hooks** во всех PATCH/POST/DELETE endpoint'ах, меняющих
  pipeline input: projects, project_skus, project_sku_channels,
  period_values (включая batch и reset), bom, scenarios, financial_plan,
  actual_import.
- **`StalenessBadge` компонент** — жёлтый баннер "⚠️ Расчёт устарел"
  с CTA "Пересчитать" в results-tab, scenarios-tab, pnl-tab,
  value-chain-tab. При успешном recalculate новые строки создаются
  с `server_default='false'` — флаг автоматически сбрасывается.

### Added (backend — engine quick wins)
- **4.3 Input validation** — `LineValidationError` на
  `channel_margin ≥ 1.0` (иначе `ex_factory ≤ 0` → мусорные KPI).
  Warnings в логе на `universe=0` / `bom_unit_cost=0` /
  `shelf_price=0` (pipeline валиден, но вероятно незавершённая
  настройка). `pollTaskStatus` в frontend проверяет
  `result.error` на Celery SUCCESS — логические ошибки доходят
  до пользователя через recalcError + toast.
- **4.4 Fractional payback** — линейная интерполяция вместо
  integer count. `int → float`. GORJI payback_simple y1y10 теперь
  3.606 лет (было 3). Frontend `.toFixed(1)`. D-23 в
  `TZ_VS_EXCEL_DISCREPANCIES.md`.
- **4.1 Loss carryforward (ст.283 НК РФ)** — opt-in через
  `Project.tax_loss_carryforward` (миграция `d894b52f645b`,
  default `false` сохраняет Excel-compat). С cap 50% прибыли
  года. Pure-function `_compute_annual_tax` в `s10_discount.py`
  для unit-тестов. Checkbox в форме создания проекта. D-24.
- **4.5 Scenario deltas price/COGS/logistics** — 3 новых
  project-wide поля на Scenario (миграция `3e5dcbc50271`):
  `delta_shelf_price`, `delta_bom_cost`, `delta_logistics`.
  Мультипликативное применение во всех psc сценария в
  `_build_line_input`. UI editor в scenarios-tab — 3 новых
  input'а с HelpButton в каждой Conservative/Aggressive
  карточке. Позволяет моделировать risk scenarios
  "сырьё +15%" / "логистика +25%" / "ритейл требует −10% цены".

### Changed (dev tooling)
- **F-05 celery-worker auto-reload:** команда в
  `infra/docker-compose.dev.yml` заменена на
  `watchmedo auto-restart --debug-force-polling --interval=2 --
  celery -A app.worker worker`. Polling режим обязателен на
  Windows+Docker/WSL2 (inotify не пробрасывается через bind
  mount). `watchdog` добавлен в `backend/requirements.txt`.
  Prod команда не трогается.

### Changed (infra)
- **Server migration: 45.144.221.215 → 85.239.63.206.** Старый VPS попал
  в RKN-блокировки и имел плохой BGP-peering с европейскими сетями
  (только 5/20 локаций мира открывали сайт). Новый сервер: чистый IP,
  открывается с 13/15 локаций (только Иран блокирует).
- **Docker Hub mirror:** на новом сервере настроен `mirror.gcr.io` через
  `/etc/docker/daemon.json` — обходит anonymous rate limit.
- **SSL_SETUP.md** обновлён под новый сервер (без legacy frpanel конфликта).

### Changed (docs)
- **`docs/README.md`** — новый индекс активной документации
  (entry point).
- **Корневой `README.md`** — overview проекта + quick-start.
- **`docs/archive/`** — устаревшие документы перенесены:
  `TZ_COMPLIANCE_REPORT.md` (replaced by TZ_VS_EXCEL_DISCREPANCIES),
  `AUDIT_FIX_PLAN.md` (все фазы закрыты).

### Verification
- Backend: 469 tests + 4 acceptance passed (baseline drift
  сохранён, 3 новых тестовых файла: `test_security_rate_limit`,
  `test_staleness_invalidation`, `test_calculation_validation`).
- Frontend: `tsc --noEmit` clean.
- 3 Alembic миграции (`c30b0e3ac9bb`, `d894b52f645b`,
  `3e5dcbc50271`) применены на prod без downtime кроме
  `--force-recreate` (~1 минута). Существующие 18
  `scenario_results` получили `is_stale=false` через
  server_default — визуальной регрессии нет.

---

## [0.3.0] — 2026-04-11

Phase 8: presentation layer parity. Полное соответствие presentation
паспорта с эталоном Elektra Zero — все 10 задач закрыты с UI и экспортом
в PPT/PDF. 3 миграции БД, 5 новых endpoint'ов, 4 новых таба в проекте.

### Added (UI)
- **8.1 Pricing Summary tab:** сводная таблица цен SKU × канал (полка,
  ex-factory с VAT-коррекцией, COGS из BOM, маржи каналов). Backend
  endpoint GET /api/projects/{id}/pricing-summary + frontend PricingTab.
- **8.2 Value Chain / Стакан tab:** per-unit waterfall экономика по
  SKU × канал (Shelf → Ex-Factory → COGS → GP → Logistics → CM →
  CA&M → Marketing → EBITDA). Backend endpoint GET
  /api/projects/{id}/value-chain + frontend ValueChainTab с цветовой
  индикацией маржей (green ≥50%, yellow 45-50%, red <45%).
- **8.3 Per-unit метрики в KPI-сводке:** scope-averaged Revenue/GP/CM/EBITDA
  на штуку, литр, кг. 12 новых Numeric колонок в scenario_results,
  вычисление в calculation_service, таблица 4×3×3 в ResultsTab.
- **8.5 P&L tab с toggle месяцы/кварталы/годы:** Backend endpoint
  GET /api/projects/{id}/pnl (43 per-period P&L метрики из pipeline).
  Frontend PnlTab с client-side агрегацией в кварталы (Q1-Q4 × Y1-Y3)
  и годы (Y1-Y10). Toggle "Месяцы / Кварталы / Годы".
- **8.6 Цветовая индикация KPI:** 3-tier margin colors в ResultsTab
  (green ≥25% / yellow 15-25% / red <15%), NPV color в ScenariosTab
  (green/red), легенды в обоих табах.
- **8.7 Gate Timeline:** горизонтальная шкала G0→G5 с текущей позицией
  и milestone labels (Идея→Масштабирование). Встроена в overview tab.
- **8.8 Расширенный бюджет маркетинга:** category колонка в opex_items +
  migration, 14 категорий (Digital, E-com, OOH, PR, SMM, Design, Research,
  ПОСМ, Creative, Special, Merch, TV, Листинги, Другое), Select dropdown
  в FinancialPlanEditor. UNIQUE(plan, category, name). Backward compat:
  старые записи получают `category="other"`.
- **8.9 Nielsen бенчмарки:** JSONB поле `nielsen_benchmarks` на Project,
  редактируемая таблица в ContentTab (channel × universe × offtake × ND
  × price × category share + note).
- **8.10 КП на производство:** JSONB поле `supplier_quotes` на Project,
  редактируемая таблица в ContentTab (supplier × item × price × MOQ × lead time).

### Added (Exports)
- **8.4 Sensitivity в PPT/PDF:** 2D матрица чувствительности (4 param ×
  5 delta → NPV Y1-Y10) — новый слайд PPT + секция HTML-template.
- **8.1+8.2 Pricing + Value Chain в PPT/PDF:** два новых слайда и две
  PDF секции с pricing waterfall и value chain.
- **8.3 Per-unit в PPT/PDF:** расширение KPI слайда таблицей per-unit
  метрик Base сценария (4 metrics × 3 scopes) + аналог в PDF.
- **8.7 Gate Timeline в PPT/PDF cover:** текстовая шкала G0→G5 с
  маркером ●Gx на title slide и cover PDF.
- **8.8 OPEX категории в PPT/PDF:** секция "OPEX по категориям маркетинга"
  в стакан-fin-plan слайде и аналогично в PDF секции 9.
- **8.9+8.10 Рынок и поставки в PPT/PDF:** объединённый слайд "Рынок
  и поставки" с Nielsen (слева) + supplier_quotes (справа). Слайд
  отображается только если есть данные. PDF — двухколоночная секция.

### Changed
- **Pricing service refactoring:** логика расчёта pricing_summary и
  value_chain вынесена из `api/projects.py` в `services/pricing_service.py`
  для переиспользования API endpoint'ами и exporters.

### Migrations
- `bf144a47ef42` — add ai_sensitivity_commentary column to projects
- `df5babcd77d8` — add 12 per-unit metrics columns to scenario_results
- `338f0a242518` — add category column to opex_items + UNIQUE(plan,category,name)
- `84d5e23d52e8` — add nielsen_benchmarks JSONB column to projects
- `7b303e6b7b59` — add supplier_quotes JSONB column to projects

### Fixed
- **PnL endpoint 500:** `from app.models.enums import ScenarioType` →
  `from app.models import ScenarioType` (модуль `app.models.enums` не
  существует, ScenarioType экспортируется напрямую из `app.models`).
  Lazy import внутри функции не ловился pytest'ом до первого вызова.

### Tests
- 444 passed (no new tests added for new endpoints — TODO для следующей фазы)
- test_export_pptx обновлён: ожидаемое количество слайдов 13 → 16

---

## Older releases

Перенесены в [`docs/releases/`](docs/releases/) при чистке документации (2026-05-12):

- [`v0.2.0`](docs/releases/v0.2.0.md) — Prod fixes, chat persistence, delete project (2026-04-10)
- [`v0.1.0`](docs/releases/v0.1.0.md) — MVP release (2026-04-10)
