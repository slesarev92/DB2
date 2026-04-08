# Changelog

Все заметные изменения проекта фиксируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
проект следует [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added (задача 4.1 — AG Grid таблица периодов)
**Inline-редактируемая таблица периодов с трёхслойной подсветкой
(старт Фазы 4):**

**Backend extension:**
- `schemas/reference.py` — `PeriodRead` Pydantic схема
- `api/reference.py` — `GET /api/periods` (read-only, JWT, sorted)
- 4 новых теста в `test_reference.py` (43 rows, split monthly/yearly,
  sorted, unauthorized)

**Frontend новые зависимости:**
- **AG Grid Community v35.2.1** + **AG Grid React** установлены через
  npm. Зависимость из стека CLAUDE.md, согласована заранее. Регистрация
  через `ModuleRegistry.registerModules([AllCommunityModule])` для v33+
  (модули больше не auto-register).

**Frontend:**
- `types/api.ts` расширен типами `Period`, `PeriodType`, `SourceType`,
  `ViewMode`, `PeriodHybridItem`, `PeriodCompareItem`,
  `PatchPeriodValueResponse`, `ResetOverrideResponse`, `ScenarioRead`,
  `ScenarioUpdate`, `ScenarioResultRead`, `PeriodScope`
- `lib/period-values.ts` (новый) — `listPeriodValuesHybrid`,
  `listPeriodValues` (4 view modes), `patchPeriodValue` (создаёт
  finetuned версию append-only), `resetPeriodOverride` (DELETE override)
- `lib/reference.ts` (новый) — `listPeriods()`
- `lib/scenarios.ts` (новый) — `listProjectScenarios`, `getScenario`,
  `updateScenario`, `listScenarioResults`
- `components/projects/periods-grid.tsx` (новый) — AG Grid pivot:
  - **Rows = метрики** (ND, Off-take, Shelf price) из массива
    `METRICS` константы
  - **Columns = периоды** с pinned левой колонкой "Показатель",
    monthly/yearly заголовки (M1..M36 / Y4..Y10)
  - **Подсветка по source_type** через `cellClassRules`:
    - `bg-blue-100` для finetuned overrides
    - `bg-green-100` для actual
    - без подсветки = predict
  - **Inline edit** через `editable: true` + `singleClickEdit` +
    `stopEditingWhenCellsLoseFocus` → `onCellValueChanged` →
    `patchPeriodValue` → `reload()` (без optimistic update)
  - **"Сбросить overrides"** кнопка в шапке: `Promise.all` DELETE
    всех записей с `is_overridden=true`
  - Numeric formatting через `valueFormatter` с локалью ru-RU
  - Loading/error состояния
- `components/projects/periods-tab.tsx` (новый) — главный компонент:
  переиспользует `SkuPanel` слева (1/3), правая колонка с 3 селекторами
  (Канал / Сценарий / Период) + `PeriodsGrid` с
  `key={pscId-scenarioId}` для пересоздания при смене.
  Авто-выбор первого канала и Base сценария при загрузке.
- `app/(app)/projects/[id]/page.tsx` — добавлен новый таб **«Периоды»**
  между «Каналы» и «Результаты». Список табов: Параметры / SKU и BOM /
  Каналы / Периоды / Результаты (последний disabled до 4.2).

**E2E проверка:**
- `GET /api/periods` → 43 (M1..M36 monthly + Y4..Y10 annual)
- `GET /api/projects/1/scenarios` → 3 (Base/Conservative/Aggressive)
- `GET /api/project-sku-channels/1/values?scenario_id=1&view_mode=hybrid`
  → 43 PeriodValue с predict-слоем (auto-fill из задачи 2.5).
  Sample M1: `{nd: 0.1, offtake: 2.0, shelf_price: 100.0}`,
  source_type=predict (соответствует ND ramp 0.5×0.20=0.1).
- Frontend `/projects/1` → 200, таб «Периоды» работает

Запуск backend: **196 passed in 15.90s** (+4 от 192: 4 теста /api/periods).

**Архитектурное решение:** Pivot data конструируется на клиенте через
`useMemo` (rows = METRICS array, columns = visiblePeriods filtered по
periodFilter). Простое решение для MVP — 43 столбца × 3 строки
помещаются легко. Для большего horizon можно вынести в server-side.

### Added (задача 3.4 — Frontend: Каналы)
**Привязка SKU к каналам сбыта с авто-генерацией predict (закрытие Фазы 3):**

**Backend extension:**
- `schemas/reference.py` — `RefSeasonalityRead` Pydantic схема
- `api/reference.py` — `GET /api/ref-seasonality` (read-only, JWT,
  отсортирован по profile_name) для dropdown сезонности

**Frontend:**
- `types/api.ts` расширен Channel/ProjectSKUChannel(Create/Update/Read)/
  RefSeasonality
- `lib/channels.ts` (новый) — типизированные обёртки listChannels/
  listProjectSkuChannels/getPskChannel/addChannelToPsk/updatePskChannel/
  deletePskChannel/listRefSeasonality
- `components/projects/channel-form.tsx` (новый) — **reusable** форма
  PSC параметров: Select каналов с исключением уже привязанных,
  9 числовых полей (nd_target, ramp_months, offtake_target,
  channel_margin, promo_discount, promo_share, shelf_price_reg,
  logistics_cost_per_kg, seasonality_profile_id Select). Состояние
  как одна структура `ChannelFormState`, helper `toPscPayload` для
  API payload. Параметры `excludeChannelIds` (для add) и `channelLocked`
  (для edit).
- `components/projects/channel-dialogs.tsx` (новый) — `AddChannelDialog`
  и `EditChannelDialog`. Add: пустая форма с дефолтами, исключение
  привязанных каналов. Edit: предзаполнение через `pscToFormState`,
  channel_id заблокирован, PATCH без `channel_id` поля (backend всё
  равно игнорирует, но чисто).
- `components/projects/channels-panel.tsx` (новый) — таблица PSC
  выбранного PSK (Channel code/name, ND %, Off-take, Margin %,
  Promo discount/share, Shelf price ₽) с кнопками `✎` (edit) и `×`
  (delete с window.confirm). Кнопка "+ Привязать канал" → AddChannelDialog.
- `components/projects/channels-tab.tsx` (новый) — комбинирующий
  компонент. **Переиспользует** `SkuPanel` слева (1/3 grid) +
  `ChannelsPanel` справа (2/3) + selectedPskId state поднят сюда.
  Никаких render-prop'ов или дополнительной абстракции — каждый таб
  держит свой selection state.
- `app/(app)/projects/[id]/page.tsx` — таб "Каналы" больше не disabled,
  использует `<ChannelsTab projectId={projectId} />`. Остаётся только
  таб "Результаты" disabled (Phase 4).

**E2E проверка (curl):**
- `GET /api/ref-seasonality` → 6 профилей
- `GET /api/channels` → 25 каналов, HM id=1
- `POST /api/project-skus/1/channels` HM с дефолтами → 201
- `SELECT COUNT(*) FROM period_values WHERE psk_channel_id=1 AND source_type='predict'`
  → **129** (43 периода × 3 сценария — auto-fill predict из задачи 2.5)
- Frontend `/projects/1` → 200, таб "Каналы" работает

**3 новых backend теста** (192 total, 15.61 сек):
- `test_list_ref_seasonality_returns_seeded_profiles` — структура и наличие
- `test_list_ref_seasonality_unauthorized` — 401 без JWT
- `test_list_ref_seasonality_sorted_by_name` — алфавитная сортировка

**ФАЗА 3 ЗАКРЫТА.** End-to-end UI flow готов: пользователь регистрируется
→ создаёт проект → добавляет SKU + BOM (live COGS) → привязывает каналы
(с auto-fill predict) → готов запускать `/recalculate`. Следующая фаза —
**4. Frontend: результаты и анализ** (AG Grid периоды, KPI экран,
сравнение сценариев, чувствительность).

### Added (задача 3.3 — Frontend: SKU и BOM)
**Полный CRUD flow для SKU и BOM в карточке проекта:**

- `types/api.ts` расширен типами SKU/ProjectSKU/ProjectSKUDetail/BOMItem
  + Create/Update варианты. Decimal как `string` (Pydantic v2 → JSON Numeric).
- `lib/skus.ts` (новый файл) — типизированные обёртки над всеми SKU/PSK/BOM
  endpoints: listSkus/createSku/listProjectSkus/getProjectSku/addSkuToProject/
  updateProjectSku/deleteProjectSku/listBomItems/createBomItem/updateBomItem/
  deleteBomItem.
- `components/projects/add-sku-dialog.tsx` (новый файл) — модальный диалог
  с двумя режимами:
  - **"Из каталога"**: Select из глобального справочника `/api/skus`
  - **"Создать новый"**: форма brand/name/format/volume_l/package_type
  После создания SKU автоматически вызывает `addSkuToProject` чтобы
  пользователь не делал двух кликов.
- `components/projects/sku-panel.tsx` (новый файл) — список ProjectSKU как
  кликабельные карточки. Auto-select первого SKU при загрузке если ничего
  не выбрано (для удобства). Active state через `border-primary ring-1`.
  Удаление с `window.confirm` (BOM удаляется каскадно через FK ON DELETE
  CASCADE из задачи 1.3). Кнопка "+ Добавить" → AddSkuDialog.
- `components/projects/bom-panel.tsx` (новый файл) — основная панель работы
  с одним ProjectSKU:
  - **Editor rates**: 3 числовых поля (production_cost_rate, ca_m_rate,
    marketing_rate) с PATCH on blur — каждое поле сохраняется отдельно
    при потере фокуса. Простое решение без debounce.
  - **Таблица BOM** (shadcn Table): ingredient, qty/unit, % loss, price/unit,
    item cost (вычисляется), кнопка `×` удаления per row.
  - **Inline форма добавления** (12-column grid): name (4) + qty (2) +
    loss (2) + price (2) + button (2). HTML5 валидация.
  - **Live COGS_PER_UNIT preview** в правом верхнем углу — `Σ(qty × price
    × (1+loss))` по всем BOM items текущего PSK. Пересчитывается на
    клиенте через `computeCogsPreview()` без round-trip к backend.
- `components/projects/skus-tab.tsx` (новый файл) — комбинирующий компонент
  для таба, поднимает selectedPskId state. Layout: 2-column grid (1/3 + 2/3
  на md+, стек на mobile). Когда нет выбранного SKU справа — placeholder.
- `app/(app)/projects/[id]/page.tsx` обновлён — таб "SKU и BOM" больше не
  disabled, использует `<SkusTab projectId={projectId} />`. Табы Каналы и
  Результаты остаются disabled placeholder для задач 3.4 и Phase 4.

**Shadcn компоненты добавлены:** Dialog, Table.

**Критерий готовности (E2E проверка через curl):**
- Создать SKU `Gorji / Test 3.3 SKU / 0.5L PET` → 201
- Привязать к проекту → 201, sku вложен в response
- Добавить 3 BOM ингредиента (Sugar/Concentrate/Water)
- GET project-sku detail → `cogs_per_unit_estimated: "12.1800000000000000"`
- Math: `0.05×80×1.02 + 0.005×1500×1.05 + 0.45×0.5×1.0 = 4.08 + 7.875 + 0.225 = 12.18 ✓`
- Все frontend маршруты компилируются (200), backend pytest **189/189** зелёные

**Архитектурное замечание:** В этой задаче backend не менялся — API уже был
готов в задаче 1.3. Фокус только на UI и интеграции.

### Added (задача 3.2 — Frontend: список и создание проектов)
**Frontend MVP первый CRUD-flow + backend extensions:**

**Backend extensions:**
- `services/project_service.py:list_projects` — теперь возвращает
  `list[ProjectListRow]` (dataclass с проектом + npv/irr/go_no_go из
  Base/Y1Y10 ScenarioResult). LEFT JOIN в одном запросе вместо N+1.
- `api/projects.py:list_projects_endpoint` обновлён под новую сигнатуру.
- `schemas/reference.py` (новый файл) — `RefInflationRead` Pydantic схема.
- `api/reference.py` (новый файл) — `GET /api/ref-inflation` для dropdown
  в форме создания проекта. Read-only, защищён JWT, отсортирован по
  profile_name.
- `main.py` подключает `reference_router`.

**Frontend:**
- `types/api.ts` (новый файл) — TypeScript типы синхронизированные с
  Pydantic схемами: Project*, RefInflation, UserMe. Decimal как `string`
  (приходит с backend как Pydantic v2 → JSON Numeric).
- `lib/projects.ts` (новый файл) — типизированные обёртки над apiGet/Post:
  `listProjects/getProject/createProject/updateProject/deleteProject/
  listRefInflation`.
- `lib/format.ts` (новый файл) — `formatMoney` (₽ + ru-RU разделители),
  `formatPercent`, `formatDate` (Intl.DateTimeFormat).
- `components/go-no-go-badge.tsx` (новый файл) — цветной badge:
  - `true` → GREEN "GO" (bg-green-600)
  - `false` → RED "NO GO" (bg-red-600)
  - `null` → серый outline "не рассчитан" (расчёт не запускался)
- `app/(app)/projects/page.tsx` обновлён — список карточек:
  название, GoNoGo badge, "Старт: дата · N лет", NPV Y1-Y10, WACC.
  Loading/empty/error состояния. Кнопка "Создать проект" → `/projects/new`.
  Grid responsive (1/2/3 колонки в зависимости от ширины).
- `app/(app)/projects/new/page.tsx` (новый файл) — форма создания:
  Card с CardHeader/Content/Footer, Input для name/start_date/horizon_years
  и 4 финансовых параметров (wacc/tax_rate/wc_rate/vat_rate с дефолтами
  0.19/0.20/0.12/0.20), Select для inflation_profile_id (загружается
  через `/api/ref-inflation`, опция "Без инфляции"). HTML5 валидация.
  После create → `router.push("/projects/{id}")`. Кнопка "Отмена"
  возвращает на `/projects`.
- `app/(app)/projects/[id]/page.tsx` (новый файл) — карточка проекта:
  `<` назад → /projects, заголовок с названием и метаданными.
  Tabs ("Параметры" активная, "SKU и BOM" / "Каналы" / "Результаты"
  disabled placeholder для задач 3.3-3.4). Tab Параметры показывает
  WACC/Tax/WC/VAT в %, валюту, профиль инфляции. 404 → понятное
  сообщение с кнопкой "К списку".

**Shadcn компоненты добавлены:** Badge, Select, Tabs (через `shadcn add`).

**Тесты** (4 новых, 189 total за 15.26 сек):
- `tests/api/test_reference.py` (новый файл, 3 теста):
  - `test_list_ref_inflation_returns_seeded_profiles` — 16 профилей,
    "No_Inflation" + "Апрель/Октябрь +7%" присутствуют, структура
    с `month_coefficients` dict
  - `test_list_ref_inflation_unauthorized` — 401 без JWT
  - `test_list_ref_inflation_sorted_by_name` — алфавитная сортировка
- `tests/api/test_projects.py:test_list_projects_returns_kpi_after_calculation` —
  после прямого INSERT в ScenarioResult (Base + Y1Y10) GET /api/projects
  возвращает npv/irr/go_no_go из расчёта. Проверяет JOIN.

**E2E проверка:**
- POST /api/projects 201 → проект создан, id=1
- GET /api/projects → список с npv_y1y10=null (расчёт не выполнен)
- GET /api/ref-inflation → 16 профилей
- Frontend: /projects, /projects/new, /projects/1 → все 200

Запуск backend: `pytest -q` → **189 passed in 15.26s** (66+4 CRUD +
90 engine + 13 predict + 16 calculation, 0 warnings).

### Added (задача 3.1 — Frontend: routing, layout, auth)
**Первая задача Фазы 3 — фронтенд авторизация и защищённые маршруты:**

- **Tailwind CSS v4 + shadcn/ui v4** — установлены, инициализированы.
  CSS-based config через `app/globals.css` (`@import "tailwindcss"`),
  postcss.config.mjs с `@tailwindcss/postcss`. Base components добавлены:
  Button, Input, Label, Card. Inter шрифт через `next/font/google` (Geist
  доступен только в Next.js 15+, у нас 14.2).
- **`frontend/lib/api.ts`** — fetch wrapper:
  - Auto-attach `Authorization: Bearer` header
  - При 401 → попытка refresh через `/api/auth/refresh`, retry оригинального
    запроса; при неуспехе → `clearTokens()` (AuthProvider увидит и перенаправит)
  - `ApiError` класс с `status` и `detail`
  - Типизированные `apiGet/Post/Patch/Delete`
  - Отдельный `loginRequest` через OAuth2 password flow (form-urlencoded)
- **`frontend/lib/auth.ts`** — SSR-safe localStorage helpers (возвращают
  null на сервере) для access/refresh JWT
- **`frontend/components/auth-provider.tsx`** — React Context + `useAuth()`:
  - Восстановление сессии при mount через `/api/auth/me`
  - `login(email, password)` → токены в localStorage + `router.push("/projects")`
  - `logout()` → `clearTokens()` + `router.push("/login")`
- **`frontend/app/(auth)/login/page.tsx`** — login форма (Card + Input + Button)
  с обработкой ApiError, loading state кнопки, автоматическим редиректом
  на /projects если уже залогинен
- **`frontend/components/sidebar.tsx`** — sidebar навигация с активным
  состоянием через `usePathname`, email текущего user + кнопка "Выйти"
- **`frontend/app/(app)/layout.tsx`** — защищённый layout с client-side
  auth check: при `!loading && user === null` → `router.replace("/login")`.
  Loading спиннер во время восстановления сессии (избегает flash контента).
- **`frontend/app/(app)/projects/page.tsx`** — placeholder для задачи 3.2
- **`frontend/app/page.tsx`** — корневой `/` редиректит на `/projects`
  или `/login` в зависимости от auth state
- **`backend/scripts/create_dev_user.py`** — идемпотентный скрипт для создания
  dev user `admin@example.com / admin123`. Только для dev (в prod через
  Keycloak / административные процедуры по ADR-08).

**Архитектурные решения:**
- localStorage для токенов (не httpOnly cookies — проще для SPA)
- React Context для auth state (избыточно ставить zustand для одного state'а)
- Защита через client-side useEffect (Next.js middleware не имеет доступа
  к localStorage на server-side)
- Route groups `(auth)` и `(app)` для группировки публичных и защищённых
  маршрутов с разными layout'ами

**Известные ограничения:**
- Frontend dev server не подхватывает структурные изменения (новые route
  groups) через HMR на Windows + Docker volume mount. Требуется ручной
  `docker compose restart frontend` после добавления route group.
- Pre-existing уязвимости в Next.js 14.2.35 (4 high severity) — фикс
  требует major upgrade до Next.js 16, отдельная задача.

**End-to-end проверка:**
1. `python -m scripts.create_dev_user` → `admin@example.com` создан
2. `curl POST /api/auth/login` form-urlencoded → access+refresh tokens
3. `curl GET /api/auth/me` с Bearer → `{"email":"admin@example.com",...}`
4. Frontend `/`, `/login`, `/projects` все возвращают 200 после
   `docker compose restart frontend`
5. Backend pytest 185/185 зелёные после изменений (только новый dev_user
   скрипт, кодовая база backend'а не тронута)

Frontend unit/e2e тесты не реализованы в 3.1 — добавятся позже (Vitest/
Playwright по необходимости).

### Added (задача 2.5 — Predict-слой автогенерации)
**Автоматическое заполнение PeriodValue при создании ProjectSKUChannel:**

- `backend/app/services/predict_service.py` — новый сервис:
  - `_ramp_values(target, ramp_months, start_pct, n_monthly)` — pure function
    линейного рамп-апа от target × start_pct (default 20%) до target за
    ramp_months месяцев. После рамп-апа — плато target.
  - `_shelf_price_series(base, sorted_periods, profile)` — pure function
    применения инфляционного профиля по месяцам:
    - Monthly периоды: `shelf[t] = shelf[t-1] × (1 + monthly_deltas[month_num−1])`
    - Yearly периоды (Y4-Y10): `shelf[Yk] = shelf[предыдущего] × (1 + yearly_growth[k−4])`
  - `fill_predict_for_psk_channel(session, psc)` — async, создаёт 43 × 3 = 129
    PeriodValue с predict-слоем (43 периода × 3 сценария: Base/Conservative/Aggressive).
    Идемпотентно: при повторном вызове удаляет старые predict перед созданием новых.
    Finetuned/actual слои не трогаются.
- `backend/app/services/project_sku_channel_service.py`:
  - `create_psk_channel` принимает `auto_fill_predict: bool = True` (default).
    После успешного create вызывает `fill_predict_for_psk_channel`.
    Параметр `auto_fill_predict=False` нужен тестам `test_period_values`,
    которые управляют PeriodValue слоями вручную.

**Архитектурные решения:**
- Predict значения **одинаковы для всех 3 сценариев** (Base/Conservative/Aggressive).
  Сценарные дельты (`delta_nd`, `delta_offtake`) применяются runtime в
  `calculation_service.build_line_inputs`. Это упрощает predict_service
  и позволяет менять scenario delta без перегенерации predict.
- Сезонность хранится в `ref_seasonality` profile (PSC.seasonality_profile_id),
  применяется в `s01_volume`, **не** записывается в JSONB PeriodValue.
- ND_START_PCT и OFFTAKE_START_PCT захардкожены = 0.20 (D-10/D-11). Если
  бизнесу нужно сделать их параметром PSC — отдельная задача.

**Тесты** (13 новых, 185 total за 14.47 сек):

*`tests/api/test_predict_service.py`*:
- `TestRampValues` (4): target=0 → all zeros, ramp_months=0 → start at target,
  linear interpolation first/last/plato, ramp longer than horizon
- `TestShelfPriceSeries` (3): no profile → constant, **Апрель/Октябрь +7%
  профиль** (M1-M3 = база, M4 = база × 1.07, M10 = M4 × 1.07), **yearly_growth
  для Y4-Y10**
- `TestAutoFill` (6): 129 строк, **3 сценария × 43 периода**, **ND ramp pattern**
  (M1=0.10, M12=0.467, M13+=0.50), Offtake ramp pattern с ramp=6 месяцев,
  **идемпотентность** (повторный вызов → 129 строк не 258), **finetuned
  слой не трогается** при пересоздании predict

**Обновления существующих тестов:**
- `tests/api/test_period_values.py`: `_setup_psk_channel` теперь использует
  сервис `create_psk_channel(auto_fill_predict=False)` вместо API endpoint —
  тестам нужно вручную управлять слоями PeriodValue.
- `tests/api/test_calculation.py`: `_seed_minimal_project` упрощён —
  ручное создание 43 PeriodValue убрано, auto-fill через сервис делает
  всё сам. Параметры `nd_target=0.001, offtake_target=1.0, shelf_price=10.0`
  выбраны малыми чтобы итоговый ROI помещался в `Numeric(10, 6)` (Excel quirk
  D-06: при всех положительных FCF формула вырождается в среднее).
- Helper `_clone_period_values_to_other_scenarios` удалён — больше не нужен,
  auto-fill сразу создаёт записи для всех 3 сценариев.

Запуск: **185 passed in 14.47s** (66 CRUD + 90 engine + 13 predict + 16 calculation, 0 warnings).

**Фаза 2 закрыта.** Расчётное ядро готово end-to-end: пользователь создаёт
проект → SKU → канал, predict значения генерируются автоматически,
`POST /api/projects/{id}/recalculate` запускает Celery task, `ScenarioResult`
сохраняется по 3 сценария × 3 скоупа = 9 строк. Следующая фаза — Frontend.

### Added (post-2.4: ProjectFinancialPlan — project-level CAPEX/OPEX в БД)
**Изменение схемы (новая таблица + миграция):**

- `backend/app/models/entities.py` — модель `ProjectFinancialPlan`:
  - `id` (PK), `project_id` (FK projects CASCADE), `period_id` (FK periods RESTRICT)
  - `capex` Numeric(20, 2), `opex` Numeric(20, 2)
  - `UNIQUE(project_id, period_id)` — одна запись на (проект × период)
  - timestamps через TimestampMixin
- `backend/migrations/versions/0bc2641bd568_add_project_financial_plans.py` —
  Alembic миграция (autogenerated, проверена upgrade/downgrade в dev DB)
- `backend/app/services/calculation_service.py`:
  - `_load_project_financial_plan(session, project_id, sorted_periods)` →
    `(capex_tuple, opex_tuple)` длины 43, нули для отсутствующих периодов;
    пустые tuples если в plan вообще нет записей для проекта
  - `calculate_and_save_scenario` теперь грузит plan и передаёт в
    `run_project_pipeline` через `project_capex` / `project_opex`

**Архитектурное обоснование (вариант 2 из обсуждения после 2.4):**
Project-level capex/opex хранятся в **отдельной таблице с FK на period**,
а не как JSONB-поля в Project. Преимущества:
- Чище: одна строка = одна запись (capex/opex для конкретного периода),
  легче валидировать, индексировать, редактировать через будущее API
- Масштабируемее: можно добавить новые поля (например `notes`,
  `category`, `approved_by`) без изменения схемы Project
- Соответствует общему паттерну: `project_sku_channels`, `period_values` —
  все per-period данные хранятся в отдельных таблицах
- CASCADE на projects означает что при удалении проекта plan тоже удаляется

**Тесты** (4 новых, 172 total за 14 сек):
- `test_no_financial_plan_means_zero_capex` — без записей в plan FCF == OCF
- `test_financial_plan_capex_reduces_fcf` — CAPEX 5000₽ на M1 → FCF[0] -= 5000,
  ICF[0] = -5000 (vs 0 без plan)
- `test_financial_plan_opex_reduces_contribution` — OPEX 100₽ на M1 →
  contribution[0] и OCF[0] -= 100
- `test_load_plan_with_partial_periods` — partial fill (3 записи из 43) →
  tuples длины 43 с нулями на отсутствующих периодах

Запуск: **172 passed in 14.00s** (66 CRUD + 90 engine + 16 calculation, 0 warnings).

API endpoints для CRUD над ProjectFinancialPlan **не реализованы** в этом
коммите — добавятся в Phase 3 вместе с UI редактирования. Сейчас записи
можно создавать только через прямой INSERT (или из тестов / seed скриптов).

### Added (задача 2.4 — Celery pipeline orchestration)
**End-to-end оркестратор расчёта от БД до ScenarioResult:**

- `backend/app/engine/aggregator.py` — `aggregate_lines(line_contexts)` складывает
  per-line PipelineContext'ы в один проектный агрегат element-wise по всем
  per-period полям (NR, COGS, GP, CM, FCF и т.д.). Метаданные временной оси
  и project-level параметры (wacc, wc_rate, tax_rate) берутся из первой линии.
  Опциональные `project_capex` и `project_opex` для применения на уровне
  агрегата.
- `backend/app/engine/pipeline.py` — оркестратор:
  - `run_line_pipeline(input)` — прогон s01..s09 для одной линии
  - `run_project_pipeline(line_inputs, project_capex=, project_opex=)` —
    per-line + aggregate + s10..s12 → готовый PipelineContext с KPI словарями
- `backend/app/services/calculation_service.py` — точка интеграции pipeline ↔ БД:
  - `build_line_inputs(session, project_id, scenario_id)` — грузит ProjectSKU/PSC
    с selectinload, эффективные PeriodValue (priority actual > finetuned > predict),
    BOM unit cost, channel.universe_outlets, seasonality профиль; применяет
    scenario delta_nd / delta_offtake; формирует list[PipelineInput]
  - `calculate_and_save_scenario` — pipeline + удаление старых ScenarioResult +
    сохранение 3 новых per scope (Y1Y3/Y1Y5/Y1Y10)
  - `calculate_all_scenarios(session, project_id)` — для всех 3 сценариев проекта
- `backend/app/tasks/calculate_project.py` — Celery task `calculate_project_task`
  с `asyncio.run(_calculate_project_async)` wrapper'ом. Сессия БД создаётся
  внутри async-функции через `async_session_maker`. Domain-исключения
  (`ProjectNotFoundError`, `NoLinesError`) возвращаются как error-result,
  остальные пробрасываются для Celery FAILED state.
- `backend/app/api/projects.py` — `POST /api/projects/{id}/recalculate` →
  202 Accepted + `{task_id, project_id, status: "PENDING"}`. Импорт задачи
  внутри функции чтобы избежать загрузки celery_app на import-time API модуля.
- `backend/app/api/tasks.py` (новый файл) — `GET /api/tasks/{task_id}` →
  опрос Celery AsyncResult. Возвращает status (PENDING/STARTED/SUCCESS/FAILURE)
  + result или error/traceback.
- `backend/app/worker.py` — добавлен `import app.tasks` после создания
  `celery_app` для регистрации тасков.
- `backend/app/main.py` — подключён `tasks_router`.

**Архитектурные решения 2.4:**
- Pipeline = pure functions, БД только в `calculation_service`
- Aggregator складывает per-period values; KPI считаются на агрегате (не суммируются
  per-line) — это математически корректно для NPV/IRR/Payback
- Async ↔ Celery через `asyncio.run` per-task — чисто, изолированно, без
  пулинга event loop'ов
- `project_capex` / `project_opex` пока пустые tuples (TODO: добавить поля
  в Project model в Phase 3 когда появится UI для редактирования). MVP
  даёт FCF = OCF (без инвестиционного оттока на уровне проекта).

**Тесты** (24 новых, 168 total за 13.95 сек):

*`tests/engine/test_aggregator.py`* (6 тестов): empty list raises, single
line passthrough, two identical lines doubles values, period_count mismatch
raises, metadata from first line, project_capex passed to input.

*`tests/engine/test_pipeline.py`* (6 тестов): run_line single/multi period,
run_project empty raises, single line project, two lines aggregated,
project_capex reduces FCF.

*`tests/api/test_calculation.py`* (12 тестов, integration с реальной БД):
- `TestBuildLineInputs` (4): builds 1 input for 1 PSC (universe_outlets=822 из HM seed,
  bom_unit_cost из BOMItem, vat/wacc/wc_rate из Project), project_not_found,
  no_lines_error, scenario delta_nd applied (×0.90 для Conservative)
- `TestCalculateScenario` (3): создаёт 3 ScenarioResult per scope, results имеют
  KPI значения (NPV, ROI, CM, go_no_go non-None), recalculate replaces old
  results (старые удаляются)
- `TestRecalculateEndpoint` (3): возвращает 202 + task_id (с monkeypatch на
  task.delay чтобы не дёргать реальную async session), 404 для unknown project,
  401 unauthorized
- `TestGetTaskStatus` (2): PENDING для unknown task_id (Celery дизайн), 401
  unauthorized

Eager Celery mode через autouse fixture: `task_always_eager=True`,
`task_eager_propagates=True`, `task_store_eager_result=True` (последнее —
подавляет RuntimeWarning о хранении результатов в eager mode).

Запуск: `docker compose -f infra/docker-compose.dev.yml exec backend pytest -v`
→ **168 passed in 13.95s** (66 CRUD + 90 engine + 12 calculation, 0 warnings).

### Added (задача 2.3 — Pipeline steps 10–12 + IRR solver)
**Расчётное ядро — финансовые KPI и Go/No-Go:**

- `backend/app/engine/irr.py` — **собственный IRR solver** (Newton-Raphson +
  bisection fallback). Без внешних зависимостей. 50 строк. Покрытие — GORJI
  Y1-Y3/Y1-Y5/Y1-Y10 до rel 1e-6.
  - Newton-Raphson из 5 начальных guess'ов (-0.5, 0.0, 0.1, 0.5, 1.0)
  - Bisection в `[-0.999, 10.0]` если NR расходится / производная = 0
  - `None` если решения нет (все cashflows одного знака) или ни один метод не сошёлся
- `backend/app/engine/steps/s10_discount.py` — аннуализация per-period в годовые
  бакеты по `model_year`, `DCF[t] = ANNUAL_FCF[t] / (1+WACC)^t`,
  cumulative_fcf/cumulative_dcf для payback, Terminal Value (Гордон) как
  справочный показатель (D-07 — НЕ входит в NPV).
- `backend/app/engine/steps/s11_kpi.py` — NPV/IRR/ROI/Payback по 3 скоупам:
  - NPV: `SUM(annual_dcf[0:end])` где end ∈ {3, 6, 10}
  - **D-12 Excel quirk**: scope "Y1-Y5" в Excel формуле использует 6 элементов,
    не 5 (`=SUM(B44:G44)`). Реализуем как в Excel, документировано в
    TZ_VS_EXCEL_DISCREPANCIES.md.
  - IRR: собственный solver
  - ROI: Excel D-06 формула `(−SUM/(SUMIF<0 − 1))/COUNT` (НЕ ТЗ-формула)
  - Payback simple/discounted: count лет где cumulative < 0; `None` если > threshold
  - Contribution Margin overall ratio: `SUM(CM)/SUM(NR)` для всего проекта
- `backend/app/engine/steps/s12_gonogo.py` — `GREEN if NPV[scope] >= 0 AND CM_ratio >= 0.25`
  для каждого скоупа отдельно.

**PipelineInput** расширен полем `wacc` (Project.wacc, default 0.19).

**PipelineContext** дополнен 13 новыми полями: `annual_free_cash_flow`,
`annual_discounted_cash_flow`, `cumulative_fcf`, `cumulative_dcf`,
`annual_net_revenue`, `annual_contribution`, `terminal_value`, `npv`, `irr`,
`roi`, `payback_simple`, `payback_discounted`, `contribution_margin_ratio`,
`go_no_go`. KPI — словари по скоупам ("y1y3" / "y1y5" / "y1y10").

**Тесты** — 34 новых, 144 total в 12.74 сек:

*`test_irr.py`* (16 тестов):
- TestNPV (3): zero_rate, simple, neg-one защита
- TestIRR (13): two_period 10%, three_period 23.4%, zero, negative,
  no_sign_change → None, all_negative → None, empty → None, single → None,
  npv_at_irr ≈ 0, high_irr через bisection,
  **GORJI Y1-Y10 = 78.6%, Y1-Y3 = -60.97%, Y1-Y5 = 64.12% (6 элементов)**

*`test_steps_10_12.py`* (18 тестов):
- TestDiscount (6): annualization passthrough yearly, **DCF ↔ DATA row 44**,
  **cumulative_fcf ↔ DATA row 56**, **cumulative_dcf ↔ DATA row 57**, monthly
  → yearly aggregation (M1..M12 → 1 элемент), **Terminal Value ↔ DATA row 47 col 4**
- TestKpi (6): **NPV три скоупа ↔ DATA row 48** (rel 1e-9), **IRR три скоупа
  ↔ DATA row 50** (rel 1e-6), **ROI три скоупа ↔ DATA row 49** (rel 1e-9),
  **payback simple = {3,3,3}**, **payback discounted = {None, 4, 4}**,
  CM ratio ≈ 25.1%
- TestGoNoGo (6): GORJI Y1-Y10 GREEN, Y1-Y3 RED (NPV<0), Y1-Y5 GREEN,
  low CM ratio blocks all, NPV=0 threshold (≥), CM=0.25 threshold (≥)

**TZ_VS_EXCEL_DISCREPANCIES.md** — добавлено D-12 (Excel quirk Y1-Y5 = 6 элементов).

Запуск: `docker compose -f infra/docker-compose.dev.yml exec backend pytest -v`
→ **144 passed in 12.74s** (66 CRUD + 78 engine, 0 warnings).

### Added (задача 2.2 — Pipeline steps 6–9)
**Расчётное ядро — вторая половина без KPI/discount:**

- `backend/app/engine/steps/s06_ebitda.py` — `EBITDA = CM − NR×CA_M_RATE − NR×MARKETING_RATE`
  (Excel DATA rows 29-31). По D-05 КАиУР и Marketing — % от NR на уровне ProjectSKU,
  вычитаются на уровне EBITDA, не Contribution.
- `backend/app/engine/steps/s07_working_capital.py` — `WC[t] = NR[t] × wc_rate`
  и `ΔWC[t] = WC[t-1] − WC[t]` с граничным случаем `ΔWC[0] = −WC[0]` (нет
  предыдущего периода). **D-01 / ADR-CE-02** — формула ТЗ `× (1 − 0.12)` неверна,
  ΔWC основан на изменении уровня WC, не на удержании от Contribution.
- `backend/app/engine/steps/s08_tax.py` — `TAX[t] = −(CM × tax_rate)` если CM ≥ 0,
  иначе 0. **D-03 / ADR-CE-04** — нет налогового щита при убытке, знак отрицательный
  (отток), база — Contribution.
- `backend/app/engine/steps/s09_cash_flow.py` — `OCF = CM + ΔWC + TAX`,
  `ICF = −CAPEX`, `FCF = OCF + ICF` (Excel DATA rows 41-43).

**Расширения PipelineInput** (`backend/app/engine/context.py`):
- `ca_m_rate`, `marketing_rate` — % от NR (ProjectSKU level)
- `wc_rate`, `tax_rate` — Project-level financial parameters
- `capex: tuple[float, ...] = ()` — per-period investment, default empty (zeros).
  На per-line уровне обычно 0, оркестратор (2.4) добавляет project-level.
- Валидация длин для `capex`.

**PipelineContext** дополнен полями: `ca_m_cost`, `marketing_cost`, `ebitda`,
`working_capital`, `delta_working_capital`, `tax`, `operating_cash_flow`,
`investing_cash_flow`, `free_cash_flow`.

**Тесты** (`backend/tests/engine/test_steps_6_9.py`) — 17 новых, ≈0.13 сек:

- `TestEbitda` (3): subtraction формула, zero-rates → EBITDA=CM, pre-condition
- `TestWorkingCapital` (4): WC формула, граничный t=0, multi-period растущий WC,
  **численная сверка с Excel DATA rows 38-39** (Y0/Y1 GORJI агрегаты — WC и ΔWC
  совпадают до 1e-9)
- `TestTax` (4): positive→negative tax, negative→0 (нет щита), zero→0,
  **сверка с Excel DATA row 40 Y0/Y1**
- `TestCashFlow` (5): OCF=CM+ΔWC+TAX, ICF=−CAPEX, empty capex→0, FCF=OCF+ICF,
  **полная сверка цепочки s07-s09 с DATA rows 41-43 Y0/Y1**
- `TestPipelineSmoke6_9` (1): full s01..s09 на 3-период с capex в Y0

**Acceptance EBITDA** (`backend/tests/engine/test_gorji_reference.py` +2 теста):
- `test_ebitda_per_unit_m1_m3` — 5.66203 ₽/unit ↔ DASH row 48 col D-F
- `test_ebitda_per_unit_m4_m6` — 4.69769 ₽/unit (после апрельской инфляции)

Эталонные значения извлечены тем же openpyxl one-shot методом что и в 2.1.
В `requirements.txt` openpyxl не добавлен.

Запуск: `docker compose -f infra/docker-compose.dev.yml exec backend pytest -v`
→ **110 passed in 12.45s** (66 CRUD + 44 engine, 0 warnings).

### Added (задача 2.1 — Pipeline steps 1–5)
**Расчётное ядро — первая половина pipeline:**

- `backend/app/engine/context.py` — `PipelineInput` (frozen dataclass, иммутабельный вход)
  и `PipelineContext` (мутабельный контейнер промежуточных результатов шагов).
  `PipelineInput.__post_init__` валидирует длины всех массивов — падаем рано с
  понятной ошибкой, не IndexError глубоко в шаге.
- `backend/app/engine/steps/s01_volume.py` — `VOLUME_UNITS = UNIVERSE × ND × OFFTAKE × SEASONALITY`
- `backend/app/engine/steps/s02_price.py` — price waterfall с **D-02/ADR-CE-03**:
  `EX_FACTORY = SHELF_W / (1 + VAT) × (1 − CHANNEL_MARGIN)` (делим на 1+VAT, не умножаем на 1−VAT).
- `backend/app/engine/steps/s03_cogs.py` — COGS из BOM (material+package lumped),
  production % от ex_factory (**D-04**), copacking (0 в MVP).
- `backend/app/engine/steps/s04_gross_profit.py` — `GP = NR − COGS` **без логистики** (Excel DATA row 23).
- `backend/app/engine/steps/s05_contribution.py` — `CM = GP − LOGISTICS − PROJECT_OPEX`
  где `LOGISTICS = cost_per_kg × volume_liters × density` (**D-09**).

**Расхождение с первоначальной формулировкой 2.1 из плана:** логистика перенесена
из s04 (Gross Profit) в s05 (Contribution) чтобы соответствовать Excel-семантике.
Итоговая Contribution та же, но терминология критична для сверки с эталоном.
ADR-CE-01 приоритетно.

**Тесты** (`backend/tests/engine/`) — 25 pure-function тестов, ≈0.25 сек:

*`test_steps_1_5.py`* (18 unit тестов):
1. `TestVolume` — базовый, zero_nd, seasonality, multi_period (4)
2. `TestPrice` — ADR-CE-03 VAT, promo waterfall, net_revenue, pre-condition (4)
3. `TestCogs` — material_only, production_rate_on_ex_factory, all_three_components,
   zero_volume (4)
4. `TestGrossProfit` — GP = NR − COGS, логистика **не** влияет на GP (1)
5. `TestContribution` — logistics + opex subtract, empty_opex=zeros, zero_density (3)
6. `TestPipelineSmoke` — 3-period full run + input length validation (2)

*`test_gorji_reference.py`* (7 acceptance тестов против GORJI+ Excel):
Эталонные per-unit значения извлечены из `PASSPORT_MODEL_GORJI_2025-09-05.xlsx`,
лист DASH, блок SKU_1 (Gorji Цитрус Газ Пэт 0,5 × канал HM), 6 месяцев (M1-M6).
openpyxl использован одноразово через `docker cp + docker exec`, в requirements.txt
не добавлен (назначен Фазе 5).

1. `test_active_outlets_matches_dash_row_22` — universe=822 × nd[t] ↔ DASH row 22
2. `test_price_waterfall_matches_dash_rows_30_35` — shelf_promo / weighted / ex_factory
3. `test_gross_profit_per_unit_m1_m3` — GP/unit = 14.4293 ₽ (M1-M3, до инфляции)
4. `test_gross_profit_per_unit_m4_m6` — GP/unit = 13.7450 ₽ (M4-M6, после апрельской +7%)
5. `test_contribution_per_unit_m1_m3` — CM/unit = 10.4293 ₽
6. `test_contribution_per_unit_m4_m6` — CM/unit = 9.4650 ₽
7. `test_inflation_jump_m3_to_m4` — защитный assert: эталон M3 ≠ M4 (поймать если
   тест "проходит" из-за одинакового эталона)

Запуск: `docker compose -f infra/docker-compose.dev.yml exec backend pytest -v`
→ **91 passed in 12.36s** (66 CRUD + 25 engine, 0 warnings).

### Added (задача 1.6 — Scenarios API)
**Endpoints:**
- `GET    /api/projects/{project_id}/scenarios` — 3 сценария проекта в порядке Base → Conservative → Aggressive
- `GET    /api/scenarios/{id}` — один сценарий по id (для удобства frontend перед PATCH)
- `PATCH  /api/scenarios/{id}` — обновить дельты (`delta_nd`, `delta_offtake`, `delta_opex`) и `notes`. Поля `type` и `project_id` отсутствуют в `ScenarioUpdate` — Pydantic v2 ignores unknown fields, попытка передать `type` молча игнорируется (тест 6 подтверждает)
- `GET    /api/scenarios/{id}/results` — список `ScenarioResult` в порядке Y1Y3 → Y1Y5 → Y1Y10. **404 с actionable message** если расчёт не выполнен: `"Scenario has not been calculated yet. Run POST /api/projects/{project_id}/recalculate first (available after task 2.4)."`

**Service** (`backend/app/services/scenario_service.py`):
- Сортировка через explicit order maps `SCENARIO_ORDER` и `SCOPE_ORDER` — алфавит даёт неправильный порядок (`aggressive < base < conservative`, `y1y10 < y1y3 < y1y5`). Сортировка в Python после fetch
- `list_scenarios_for_project`, `get_scenario`, `update_scenario`, `list_results_for_scenario`

**Pydantic схемы** (`backend/app/schemas/scenario.py`):
- `ScenarioRead` (полная)
- `ScenarioUpdate` — только дельты + notes. Дельты могут быть отрицательными: `Field(ge=-1, le=1)` — диапазон от -100% до +100%, потому что Conservative обычно `delta_nd<0`
- `ScenarioResultRead` — все KPI поля nullable (npv, irr, roi, payback, margins, go_no_go), заполняются расчётным ядром в задаче 2.4

**Тесты** (`backend/tests/api/test_scenarios.py`) — 9 кейсов:
1. GET project scenarios → 3 сценария в порядке `["base", "conservative", "aggressive"]`
2. GET без auth → 401
3. GET для несуществующего проекта → 404
4. GET single scenario by id → 200 с правильным type и default дельтами
5. PATCH delta_nd/delta_offtake/notes → 200, поля обновлены, type не менялся
6. PATCH с body `{type: aggressive, delta_nd: 0.15}` → type проигнорирован (Pydantic ignore), delta_nd обновлён
7. PATCH с delta_nd > 1 → 422 (Field validation)
8. GET results без расчёта → 404 с детальным actionable сообщением (содержит "not been calculated", "recalculate", "task 2.4")
9. GET results после insert 3 ScenarioResult напрямую → 200, порядок `["y1y3", "y1y5", "y1y10"]`. Эталонные NPV из задачи 2.3 GORJI+: -11.6M / 27.3M / 80.0M, go_no_go=False/True/True

Запуск: `docker compose -f infra/docker-compose.dev.yml exec backend pytest -v` → **66 passed in 12.40s** (8 auth + 12 projects + 14 skus + 11 channels + 12 period_values + 9 scenarios, 0 warnings).

**Фаза 1 (Backend CRUD API) закрыта полностью.**

### Added (задача 1.5 — PeriodValues API + трёхслойная модель данных)
Материализация ADR-05 (трёхслойная модель `predict / finetuned / actual` с приоритетом `actual > finetuned > predict`) и версионирование fine-tuned значений.

**Endpoints:**
- `GET    /api/project-sku-channels/{id}/values?scenario_id=&view_mode=hybrid` — значения по периодам с применением приоритета слоёв. 4 view modes: `hybrid` (default), `fact_only`, `plan_only`, `compare`
- `PATCH  /api/project-sku-channels/{id}/values/{period_id}?scenario_id=` — fine-tune. Append-only: создаёт новую строку с `version_id = MAX + 1`, `is_overridden=true`. Старые версии остаются как audit log
- `DELETE /api/project-sku-channels/{id}/values/{period_id}/override?scenario_id=` — сброс к predict. Удаляет ВСЕ finetuned версии для периода. Идемпотентно — если не было finetuned, вернёт `deleted_versions=0`

**Service** (`backend/app/services/period_value_service.py`):
- `validate_context(psk_channel_id, scenario_id, period_id)` — проверка цепочки и бизнес-инварианта (scenario должен принадлежать тому же проекту, что и psk_channel). Custom exceptions: `PSKChannelNotFoundError`, `PeriodNotFoundError`, `ScenarioMismatchError`
- `get_values_hybrid` — один проход по всем строкам для (psk_channel, scenario), группировка в Python через `_resolve_priority`. Для каждого слоя берётся latest version, потом применяется приоритет actual > finetuned > predict
- `get_values_fact_only` — только actual-слой, latest version per period
- `get_values_plan_only` — `_resolve_priority(exclude_actual=True)`. Возвращает finetuned (если есть) или predict
- `get_values_compare` — все три слоя в одной структуре `CompareResponseItem` с полями `predict`, `finetuned`, `actual` (None если слоя нет)
- `patch_value` — append-only: `SELECT MAX(version_id) WHERE finetuned ... + 1`, INSERT новой строки
- `reset_value_to_predict` — `DELETE WHERE source_type=finetuned AND ...`, возвращает rowcount

**Pydantic схемы** (`backend/app/schemas/period_value.py`):
- `ViewMode` enum (str)
- `PeriodValueWrite` — тело PATCH (только `values: dict[str, Any]`, JSONB произвольной формы — в MVP только входные показатели по решению пользователя)
- `HybridResponseItem`, `CompareResponseItem`, `PatchPeriodValueResponse`, `ResetOverrideResponse`

**Endpoint особенности:**
- `view_mode` через query param, response shape зависит от значения. `response_model=Any` потому что union response model в FastAPI путает OpenAPI генерацию. Frontend знает что ожидать по тому какой view_mode передал
- `scenario_id` обязательный query parameter (без него непонятно к какому сценарию относятся values)
- Бизнес-валидация scenario↔project работает через `validate_context` — без неё можно было бы создать PeriodValue с scenario из чужого проекта, чего FK constraints отдельно не проверяют

**Тесты** (`backend/tests/api/test_period_values.py`) — 12 кейсов:
1. PATCH создаёт finetuned v1, is_overridden=True
2. PATCH дважды → version_id=1, 2 (append-only, обе строки в БД)
3. GET hybrid с только predict → возвращает predict
4. GET hybrid: finetuned побеждает predict
5. GET hybrid: actual побеждает finetuned и predict
6. GET hybrid: берёт latest finetuned версию (3 PATCH → возвращает values из v3)
7. fact_only: только actual, периоды без actual не возвращаются
8. plan_only: actual игнорируется, finetuned побеждает predict
9. compare: все 3 слоя в одной структуре CompareResponseItem
10. DELETE override удаляет ВСЕ finetuned версии (3 PATCH → DELETE → 0 finetuned в БД)
11. DELETE override + GET hybrid → возвращает predict
12. PATCH с scenario из чужого проекта → 400 (бизнес-инвариант)

Тесты создают predict и actual слои напрямую через `db_session.add(PeriodValue(...))`, потому что:
- predict в задаче 1.5 не генерируется автоматически (это задача 2.5)
- endpoint для записи actual в backlog B-02 (импорт из Excel)

Эти решения зафиксированы как осознанные — архитектурная поддержка через `source_type` enum и приоритет в hybrid view готова, само наполнение слоёв — отдельные задачи.

Запуск: `docker compose -f infra/docker-compose.dev.yml exec backend pytest -v` → **57 passed in 10.83s** (8 auth + 12 projects + 14 skus + 11 channels + 12 period_values, 0 warnings).

### Added (задача 1.4 — Channels API + ProjectSKUChannel CRUD)
- **Channels read-only API** (вариант A одобрен — каналы устойчивая бизнес-структура, наполняются seed-скриптом, в MVP не редактируются через UI):
  - `GET /api/channels` — список всех каналов из справочника (25 шт. из GORJI DASH MENU)
  - `GET /api/channels/{id}` — один канал, 404 если не найден
- **ProjectSKUChannel CRUD** (параметры SKU в конкретном канале сбыта):
  - `GET    /api/project-skus/{psk_id}/channels` — список каналов SKU с nested channel
  - `POST   /api/project-skus/{psk_id}/channels` — добавить канал с параметрами (ND target, ramp months, offtake, цены, промо, логистика, опц. seasonality_profile_id)
  - `GET    /api/psk-channels/{id}` — детали с nested channel
  - `PATCH  /api/psk-channels/{id}` — partial update параметров
  - `DELETE /api/psk-channels/{id}` — удалить
- В `ProjectSKUChannel` model добавлен relationship `channel: Mapped[Channel]` с `lazy="raise_on_sql"` (паттерн из 1.3, применён везде по решению пользователя)
- Custom exceptions в service: `ChannelNotFoundError`, `ProjectSKUChannelDuplicateError`. Дубликат `(project_sku_id, channel_id)` ловится через **savepoint pattern** (`async with session.begin_nested()`) — тот же паттерн что в 1.3
- Новые файлы:
  - `backend/app/schemas/{channel.py, project_sku_channel.py}`
  - `backend/app/services/{channel_service.py, project_sku_channel_service.py}`
  - `backend/app/api/{channels.py, project_sku_channels.py}`
  - `backend/tests/api/test_channels.py` — **11 тест-кейсов** (4 channels read-only + 4 ProjectSKUChannel CRUD + 3 edge cases: дубликат, несуществующий канал, требование auth)

**Улучшение тестового инструментария:** `test_engine` fixture в `backend/tests/conftest.py` теперь после `Base.metadata.create_all` сразу прогоняет seed справочников (`Channel`, `RefInflation`, `RefSeasonality`, `Period`) через тестовый engine. Импорт констант идёт из `scripts.seed_reference_data`, единый источник данных. Коммитится один раз на pytest-сессию — каждый тест видит данные через свою (откатываемую) транзакцию. Это нужно для read-only ресурсов вроде Channels (1.4) и для будущей задачи 1.5 PeriodValues (требует 43 периода).

Запуск: `docker compose -f infra/docker-compose.dev.yml exec backend pytest -v` → **45 passed in 8.31s** (8 auth + 12 projects + 14 skus + 11 channels, 0 warnings).

### Added (задача 1.3 — SKU + ProjectSKU + BOM API)
- Три новых ресурса с раздельным CRUD:
  - **Справочник SKU** — `/api/skus` (5 endpoint'ов): не привязан к проекту, переиспользуется между проектами. DELETE с проверкой связей через explicit count → custom `SKUInUseError` → HTTP 409
  - **ProjectSKU** — `/api/projects/{project_id}/skus` (list + create) и `/api/project-skus/{psk_id}` (get/patch/delete). Включение SKU в конкретный проект с rates (production_cost_rate, ca_m_rate, marketing_rate). Дубликат `(project_id, sku_id)` ловится через savepoint + IntegrityError → HTTP 409
  - **BOM** — `/api/project-skus/{psk_id}/bom` (list + create) и `/api/bom-items/{bom_id}` (patch/delete). FK ON DELETE CASCADE: BOM удаляется автоматически вместе с ProjectSKU
- Все endpoint'ы защищены через `get_current_user`
- **COGS preview расчёт** — `GET /api/project-skus/{psk_id}` возвращает `ProjectSKUDetail` с computed полем `cogs_per_unit_estimated = Σ(qty × price × (1 + loss_pct))`. Только на single GET, не на list (избегаем лишнего SQL). Это упрощённая preview-формула для UI; реальная формула COGS из эталонной модели GORJI — в задаче 2.1 расчётного ядра по ADR-CE-01
- В `Project SKU` model добавлен relationship `sku: Mapped[SKU]` с `lazy="raise_on_sql"` — async-safe: запрещает случайные ленивые загрузки, заставляет явно использовать `selectinload(ProjectSKU.sku)`. Без миграции (relationship — Python-уровень)
- Новые файлы:
  - `backend/app/schemas/{sku.py, project_sku.py, bom.py}` — Pydantic схемы
  - `backend/app/services/{sku_service.py, project_sku_service.py, bom_service.py}` — CRUD + COGS preview
  - `backend/app/api/{skus.py, project_skus.py, bom.py}` — три router'а
  - `backend/tests/api/test_skus.py` — **14 тест-кейсов** (5 SKU CRUD + 1 RESTRICT edge case + 4 ProjectSKU + 4 BOM/COGS/CASCADE)
- Обновлены: `entities.py` (ProjectSKU.sku relationship), `services/__init__.py` (re-exports), `main.py` (3 новых router)

**Один technical-debt fix по дороге:** при попытке вставить дубликат `ProjectSKU` IntegrityError ловится внутри `async with session.begin_nested()` (savepoint), а не через простой `session.rollback()`. Без savepoint простой rollback ломал outer transaction в тестах (`SAWarning: transaction already deassociated from connection`). Savepoint pattern — корректный async-паттерн для retry-семантики в SQLAlchemy.

Запуск: `docker compose -f infra/docker-compose.dev.yml exec backend pytest -v` → **34 passed in 6.23s** (8 auth + 12 projects + 14 skus, 0 warnings).

### Added (задача 1.2 — Projects API + soft delete)
- Alembic-миграция `7efc99156f7e_add_project_soft_delete.py` — добавлен `projects.deleted_at TIMESTAMPTZ NULL`
- В `Project` model — `deleted_at: datetime | None` (наследует комментарий о soft delete и отсутствии потери данных)
- `backend/app/schemas/project.py` — `ProjectBase`, `ProjectCreate`, `ProjectUpdate` (все поля Optional, для PATCH), `ProjectRead`, `ProjectListItem` (Read + KPI поля `npv_y1y10`, `irr_y1y10`, `go_no_go` — все `null` пока расчёт не выполнен в Фазе 2)
- `backend/app/services/project_service.py` — `list_projects` (фильтр `deleted_at IS NULL`), `get_project`, `create_project` (создаёт проект + 3 сценария Base/Cons/Aggr в одной транзакции), `update_project` (PATCH через `model_dump(exclude_unset=True)`), `soft_delete_project` (set `deleted_at = now()`)
- `backend/app/api/projects.py` — router `/api/projects` с 5 endpoint'ами:
  - `GET    /api/projects`        → `list[ProjectListItem]`
  - `POST   /api/projects`        → `ProjectRead`, 201, авто-создание 3 сценариев
  - `GET    /api/projects/{id}`   → `ProjectRead`, 404 если deleted
  - `PATCH  /api/projects/{id}`   → `ProjectRead`, partial update
  - `DELETE /api/projects/{id}`   → 204, soft delete (физически не удаляется)
- Все endpoint'ы защищены через `get_current_user` dependency (JWT)
- Подключён в `backend/app/main.py`
- В `tests/conftest.py` добавлены fixtures `test_user` (создаёт юзера в БД) и `auth_client` (HTTPX-клиент с `Authorization: Bearer <jwt>`) — переиспользуется во всех защищённых тестах
- `backend/tests/api/test_projects.py` — **12 тест-кейсов**: создание + auto-scenarios, auth required, validation 422, defaults, list с KPI=null, get by id, 404, PATCH name, PATCH partial, DELETE → 204 + soft delete (физически в БД), GET после delete → 404, list после delete не показывает удалённый
- Замечание о Decimal в JSON: PG `Numeric(8,6)` возвращает `"0.190000"` (трейлинг нули до объявленной точности), Pydantic v2 сохраняет это как есть. Тесты сравнивают через `Decimal()` — семантическое равенство, без хрупкого форматирования. Frontend нормализует отображение в Фазе 3 (вынесено как осознанное решение, не баг)

Запуск: `docker compose -f infra/docker-compose.dev.yml exec backend pytest -v` → **20 passed in 3.77s** (8 auth + 12 projects).

### Added (задача 1.1 — Auth endpoints + первые тесты)
- `backend/app/core/security.py` — bcrypt password hashing + JWT access/refresh encode/decode (HS256, `sub`=user_id как str по RFC 7519, `type`=access|refresh для разделения)
- `backend/app/schemas/{user.py, auth.py}` — Pydantic-схемы: `UserBase`, `UserCreate`, `UserRead`, `Token`, `AccessToken`, `RefreshRequest` (email хранится как `str` без EmailStr — без зависимости `email-validator`)
- `backend/app/services/user_service.py` — `get_user_by_email`, `get_user_by_id`, `create_user`, `authenticate_user`
- `backend/app/api/deps.py` — `oauth2_scheme` (`OAuth2PasswordBearer`) + `get_current_user` dependency: декодирует JWT, проверяет `type=access`, грузит User из БД, поднимает 401 на любом сбое
- `backend/app/api/auth.py` — router `/api/auth/{login, refresh, me}`. Login принимает form data (OAuth2 password flow), refresh — JSON body
- `backend/app/main.py` — подключён auth router
- `backend/pytest.ini` — `asyncio_mode=auto`, обе scope (fixture и test) = `session` (см. ERRORS_AND_ISSUES.md о том, почему это критично)
- `backend/tests/conftest.py` — fixtures: `test_db_url` (создаёт чистую `dbpassport_test` через admin connection к `postgres`), `test_engine` (`create_all` schema, NullPool), `db_session` (connection + transaction + rollback на каждый тест), `client` (HTTPX AsyncClient с подменой `get_db`)
- `backend/tests/api/test_auth.py` — **8 тест-кейсов**, все зелёные:
  1. login success → 200 + access + refresh
  2. login wrong password → 401
  3. login unknown user → 401
  4. /me without token → 401
  5. /me with valid token → 200 + user data (role в JSON = `"analyst"` lowercase ✓)
  6. /me with expired token → 401
  7. /me with garbage token → 401
  8. refresh flow: login → /refresh → /me с новым access
- В `backend/requirements.txt` добавлены: `python-jose[cryptography]>=3.3`, `passlib[bcrypt]>=1.7.4`, `bcrypt>=4.0.0,<4.1.0` (см. ERRORS_AND_ISSUES.md), `python-multipart>=0.0.9`, `pytest>=8.3`, `pytest-asyncio>=0.24`, `httpx>=0.27`

Тесты против реального postgres из compose (вариант, выбранный пользователем; SQLite не подходит из-за JSONB/PG enums). Изоляция через transaction-rollback на каждый тест.

Запуск: `docker compose -f infra/docker-compose.dev.yml exec backend pytest -v` → **8 passed in 1.86s**.

### Added (задача 0.4 — Справочные данные)
- `backend/scripts/__init__.py`, `backend/scripts/seed_reference_data.py` — идемпотентный seed-скрипт для справочников
- Загружено в БД:
  - `periods` — **43 строки**: M1..M36 (помесячно за первые 3 года) + Y4..Y10 (годовые)
  - `channels` — **25 каналов** из листа DASH MENU модели GORJI (HM, SM, MM, TT, Beauty, Beauty-NS, DS_Pyaterochka, DS_Magnit, HDS, ALCO, 5×E-COM, E_COM_E-grocery, 4×HORECA, 4×QSR, VEND_machine, E-COM_OZ_Fresh) с реальными значениями ОКБ
  - `ref_inflation` — **16 профилей**: No_Inflation + 4×"Апрель +N%" (N=4..7) + 4×"Октябрь +N%" + 7×"Апрель/Октябрь +N%" (N=4..10). Структура `month_coefficients` — `{monthly_deltas: [12 элементов янв..дек], yearly_growth: [7 элементов Y4..Y10]}`
  - `ref_seasonality` — **6 профилей**: No_Seasonality, CSD, WTR, EN, TEA, JUI (TEA и JUI в Excel-модели — копии EN). 12 коэффициентов янв..дек, среднее ≈ 1.0
- Все значения захардкожены в скрипт — нет зависимости от наличия xlsx в окружении (требование пользователя)
- Идемпотентность: повторный запуск пропускает существующие записи, проверка по уникальным колонкам (`profile_name` / `code` / `period_number`)

**Расхождение с планом по каналам:** план задачи 0.4 указывал "6 каналов", но в реальной модели GORJI DASH MENU их 25. Использованы все 25 как источник истины (ADR-CE-01). План обновлён.

Запуск: `docker compose -f infra/docker-compose.dev.yml exec backend python -m scripts.seed_reference_data`

### Added (задача 0.3 — Схема базы данных)
- `backend/app/models/base.py` — `Base` (DeclarativeBase), `TimestampMixin`, 5 enums (`ScenarioType`, `SourceType`, `PeriodType`, `PeriodScope`, `UserRole`), helper `varchar_enum()` для VARCHAR + CHECK enums с lowercase значениями
- Naming convention для constraints (`pk_/uq_/fk_/ck_/ix_`) — стабильные имена в миграциях, корректный downgrade
- `backend/app/models/entities.py` — 13 ORM-моделей: `User`, `RefInflation`, `RefSeasonality`, `SKU`, `Channel`, `Period`, `Project`, `Scenario`, `ProjectSKU`, `ProjectSKUChannel`, `BOMItem`, `PeriodValue` (JSONB по ADR-04), `ScenarioResult`. Все денежные/процентные поля — `Numeric` (точность критична для NPV/IRR)
- `backend/app/db/__init__.py` — async SQLAlchemy engine, session factory, FastAPI dependency `get_db()`
- `backend/alembic.ini` + `backend/migrations/env.py` — Alembic с автоподменой `+asyncpg` → `+psycopg` для sync миграций
- `backend/migrations/versions/1c05696e13e6_initial_schema.py` — первая миграция, 14 таблиц (13 моделей + alembic_version), 13 foreign keys, 10 unique constraints
- В `backend/requirements.txt` добавлены: `sqlalchemy[asyncio]>=2.0.36`, `alembic>=1.14`, `asyncpg>=0.30`, `psycopg[binary]>=3.2`
- Backend и celery-worker образы пересобраны с новыми зависимостями (375 MB, +83 MB)

Проверки выполнены против живой БД в compose: `alembic upgrade head` → `\dt` (14 таблиц) → `alembic downgrade -1` → `\dt` (1 таблица alembic_version) → `alembic upgrade head` → `\dt` (14 таблиц).

### Added (задача 0.2 — Docker Compose dev environment)
- `infra/docker-compose.dev.yml` с 5 сервисами: postgres:16-alpine, redis:7-alpine, backend (FastAPI), celery-worker, frontend (Next.js 14)
- `backend/Dockerfile` (dev, python:3.12-slim + uvicorn --reload)
- `backend/requirements.txt` — минимум для 0.2: fastapi, uvicorn[standard], pydantic, pydantic-settings, celery[redis]
- `backend/app/main.py` — FastAPI app с `/health` endpoint и CORS middleware
- `backend/app/core/config.py` — pydantic-settings с загрузкой из env
- `backend/app/worker.py` — минимальное Celery-приложение + task `system.ping` (наполняется в задаче 2.4)
- `frontend/Dockerfile` (dev, node:20-alpine + next dev)
- `frontend/package.json` — Next.js 14.2.15, React 18.3, TypeScript 5.6
- `frontend/app/layout.tsx`, `frontend/app/page.tsx` — минимальная стартовая страница
- `frontend/{tsconfig.json, next.config.mjs, next-env.d.ts, .eslintrc.json}`
- `.gitattributes` с `eol=lf` для всех текстовых файлов и `binary` для xlsx/docx/pdf/pptx — устраняет шум LF↔CRLF между Windows-хостом и Linux-контейнерами
- `backend/.dockerignore`, `frontend/.dockerignore`

### Added (задача 0.1 — инициализация)
- Базовая структура проекта (`backend/`, `frontend/`, `infra/`, `.github/`) согласно ADR-11
- `docs/ADR.md` — 15 архитектурных решений, включая ADR-CE-01..04 (Excel-модель как источник истины для формул расчётного ядра)
- `docs/IMPLEMENTATION_PLAN.md` — план реализации с явно зафиксированным MVP scope и backlog
- `docs/TZ_VS_EXCEL_DISCREPANCIES.md` — 11 расхождений между ТЗ и Excel-моделью, из них 3 критических (D-01 OCF, D-02 VAT, D-03 TAX)
- `docs/ERRORS_AND_ISSUES.md` — журнал проблем и решений
- `CLAUDE.md` — правила работы, стек, раздел "Источник истины для формул"
- `.gitignore`, `.env.example`, `CHANGELOG.md`
- Git-репозиторий инициализирован, первый коммит `chore: init project structure`

### Changed
- Исходные документы переименованы в ASCII-имена для надёжности CI и Docker: `ТЗ Цифровой паспорт проекта V3.docx` → `TZ_Digital_Passport_V3.docx`, `ПАСПОРТ МОДЕЛЬ GORJI+ 05-09-25.xlsx` → `PASSPORT_MODEL_GORJI_2025-09-05.xlsx`, и ещё 3 файла. История git сохранена.
- Удалены устаревшие placeholder-файлы `frontend/.gitkeep` и `infra/.gitkeep` после наполнения директорий.
