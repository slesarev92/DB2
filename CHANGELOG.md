# Changelog

Все заметные изменения проекта фиксируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
проект следует [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

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
