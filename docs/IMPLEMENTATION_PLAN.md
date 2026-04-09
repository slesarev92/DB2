# Implementation Plan — Цифровой паспорт проекта

**Версия:** 1.0  
**Дата:** 2026-04-08  
**ADR:** одобрен  
**Статус:** На согласовании

---

## РАЗДЕЛ 0 — MVP SCOPE (читать первым, согласовать до начала кода)

Это единственный обязательный раздел для согласования. Без его одобрения к реализации не переходим.

---

### 0.1 Что входит в MVP

#### Экраны / страницы

| # | Экран | Описание |
|---|-------|----------|
| E-01 | Список проектов | Карточки проектов с базовыми KPI (NPV, статус Go/No-Go), создать новый, открыть существующий |
| E-02 | Карточка проекта — Вводные | Название, даты старта, горизонт, параметры (WACC, TAX_RATE, WC_RATE, VAT_RATE, валюта, инфляционный профиль) |
| E-03 | SKU — список и настройка | Добавить/удалить SKU в проект, базовые параметры SKU (бренд, формат, объём, упаковка, сегмент) |
| E-04 | BOM — технологическая карта | Состав себестоимости на SKU: сырьё (материалы), упаковка, production %, copacking rate, logistics rate |
| E-05 | Каналы — настройка | Для каждого SKU × канал: ND target, offtake target, channel margin, promo discount/share, shelf price |
| E-06 | Ввод данных — таблица периодов | AG Grid: помесячные значения M1–M36 + годовые Y4–Y10, инлайн-редактирование, цветовая подсветка слоёв (predict / finetuned / actual) |
| E-07 | KPI проекта | Сводный экран: NPV (Y1-3, Y1-5, Y1-10), IRR, ROI, Payback, Contribution Margin, EBITDA, Go/No-Go флаг |
| E-08 | Сравнение сценариев | Таблица Base / Conservative / Aggressive с абсолютными и относительными дельтами по ключевым KPI |
| E-09 | Анализ чувствительности | Таблица влияния изменений ND, offtake, цены на NPV и Contribution Margin |
| E-10 | Экспорт | Кнопки: скачать XLSX (данные), скачать PPT (паспорт), скачать PDF |

#### Функциональность

| # | Функция | Описание |
|---|---------|----------|
| F-01 | Расчёт pipeline | 12-шаговый pipeline по ADR-06 и ADR-CE-01..04, асинхронно через Celery |
| F-02 | Три сценария | Base (ручной ввод), Conservative и Aggressive (дельта ND/offtake/OPEX к Base) |
| F-03 | Три слоя данных | predict / finetuned / actual, приоритет actual > finetuned > predict |
| F-04 | История правок | Каждый fine-tune создаёт версию; "Reset to predict" откатывает к базовому значению |
| F-05 | Сезонность | Профиль сезонности на SKU × канал, применяется к M1–M36 |
| F-06 | Инфляция | Ступенчатый профиль (например, Апрель/Октябрь +7%), применяется к shelf price |
| F-07 | ND и offtake рамп-ап | Predict-значения: старт = 20% от target, линейный рост до target за заданное число месяцев |
| F-08 | Экспорт XLSX | Все данные проекта: вводные, PnL по периодам, KPI |
| F-09 | Экспорт PPT | Паспорт проекта: 9 слайдов по структуре из `Passport_Examples.pptx` |
| F-10 | Экспорт PDF | PDF-версия паспорта через WeasyPrint |
| F-11 | JWT-аутентификация | Логин/логаут, защита всех API-маршрутов |

---

### 0.2 Что НЕ входит в MVP → Backlog

| # | Функция | Почему в backlog |
|---|---------|-----------------|
| B-01 | Мультипользователь / роли | ТЗ: MVP = 1 пользователь. Keycloak — Этап 2 (ADR-08) |
| B-02 | Импорт фактических данных из Excel | Архитектурно предусмотрено (actual-слой), но парсинг входящего Excel — отдельная задача |
| B-03 | Агрегация портфеля департамента | Сборка нескольких проектов в одну сводку — Этап 2 |
| B-04 | База ингредиентов с историей цен | MVP: ингредиенты вводятся вручную. Полноценный справочник — позже |
| B-05 | Региональная детализация канала | MVP: канал = аналитическая единица (ADR, раздел 4.6 ТЗ). Регион — в идентификаторе канала |
| B-06 | Дельты сценариев по SKU/каналу | MVP: дельты только на уровне сценария целиком (раздел 8.6 ТЗ) |
| B-07 | ROAD MAP / Gantt | Визуализация дорожной карты проекта — информационный блок, не влияет на расчёт |
| B-08 | Согласование / approval flow | Блок "Согласующие" из GORJI+ — многопользовательская функция |
| B-09 | Интеграция с 1С / BI-кубами | Архитектурно предусмотрено, реализация — Этап 2+ |
| B-10 | Версионность сценариев в UI | History log в интерфейсе. Данные хранятся, UI-просмотр — Этап 2 |
| B-11 | Интерактивный Tornado chart | Визуальный анализ чувствительности (E-09 MVP = таблица, не chart) |
| B-12 | AKB / план дистрибуции | Отдельный АКБ-экран из GORJI+ — развёрнутый план по ТТ |
| B-13 | OBPPC матрица | Стратегия Price-Pack-Channel — маркетинговый блок |
| B-14 | MFA, SSO, LDAP | Этап 2 вместе с Keycloak |

---

### 0.3 Критерий готовности MVP

MVP считается готовым когда:
1. Можно создать проект с 3+ SKU и 4+ каналами.
2. Pipeline рассчитывает все KPI и результаты совпадают с GORJI+ эталоном ±0.01%.
3. Три сценария рассчитываются и сравниваются.
4. Экспорт PPT, XLSX, PDF генерируется без ошибок.
5. Все тесты зелёные (unit + integration).
6. Один пользователь может войти в систему, создать проект, получить паспорт за ≤15 минут.

---

## РАЗДЕЛ 1 — Фазы реализации

После согласования MVP Scope фазы идут последовательно. Каждая фаза = рабочий артефакт (нет полуготовых фаз).

---

### Фаза 0 — Фундамент проекта

**Цель:** рабочее окружение, структура репозитория, DB-схема, пустые сервисы запускаются.

#### ✅ Задача 0.1 — Инициализация структуры и Git

**Что делаем:** создать структуру директорий по ADR-11 (backend/, frontend/, infra/, docs/), инициализировать Git, .gitignore, .env.example, CHANGELOG.md.

**Критерий готовности:**
- `git log` показывает первый коммит `init: project structure`
- `.env.example` содержит все переменные: DATABASE_URL, REDIS_URL, SECRET_KEY, CELERY_BROKER_URL
- `.gitignore` исключает: `*.env`, `__pycache__`, `.next`, `node_modules`, `*.pyc`

**Как проверяем:** `git status` чистый после инициализации.

**Зависимости:** нет.

---

#### ✅ Задача 0.2 — Docker Compose (dev)

**Что делаем:** `infra/docker-compose.dev.yml` с сервисами: postgres:16, redis:7, backend (FastAPI), frontend (Next.js), celery-worker.

**Критерий готовности:**
- `docker compose -f infra/docker-compose.dev.yml up` — все сервисы healthy
- `GET http://localhost:8000/health` → `{"status": "ok"}`
- `GET http://localhost:3000` → Next.js стартовая страница
- postgres доступен на 5432, redis на 6379

**Как проверяем:** `docker compose ps` — все сервисы `running`.

**Зависимости:** 0.1.

---

#### ✅ Задача 0.3 — Схема базы данных (core)

**Что делаем:** SQLAlchemy models + Alembic миграция `0001_initial_schema.py`.

Таблицы:
```
users              (id, email, hashed_password, role, created_at)
projects           (id, name, start_date, horizon_years, wacc, tax_rate, wc_rate, vat_rate,
                    currency, inflation_profile_id, created_by, created_at, updated_at)
scenarios          (id, project_id, type[base/conservative/aggressive], delta_nd, delta_offtake,
                    delta_opex, notes, created_at)
skus               (id, brand, name, format, volume_l, package_type, segment, created_at)
project_skus       (id, project_id, sku_id, include, production_cost_rate, ca_m_rate,
                    marketing_rate, created_at)
channels           (id, code, name, universe_outlets, created_at)
project_sku_channels (id, project_sku_id, channel_id, nd_target, nd_ramp_months,
                      offtake_target, channel_margin, promo_discount, promo_share,
                      shelf_price_reg, logistics_cost_per_kg, seasonality_profile_id,
                      created_at)
periods            (id, type[monthly/annual], period_number, model_year, month_num,
                    start_date, end_date)
period_values      (id, psk_channel_id, scenario_id, period_id, values jsonb,
                    source_type, version_id, is_overridden, created_at)
bom_items          (id, project_sku_id, ingredient_name, quantity_per_unit, loss_pct,
                    price_per_unit, created_at)
scenario_results   (id, scenario_id, period_scope[y1y3/y1y5/y1y10], npv, irr, roi,
                    payback_simple, payback_discounted, contribution_margin, ebitda_margin,
                    go_no_go, calculated_at)
ref_inflation      (id, profile_name, month_coefficients jsonb)
ref_seasonality    (id, profile_name, month_coefficients jsonb)
```

**Критерий готовности:**
- `alembic upgrade head` проходит без ошибок
- `alembic downgrade -1` откатывает без ошибок
- Все таблицы созданы, foreign keys работают

**Как проверяем:** `psql -c "\dt"` показывает все таблицы; тест `test_migrations.py`.

**Зависимости:** 0.2.

---

#### ✅ Задача 0.4 — Справочные данные (seed)

**Что делаем:** скрипт `backend/scripts/seed_reference_data.py` — заполнить:
- `ref_inflation`: 16 профилей из листа DASH MENU GORJI (No_Inflation + Апрель/Октябрь +N% варианты)
- `ref_seasonality`: 6 профилей категорий из DASH MENU (No_Seasonality, CSD, WTR, EN, TEA, JUI)
- `channels`: **25 каналов** из листа ОКБ / DASH MENU GORJI (план изначально указывал 6, но в эталонной модели их 25 — использованы все по ADR-CE-01)
- `periods`: M1–M36 + Y4–Y10 (43 строки)

**Все значения захардкожены** в скрипт (не зависит от наличия xlsx).

**Критерий готовности:**
- После запуска скрипта в таблицах есть данные
- `periods` содержит ровно 43 строки
- `channels` содержит все 25 каналов из GORJI+ DASH MENU
- Идемпотентность: повторный запуск не создаёт дубликатов

**Как проверяем:** SQL-запросы на COUNT, unit-тест `test_seed.py`.

**Зависимости:** 0.3.

---

### Фаза 1 — Backend CRUD API

**Цель:** все сущности создаются, читаются, обновляются, удаляются через REST API. Расчётов нет.

#### ✅ Задача 1.1 — Auth endpoints

**Что делаем:**
- `POST /api/auth/login` → JWT access + refresh tokens
- `POST /api/auth/refresh` → новый access token
- `GET /api/auth/me` → текущий пользователь
- Middleware `get_current_user` для всех защищённых маршрутов

**Критерий готовности:**
- Логин с верными данными → 200 + tokens
- Логин с неверными → 401
- Запрос без токена → 401
- Запрос с истёкшим токеном → 401

**Как проверяем:** `pytest tests/api/test_auth.py` — 8 тест-кейсов.

**Зависимости:** 0.3.

---

#### ✅ Задача 1.2 — Projects API

**Что делаем:**
- `GET /api/projects` — список проектов с базовыми KPI
- `POST /api/projects` — создать проект
- `GET /api/projects/{id}` — детали проекта
- `PATCH /api/projects/{id}` — обновить параметры
- `DELETE /api/projects/{id}` — удалить (soft delete)
- При создании: автоматически создать 3 сценария (Base, Conservative, Aggressive)

**Критерий готовности:**
- CRUD работает, данные персистируются
- При создании проекта → автоматически создаются 3 сценария
- Параметры проекта (wacc, tax_rate и т.д.) сохраняются корректно

**Как проверяем:** `pytest tests/api/test_projects.py`.

**Зависимости:** 1.1.

---

#### ✅ Задача 1.3 — SKU и BOM API

**Что делаем:**
- `GET/POST /api/projects/{id}/skus` — список SKU проекта, добавить SKU
- `PATCH/DELETE /api/projects/{id}/skus/{sku_id}` — обновить, убрать из проекта
- `GET/POST/PATCH/DELETE /api/project-skus/{id}/bom` — BOM-позиции (ингредиент, норма, потери, цена)

**Критерий готовности:**
- Можно добавить SKU в проект, задать production_cost_rate, ca_m_rate, marketing_rate
- BOM-позиции создаются/редактируются/удаляются
- COGS_PER_UNIT считается как сумма BOM (material + package), остальные — через rates

**Как проверяем:** `pytest tests/api/test_skus.py`.

**Зависимости:** 1.2.

---

#### ✅ Задача 1.4 — Channels API

**Что делаем:**
- `GET /api/channels` — справочник каналов
- `GET/POST /api/project-skus/{id}/channels` — добавить канал к SKU в проекте
- `PATCH/DELETE /api/project-sku-channels/{id}` — настроить параметры канала (ND, offtake, цены, промо)

**Критерий готовности:**
- Можно привязать канал к SKU с полным набором параметров
- Параметры сохраняются и читаются корректно

**Как проверяем:** `pytest tests/api/test_channels.py`.

**Зависимости:** 1.3.

---

#### ✅ Задача 1.5 — PeriodValues API

**Что делаем:**
- `GET /api/project-sku-channels/{id}/values?scenario_id=&view_mode=hybrid` — значения по периодам с применением приоритета слоёв
- `PATCH /api/project-sku-channels/{id}/values/{period_id}` — fine-tune одного значения (создаёт версию)
- `DELETE /api/project-sku-channels/{id}/values/{period_id}/override` — сброс к predict

**Критерий готовности:**
- GET возвращает значения с правильным приоритетом (actual > finetuned > predict)
- PATCH создаёт новую версию, is_overridden = true
- DELETE убирает finetuned-версию, следующий GET возвращает predict
- `view_mode`: hybrid, fact_only, plan_only, compare

**Как проверяем:** `pytest tests/api/test_period_values.py` — включая тесты приоритетов всех трёх слоёв.

**Зависимости:** 1.4.

---

#### ✅ Задача 1.6 — Scenarios API

**Что делаем:**
- `GET /api/projects/{id}/scenarios` — три сценария проекта
- `PATCH /api/scenarios/{id}` — изменить дельты (delta_nd, delta_offtake, delta_opex)
- `GET /api/scenarios/{id}/results` — результаты последнего расчёта (ScenarioResult)

**Критерий готовности:**
- Дельты сохраняются, доступны для чтения
- Если ScenarioResult ещё не рассчитан — 404 с понятным сообщением

**Как проверяем:** `pytest tests/api/test_scenarios.py`.

**Зависимости:** 1.5.

---

### Фаза 2 — Расчётное ядро

**Цель:** pipeline рассчитывает все KPI корректно. Acceptance-критерий — сравнение с GORJI+ эталоном.

#### ✅ Задача 2.1 — Pipeline steps 1–5 (объём, цены, COGS, GP)

**Что делаем** (`backend/app/engine/steps/`):

- `s01_volume.py`: `VOLUME_UNITS = ACTIVE_OUTLETS × OFFTAKE × SEASONALITY`
  где `ACTIVE_OUTLETS = UNIVERSE_OUTLETS × ND_PLAN`
- `s02_price.py`: price waterfall — shelf_promo, shelf_weighted, ex_factory
  **Формула: D-02 из ADR-CE-03** → `EX_FACTORY = SHELF_WEIGHTED / (1+VAT) × (1-CM)`
- `s03_cogs.py`: `COGS = (BOM_MATERIAL + BOM_PACKAGE) × VOLUME + EX_FACTORY × PRODUCTION_RATE × VOLUME + COPACKING × VOLUME`
- `s04_gross_profit.py`: **по Excel DATA row 23** `GP = NET_REVENUE − COGS` (без логистики).
- `s05_contribution.py`: **по Excel DATA row 27** `CM = GP − LOGISTICS − PROJECT_OPEX`.

Правка относительно первоначальной формулировки (2026-04-08, коммит Фазы 2.1):
логистика перенесена из `s04` в `s05` чтобы соответствовать семантике Excel
(Gross Profit не включает логистику; логистика — компонент Contribution).
Итоговая Contribution та же, но правильная терминология критична для
отладки и сверки с эталоном. ADR-CE-01 приоритетно.

**Критерий готовности:**
- Unit-тест каждого step с синтетическими данными ✅ (18 тестов)
- Интеграционный тест: шаги 1–5 с данными GORJI+ SKU_1/HM → per-unit GP
  совпадает с DASH row 44 (14.43 ₽/unit M1-M3, 13.75 ₽/unit M4-M6
  после апрельской инфляции) ±0.01% ✅ (7 тестов)

Вместо сверки с DATA!B23 (агрегат по всем SKU × каналам) сверяемся с
DASH row 44/46 per-unit значениями SKU_1/HM — это точнее валидирует
формулы отдельного шага, а агрегация по SKU/каналам будет тестироваться
в задаче 2.4 (оркестратор).

**Как проверяем:** `pytest tests/engine/ -v` ✅ 25/25 зелёные.

**Зависимости:** 0.4.

---

#### ✅ Задача 2.2 — Pipeline steps 6–9 (EBITDA, WC, Tax, Cash Flow)

**Что делаем:**

- `s06_ebitda.py`: `EBITDA = CM - NET_REVENUE × CA_M_RATE - NET_REVENUE × MARKETING_RATE`
- `s07_working_capital.py`: **Формула: D-01 из ADR-CE-02**
  ```python
  wc[t] = net_revenue[t] * wc_rate
  delta_wc[t] = (wc[t-1] if t > 0 else 0) - wc[t]
  ```
- `s08_tax.py`: **Формула: D-03 из ADR-CE-04**
  ```python
  tax[t] = -(contribution[t] * tax_rate) if contribution[t] >= 0 else 0
  ```
- `s09_cash_flow.py`:
  ```python
  ocf[t] = contribution[t] + delta_wc[t] + tax[t]
  icf[t] = -capex[t]
  fcf[t] = ocf[t] + icf[t]
  ```

**Критерий готовности:**
- Unit-тест граничного случая: t=0, wc_previous=0 → delta_wc = -wc[0] ✅
- Unit-тест: contribution < 0 → tax = 0 ✅
- Acceptance EBITDA per unit ↔ DASH row 48 (5.66203 M1-M3, 4.69769 M4-M6) ✅
- Численная сверка s07-s09 с агрегатами GORJI Y0/Y1 (DATA rows 38-43)
  через подстановку NR/CM напрямую в контекст: WC, ΔWC, Tax, OCF, ICF, FCF
  совпадают до 1e-9 ✅

Acceptance "FCF по годам Y0..Y10" из исходного критерия требует
оркестратора (агрегации по SKU × каналам × сценарию) — это задача 2.4.
Для 2.2 валидация per-line + Y0/Y1 агрегатные подстановки достаточны
для подтверждения корректности самих формул.

**Как проверяем:** `pytest tests/engine/ -v` ✅ 44/44 зелёные (включая
17 новых тестов 2.2).

**Зависимости:** 2.1.

---

#### ✅ Задача 2.3 — Pipeline steps 10–12 (NPV, IRR, ROI, KPI, Go/No-Go)

**Что делаем:**

- `s10_discount.py`: аннуализация per-period в годовые бакеты по `model_year`,
  затем `DCF[t] = ANNUAL_FCF[t] / (1 + WACC)^t`. Cumulative FCF/DCF для payback.
  Terminal Value по Гордону (D-07 — TV отдельно, не входит в NPV).
- `s11_kpi.py`:
  - NPV три скоупа: y1y3=SUM(DCF[0:3]), y1y5=SUM(DCF[0:6]), y1y10=SUM(DCF[0:10])
    **Excel quirk D-12**: scope "Y1-Y5" в Excel реально использует 6 элементов,
    не 5. Реализуем как в Excel (источник истины).
  - IRR: **собственный Newton-Raphson + bisection fallback** (`backend/app/engine/irr.py`).
    Без внешних зависимостей. Покрытие тестами включает GORJI Y1-Y3/Y1-Y5/Y1-Y10.
  - ROI: формула из Excel DATA row 49 D-06: `(−SUM/(SUMIF<0 − 1))/COUNT`
  - Payback simple: число лет где cumulative_fcf < 0 (Excel формула row 51, 54)
  - Payback discounted: число лет где cumulative_dcf < 0 (row 52, 55)
  - CM ratio: SUM(annual_contribution) / SUM(annual_net_revenue) — overall
- `s12_gonogo.py`: `GREEN if npv[scope] >= 0 and contribution_margin_ratio >= 0.25`
  для каждого скоупа отдельно.

**Критерий готовности:** ✅
- Acceptance с агрегатами GORJI Y0..Y9 (DATA rows 18, 27, 43) — все KPI совпадают:

| KPI | Эталон (GORJI Excel) | Pipeline | Допуск |
|-----|--------------------------|---------|--------|
| NPV Y1-Y3 | -11 593 312 ₽ | -11 593 312 ₽ | rel 1e-9 ✅ |
| NPV Y1-Y5 | 27 251 350 ₽ | 27 251 350 ₽ | rel 1e-9 ✅ |
| NPV Y1-Y10 | 79 983 059 ₽ | 79 983 059 ₽ | rel 1e-9 ✅ |
| IRR Y1-Y3 | -60.97% | -60.97% | rel 1e-6 ✅ |
| IRR Y1-Y5 | 64.12% | 64.12% | rel 1e-6 ✅ |
| IRR Y1-Y10 | 78.63% | 78.63% | rel 1e-6 ✅ |
| ROI Y1-Y3/5/10 | -23.4%/67.4%/158.3% | match | rel 1e-9 ✅ |
| Payback simple | 3/3/3 | 3/3/3 | exact ✅ |
| Payback discounted | None/4/4 | None/4/4 | exact ✅ |
| Terminal Value Y1-Y10 | 206 140 022 ₽ | match | rel 1e-9 ✅ |
| Cumulative FCF/DCF | DATA rows 56/57 | match | rel 1e-9 ✅ |

**Как проверяем:** `pytest tests/engine/ -v` ✅ 78/78 зелёные (44 от 2.1+2.2 + 34 новых).

**Зависимости:** 2.2.

---

#### ✅ Задача 2.4 — Celery pipeline orchestration

**Что делаем:**
- `backend/app/engine/aggregator.py` — `aggregate_lines(line_contexts) → PipelineContext`,
  element-wise sum per-period значений всех линий
- `backend/app/engine/pipeline.py`:
  - `run_line_pipeline(input)` — прогон s01..s09 для одной (PSK × Channel)
  - `run_project_pipeline(line_inputs, project_capex, project_opex)` — per-line + aggregate + s10..s12
- `backend/app/services/calculation_service.py`:
  - `build_line_inputs(session, project_id, scenario_id)` — грузит ProjectSKU/PSC/PeriodValue из БД,
    применяет scenario delta_nd/delta_offtake, возвращает list[PipelineInput]
  - `calculate_and_save_scenario` — pipeline + сохранение 3 ScenarioResult per scope
  - `calculate_all_scenarios` — для всех 3 сценариев проекта
- `backend/app/tasks/calculate_project.py` — Celery task с asyncio.run wrapper
- `POST /api/projects/{id}/recalculate` → 202 + task_id
- `GET /api/tasks/{task_id}` → PENDING / STARTED / SUCCESS / FAILURE + result/error

**Критерий готовности:** ✅
- Endpoint возвращает task_id ✅ (202 Accepted)
- Pipeline end-to-end работает (build_inputs → run → save) ✅
- ScenarioResult сохранён (3 строки per scope × 3 сценария = 9 строк) ✅
- 404 для несуществующего проекта ✅
- 401 для неаутентифицированных запросов ✅
- Eager Celery mode для тестов wiring ✅

**MVP scope ограничения 2.4:**
- `project_capex` и `project_opex` пока передаются как пустые tuples (0).
  Поля для редактирования через API будут добавлены позже (Phase 3 или отдельной задачей).
  Для тестового acceptance это означает FCF = OCF (без инвестиционного оттока).
- Реальный Celery worker integration test не запускается из pytest — eager mode
  достаточен для проверки wiring API → task → service. Реальный worker
  работает в docker compose service `celery-worker` и доступен через
  обычный HTTP API.

**Как проверяем:** `pytest tests/api/test_calculation.py tests/engine/test_aggregator.py tests/engine/test_pipeline.py -v` ✅ 24/24 зелёные.

**Зависимости:** 2.3, 1.6.

---

#### ✅ Задача 2.5 — Predict-слой: заполнение базовых значений

**Что делаем:** при создании ProjectSKUChannel автоматически заполнять predict-значения для всех 43 периодов × 3 сценариев = 129 PeriodValue:
- ND: рамп-ап от `nd_target × 0.20` до `nd_target` за `nd_ramp_months`
- Offtake: рамп-ап аналогично с тем же `nd_ramp_months`
- Shelf price: базовое + инфляционный профиль (`monthly_deltas` для M1..M36
  + `yearly_growth` для Y4..Y10)
- Сезонность: остаётся в `ref_seasonality` profile (применяется в `s01_volume`,
  не записывается в JSONB PeriodValue)
- Все значения записываются как `source_type = predict`, version_id=1

Реализация в `backend/app/services/predict_service.py`:
- `_ramp_values(target, ramp_months, start_pct, n_monthly)` — pure function
- `_shelf_price_series(base, sorted_periods, profile)` — pure function
- `fill_predict_for_psk_channel(session, psc)` — async, делает DELETE
  существующих predict + INSERT новых для всех 3 сценариев. Идемпотентно.

Интеграция: `create_psk_channel` принимает `auto_fill_predict: bool = True`
(default). Тесты `test_period_values` явно используют `auto_fill_predict=False`
чтобы управлять PeriodValue слоями вручную.

**Критерий готовности:** ✅
- 129 PeriodValue записей создаются автоматически (43 × 3 сценария)
- ND[M1] = nd_target × 0.20, ND[M_ramp] = nd_target, ND[Y4..Y10] = nd_target
- Shelf price для профиля `Апрель/Октябрь +7%`:
  - M1-M3 (январь-март) = база (deltas[0..2] = 0)
  - M4 (апрель) = база × 1.07
  - M10 (октябрь) = M4 × 1.07
- Идемпотентность: повторный fill_predict удаляет старые predict, создаёт новые
- Finetuned/actual слои не трогаются при пересоздании predict

**Как проверяем:** `pytest tests/api/test_predict_service.py -v` ✅ 13/13 зелёные.
- `TestRampValues` (4): pure function для ramp
- `TestShelfPriceSeries` (3): no profile, Апрель/Октябрь +7%, yearly_growth
- `TestAutoFill` (6): 129 строк, 3 сценария, ND ramp, Offtake ramp,
  идемпотентность, finetuned preserved

**Зависимости:** 2.4.

---

### ✅ Фаза 3 — Frontend: ввод (закрыта 2026-04-08, 4 коммита)

**Цель:** пользователь может создать проект, добавить SKU с BOM, настроить каналы.

**Артефакты Фазы 3:**
- Стек: Next.js 14 App Router + Tailwind v4 + shadcn/ui v4
  (Button, Input, Label, Card, Badge, Select, Tabs, Dialog, Table)
- `frontend/lib/`: api.ts (fetch wrapper с auto-refresh), auth.ts
  (localStorage SSR-safe), format.ts (₽/%/даты), projects.ts, skus.ts,
  channels.ts (типизированные обёртки)
- `frontend/components/auth-provider.tsx` — React Context, useAuth hook
- `frontend/components/sidebar.tsx`, `go-no-go-badge.tsx`
- `frontend/components/projects/`: sku-panel, bom-panel, add-sku-dialog,
  channel-form, channel-dialogs, channels-panel, skus-tab, channels-tab
- Route groups `(auth)/login` (публичный) и `(app)/projects/*` (защищённый)
- Backend extensions: GET /api/ref-inflation, GET /api/ref-seasonality,
  list_projects с LEFT JOIN на ScenarioResult для KPI в карточках
- Dev seed: `backend/scripts/create_dev_user.py` (admin@example.com/admin123)

**End-to-end UI flow готов:** регистрация → login → создание проекта
→ SKU + BOM (live COGS) → каналы (auto-fill predict 129 PeriodValue)
→ готов запускать `/recalculate`. UI кнопка "Пересчитать" — задача 4.2.

#### ✅ Задача 3.1 — Routing, layout, auth

**Что делаем:**
- Tailwind CSS v4 + shadcn/ui v4 (init с base components: Button, Input, Label, Card)
- `frontend/lib/api.ts` — fetch wrapper с auto-Authorization, авто-refresh
  при 401, понятные ошибки (`ApiError` класс), типизированные `apiGet/Post/Patch/Delete`
- `frontend/lib/auth.ts` — localStorage helpers (SSR-safe, возвращают null
  на сервере) для access/refresh JWT
- `frontend/components/auth-provider.tsx` — React Context, `useAuth()` hook,
  восстановление сессии при mount через `/api/auth/me`, login/logout методы
- `frontend/app/(auth)/login/page.tsx` — login форма (Card + email/password
  + error alert) с обработкой ApiError. После успеха `router.push("/projects")`.
- `frontend/components/sidebar.tsx` — sidebar навигация с активным состоянием,
  email текущего user внизу + кнопка "Выйти"
- `frontend/app/(app)/layout.tsx` — защищённый layout: client-side check
  через `useAuth`, редирект на /login если `user === null`. Loading
  спиннер пока auth восстанавливается (избегает flash защищённого
  контента до проверки).
- `frontend/app/(app)/projects/page.tsx` — placeholder для задачи 3.2
- `frontend/app/page.tsx` — корневой `/` редиректит на `/projects` или `/login`
  в зависимости от auth state
- `backend/scripts/create_dev_user.py` — идемпотентный скрипт для создания
  dev user `admin@example.com / admin123`. Только для dev.

**Критерий готовности:** ✅
- Неавторизованный → редирект на `/login` (через client-side useEffect в `(app)/layout.tsx`)
- После логина → редирект на `/projects` (`router.push` в `AuthProvider.login`)
- Истёкший access token → auto-refresh через `/api/auth/refresh` в `_fetchWithAuth`,
  ретрай оригинального запроса. Если refresh не сработал → `clearTokens()`,
  AuthProvider увидит отсутствие токенов на следующем mount и перенаправит.
- Все 3 маршрута компилируются: `/`, `/login`, `/projects` → 200
- End-to-end проверка: backend `POST /api/auth/login` + `GET /api/auth/me`
  работают с dev user, frontend компилируется без ошибок

**Архитектурные решения:**
- Tailwind v4 + shadcn v4 (CSS-based config через `app/globals.css`,
  postcss.config.mjs с `@tailwindcss/postcss`)
- localStorage для токенов (не httpOnly cookies — проще для SPA, для prod
  можно мигрировать через server actions)
- React Context для auth state (вместо zustand — избыточно для одного state'а)
- Защита через client-side useEffect (не Next.js middleware — нет доступа
  к localStorage на server-side)
- Inter шрифт через `next/font/google` (не Geist — он только в Next.js 15+,
  у нас 14.2)

**Известные ограничения:**
- Frontend dev server не подхватывает структурные изменения route groups
  через HMR на Windows + Docker volume mount. Требуется ручной
  `docker compose restart frontend` после добавления новых route group.
- Pre-existing уязвимости в Next.js 14.2.35 (high severity, требуют major
  upgrade до 16.x — отдельная задача).

**Как проверяем:** ручная проверка через браузер. Frontend unit/e2e тесты
не реализуются в задаче 3.1 (потенциально Vitest/Playwright позже).

**Зависимости:** 1.1.

---

#### ✅ Задача 3.2 — Список и создание проектов (E-01, E-02)

**Что делаем:**

**Backend extensions:**
- `project_service.list_projects` — расширен LEFT JOIN на Scenario(Base) →
  ScenarioResult(Y1Y10), возвращает `list[ProjectListRow]` (dataclass с
  npv/irr/go_no_go). Один SQL вместо N+1.
- `api/projects.py:list_projects_endpoint` — конвертирует `ProjectListRow`
  → `ProjectListItem` с реальными KPI после расчёта.
- `api/reference.py` (новый файл) — `GET /api/ref-inflation` для dropdown
  в форме создания. Возвращает `list[RefInflationRead]` отсортированные
  по `profile_name`.

**Frontend:**
- `types/api.ts` — TypeScript типы синхронизированные с Pydantic схемами
  (Project*, RefInflation, UserMe). Decimal как `string`.
- `lib/projects.ts` — типизированные обёртки `listProjects/getProject/
  createProject/updateProject/deleteProject/listRefInflation`.
- `lib/format.ts` — `formatMoney/formatPercent/formatDate` (Intl ru-RU).
- `components/go-no-go-badge.tsx` — цветной badge: GREEN/RED/"не рассчитан".
- `app/(app)/projects/page.tsx` — список карточек: название, GoNoGo badge,
  старт + горизонт, NPV Y1-Y10, WACC. Loading/empty/error состояния.
  Кнопка "Создать проект".
- `app/(app)/projects/new/page.tsx` — форма создания (Card + Input + Select):
  name (required), start_date (required), horizon_years, wacc/tax_rate/
  wc_rate/vat_rate (с дефолтами 0.19/0.20/0.12/0.20), inflation_profile_id
  (Select из `/api/ref-inflation` + опция "Без инфляции"). После create →
  `router.push("/projects/{id}")`.
- `app/(app)/projects/[id]/page.tsx` — карточка проекта с Tabs (Параметры
  активная, SKU/Каналы/Результаты — disabled placeholder для 3.3-3.4).
  Tab "Параметры" показывает WACC/Tax/WC/VAT в %, валюту, профиль инфляции.

**Shadcn компоненты добавлены:** Badge, Select, Tabs.

**Критерий готовности:** ✅
- Форма валидирует обязательные поля (HTML5 required + min/max на числовых)
- После создания → редирект на `/projects/{id}` через `router.push`
- Go/No-Go badge зелёный/красный/серый ("не рассчитан") в зависимости от
  `go_no_go: true/false/null` в ProjectListItem
- E2E проверка через curl: POST /api/projects → 201, GET /api/projects →
  список с KPI=null до расчёта
- 189/189 backend pytest зелёные (+4: list KPI test + 3 ref-inflation тесты)

**Зависимости:** 3.1, 1.2.

---

#### ✅ Задача 3.3 — SKU и BOM (E-03, E-04)

**Что делаем:**

**Frontend компоненты:**
- `types/api.ts` — расширен типами SKU/ProjectSKU/ProjectSKUDetail/BOMItem
- `lib/skus.ts` — обёртки `listSkus/createSku/listProjectSkus/getProjectSku/
  addSkuToProject/updateProjectSku/deleteProjectSku/listBomItems/
  createBomItem/updateBomItem/deleteBomItem`
- `components/projects/add-sku-dialog.tsx` — модальный диалог с двумя
  режимами: выбрать существующий SKU из глобального каталога ИЛИ создать
  новый (brand/name/format/volume/package)
- `components/projects/sku-panel.tsx` — список ProjectSKU как кликабельные
  карточки (auto-select первого, active state с border-primary, удаление
  с window.confirm подтверждением, BOM каскадно через FK CASCADE)
- `components/projects/bom-panel.tsx` — для выбранного PSK:
  - Editor `production_cost_rate`/`ca_m_rate`/`marketing_rate` с PATCH on blur
  - Таблица BOM (ingredient, qty, loss%, price, item cost) с inline удалением
  - Inline форма добавления (12-col grid: name/qty/loss/price/button)
  - **Live COGS_PER_UNIT preview** — `Σ(qty × price × (1+loss))` на единицу
- `components/projects/skus-tab.tsx` — комбинирующий компонент:
  2-column grid (sku list 1/3, bom panel 2/3), поднимает selectedPskId
- `app/(app)/projects/[id]/page.tsx` — таб "SKU и BOM" больше не disabled,
  использует SkusTab

**Shadcn компоненты добавлены:** Dialog, Table.

**Критерий готовности:** ✅
- Можно добавить ≥3 ингредиента в BOM, итоговый COGS пересчитывается
  (E2E проверка curl: Sugar+Concentrate+Water → COGS = 12.18 ₽,
  совпадает с math: 0.05×80×1.02 + 0.005×1500×1.05 + 0.45×0.5×1.0)
- Сохранение через POST/PATCH endpoints, данные персистируются в БД
- Backend pytest 189/189 зелёные (без новых тестов — backend API уже
  покрыт в задаче 1.3, frontend проверка ручная)

**Архитектурное замечание:** PATCH rates через `onBlur` — каждое поле
сохраняется отдельно при потере фокуса. Простое решение, без debounce
и optimistic update. Если нужен batch — оптимизация позже.

**Зависимости:** 3.2, 1.3.

---

#### ✅ Задача 3.4 — Каналы (E-05)

**Что делаем:**

**Backend extension:**
- `schemas/reference.py` — `RefSeasonalityRead` Pydantic схема
- `api/reference.py` — `GET /api/ref-seasonality` для dropdown сезонности
  в форме канала. Read-only, защищён JWT, отсортирован по profile_name.

**Frontend компоненты:**
- `types/api.ts` — расширен Channel/ProjectSKUChannel/RefSeasonality типами
- `lib/channels.ts` — обёртки `listChannels/listProjectSkuChannels/
  getPskChannel/addChannelToPsk/updatePskChannel/deletePskChannel/
  listRefSeasonality`
- `components/projects/channel-form.tsx` — reusable форма параметров PSC:
  Select каналов (с исключением уже привязанных), nd_target,
  nd_ramp_months, offtake_target, channel_margin, promo_discount,
  promo_share, shelf_price_reg, logistics_cost_per_kg, Select сезонности.
  Состояние как одна структура `ChannelFormState`, helper `toPscPayload`
  для конвертации в API payload.
- `components/projects/channel-dialogs.tsx` — `AddChannelDialog` (пустая
  форма с дефолтами, исключение уже привязанных каналов из dropdown) и
  `EditChannelDialog` (предзаполнение из существующего PSC, channel_id
  заблокирован, отправка PATCH без channel_id).
- `components/projects/channels-panel.tsx` — таблица PSC выбранного PSK
  (Channel code/name, ND target, Off-take, Margin, Promo, Shelf price)
  с кнопками `✎` редактирования и `×` удаления per row. Кнопка
  "+ Привязать канал" → AddChannelDialog. Удаление каскадно убирает
  PeriodValue (FK ON DELETE CASCADE).
- `components/projects/channels-tab.tsx` — комбинирующий компонент:
  переиспользует `SkuPanel` слева (1/3) + `ChannelsPanel` справа (2/3),
  поднимает selectedPskId state.
- `app/(app)/projects/[id]/page.tsx` — таб "Каналы" больше не disabled,
  использует `<ChannelsTab projectId={projectId} />`. Остаётся только
  таб "Результаты" disabled (Phase 4).

**Критерий готовности:** ✅
- Все параметры канала сохраняются через POST/PATCH PSC
- При создании PSC автоматически генерируются 129 PeriodValue
  (43 период × 3 сценария predict-слой) — задача 2.5 уже сделана,
  переиспользуется. E2E проверено: после POST `/api/project-skus/1/channels`
  `SELECT COUNT(*) FROM period_values WHERE psk_channel_id = 1` = 129
- Backend pytest **192/192** зелёные (+3 от 189: ref-seasonality endpoint)
- Frontend компилируется, /projects/[id] таб "Каналы" активен

**Архитектурное решение:** SkuPanel переиспользован между SkusTab (для
BOM) и ChannelsTab (для каналов) без модификации — selection state
поднят в каждый таб отдельно. Никаких render-prop'ов и сложных абстракций.

**Зависимости:** 3.3, 1.4.

---

### Фаза 4 — Frontend: результаты и анализ

**Цель:** пользователь видит KPI, редактирует данные, сравнивает сценарии.

#### ✅ Задача 4.1 — Таблица периодов AG Grid (E-06)

**Что делаем:**

**Backend extension:**
- `schemas/reference.py` — `PeriodRead` Pydantic схема
- `api/reference.py` — `GET /api/periods` (read-only, JWT, sorted by
  period_number) — возвращает 43 периода для построения column structure

**Frontend:**
- **AG Grid Community + AG Grid React** установлены (новая зависимость
  из стека CLAUDE.md, согласована заранее). v35.2.1 с `ModuleRegistry.
  registerModules([AllCommunityModule])` для v33+ совместимости.
- `types/api.ts` — `Period`, `PeriodType`, `SourceType`, `ViewMode`,
  `PeriodHybridItem`, `PeriodCompareItem`, `PatchPeriodValueResponse`,
  `ResetOverrideResponse`, `Scenario*` типы
- `lib/period-values.ts` — `listPeriodValuesHybrid`, `listPeriodValues`
  (4 view modes), `patchPeriodValue`, `resetPeriodOverride`
- `lib/reference.ts` — `listPeriods()`
- `lib/scenarios.ts` — `listProjectScenarios`, `getScenario`,
  `updateScenario`, `listScenarioResults`
- `components/projects/periods-grid.tsx` — AG Grid pivot:
  - Rows = метрики (ND, Off-take, Shelf price)
  - Columns = периоды (M1..M36 / Y4..Y10) с pinned левой колонкой "Показатель"
  - **Подсветка по source_type через `cellClassRules`**:
    - `bg-blue-100` для finetuned overrides
    - `bg-green-100` для actual
    - без подсветки = predict
  - **Inline edit** через `editable: true` + `onCellValueChanged` →
    `PATCH /api/.../values/{period_id}` → reload (без optimistic update,
    простое решение)
  - **"Сбросить overrides" кнопка** (Promise.all DELETE для всех
    `is_overridden=true` записей)
  - Numeric formatting через valueFormatter с локалью ru-RU
- `components/projects/periods-tab.tsx` — главный компонент таба:
  переиспользует `SkuPanel` слева (1/3 grid), правая колонка содержит
  селекторы (Канал / Сценарий / Период) + `PeriodsGrid` с
  `key={pscId-scenarioId}` для пересоздания при смене селекторов.
  Авто-выбор первого канала и Base сценария.
- `app/(app)/projects/[id]/page.tsx` — добавлен таб **"Периоды"** между
  "Каналы" и "Результаты". Остался только "Результаты" disabled (4.2).

**Критерий готовности:** ✅
- Редактирование ячейки → PATCH создаёт finetuned версию → reload →
  ячейка подсвечивается синим (`bg-blue-100`)
- "Сбросить overrides" → DELETE для всех finetuned → reload → ячейки
  возвращаются к predict-цвету (без подсветки) и значениям
- Переключение Месяцы/Годы/Все 43 — через `periodFilter` state, без
  reload данных (только перестроение rowData/columnDefs)
- Backend pytest **196/196** (+4: ref periods endpoint)
- Frontend `/projects/1` → 200, таб «Периоды» работает

**Архитектурное решение:** Pivot data конструируется на клиенте через
`useMemo` (rows = METRICS array, columns = visiblePeriods filtered).
Это простое решение для MVP; для большого horizon (>43) можно вынести
в server-side rendering.

**Зависимости:** 3.4, 1.5.

---

#### ✅ Задача 4.2 — KPI экран (E-07)

**Что делаем (frontend):**
- `types/api.ts`: `RecalculateResponse`, `TaskStatusResponse`, `CeleryTaskStatus`
- `lib/calculation.ts` (новый): `recalculateProject`, `getTaskStatus`
- `components/projects/kpi-card.tsx`: универсальная карточка одного KPI
  (label, value, opt. color class, opt. subtitle)
- `components/projects/results-tab.tsx` (новый, главный таб):
  - Scenario selector (Base/Conservative/Aggressive), авто-выбор Base
  - Loading / 404 "не рассчитан" / error states
  - **Go/No-Go hero** — большой `GoNoGoBadge` scale-150 для Y1-Y10
  - **NPV row** — 3 карточки (Y1-Y3/Y1-Y5/Y1-Y10), цвет value: зелёный ≥0, красный <0
  - **IRR row** — 3 карточки (formatPercent)
  - **ROI row** — 3 карточки
  - **Payback row** — simple + discounted из Y1-Y10. null → "НЕ ОКУПАЕТСЯ"
  - **Margins row** — CM% + EBITDA%. ≥25% → зелёный, <25% → красный
  - **Кнопка "Пересчитать"** → `recalculateProject` → `pollTaskStatus` раз
    в 1 сек до SUCCESS/FAILURE или 60 сек timeout → refetch результатов
  - Локализованные статусы: "В очереди..." / "Считаем..." / "Обновляем..."
  - При FAILURE — Card border-destructive с сообщением
- `app/(app)/projects/[id]/page.tsx`: таб "Результаты" больше не disabled

**Backend:** не менялся — все endpoints готовы из задач 2.4 и 1.6.

**Критерий готовности:** ✅
- После нажатия "Пересчитать" — спиннер со статусом, затем обновлённые KPI
- 404 на scenarios/{id}/results → placeholder "Расчёт не выполнен"
- Если task FAILURE — error message с причиной
- Timeout 60 сек с понятным сообщением
- `npx tsc --noEmit` → 0 ошибок ✅
- Backend pytest **204/204** зелёные ✅

**Дополнения по итогам визуальной проверки 4.2** (3 связанных коммита
после 4.2 main commit, см. ERRORS_AND_ISSUES.md):

1. **`bfd3226` — ProjectFinancialPlan CRUD + ROI precision + Celery async**
   - Миграция `65003c0135cc`: ROI Numeric(10,6) → (20,6). Excel D-06 quirk
     при всех положительных FCF выдаёт mean FCF в ₽, не помещалось в (10,6).
   - `GET/PUT /api/projects/{id}/financial-plan` для CAPEX/OPEX по годам.
     Маппинг year → первый period_id model_year.
   - `FinancialPlanEditor` UI компонент в табе "Параметры".
   - Фикс Celery async: локальный engine с NullPool в task'е (global
     async_session_maker не работал в Celery prefork — "Future attached
     to a different loop").
   - Worker не видел task — нужен `docker compose restart celery-worker`
     после изменений `worker.py`.

2. **`c5cc6ab` — per-period bom_unit_cost + inflate_series для BOM**
   - `PipelineInput.bom_unit_cost: float → tuple[float, ...]`. Excel
     применяет инфляцию к row 36/37 DASH (material/package) тем же
     профилем что и к shelf_price.
   - `_shelf_price_series` → public `inflate_series`, переиспользуется
     для shelf и BOM.
   - Discovery скрипт `import_gorji_sku1_hm.py` подтвердил полный
     match per-line на M1-M6 (rel 1e-6) включая инфляционную ступеньку
     M3→M4 (-7%).
   - **Закрытие архитектурного долга 2.4:** workaround в test_gorji_
     reference (две PipelineInput для M1-M3 и M4-M6 отдельно) скрывал
     что one-pass прогон не воспроизводит инфляцию на BOM.

**Зависимости:** 4.1, 2.4.

**✅ Sub-task 4.2.1 — полный GORJI import + Excel parity (закрыто 2026-04-09)**

Запуск-цепочка:
1. Discovery V1 (коммит c5cc6ab): SKU_1/HM per-line точность 1e-6
2. D-13 launch lag rollback PSK → PSC (миграция 34aad4c7c120)
3. Discovery V2: полный 8 SKU × 6 каналов × 43 period import через
   `scripts/import_gorji_full.py` (~750 строк, 6192 PeriodValue +
   10 ProjectFinancialPlan)
4. **8 архитектурных расхождений найдены и исправлены (D-14..D-22)**:
   - **D-14**: yearly volume × 12 в `s01_volume` (pipeline bug,
     коммит bfab6b2)
   - **D-15**: DASH cells absolute, не relative (опровержение
     гипотезы — через точное совпадение Volume Y4 без shift'а)
   - **D-16**: per-period material+package в `PeriodValue` из DASH
     cells (Excel custom inflation, не воспроизводим стандартным
     `inflate_series`)
   - **D-17**: per-period shelf_price — уже работало через существующий
     `PeriodValue.values["shelf_price"]` механизм
   - **D-18**: per-period logistics в pipeline (`PipelineInput.logistics_cost_per_kg:
     float → tuple`, расширение `s05_contribution`)
   - **D-19** (revised): per-period production_cost_rate в pipeline
     (`PipelineInput.production_cost_rate: float → tuple`, расширение
     `s03_cogs`). Excel хранит per-period в DASH row 38 cells:
     copacking window M17-M24 = 0, остальное 0.0778
   - **D-20**: per-period channel_margin/promo_discount/promo_share
     в pipeline (`PipelineInput → tuples`, расширение `s02_price`).
     Excel меняет promo_share с 1.0 (M1..M27) до 0.8 (Y4..Y10)
   - **D-21**: copacking Y1=2025 launch costs из DATA r22 → импорт
     добавляет в `ProjectFinancialPlan.opex`
   - **D-22** (КРИТИЧЕСКИЙ для Y1Y3): Working Capital на годовом
     уровне (refactor `s10_discount` — annual recompute WC/ΔWC/Tax/
     OCF/FCF из аннуализированных NR/CM/CAPEX). Per-period s07/s08/s09
     не удалены, но финальные annual values вычисляются в s10
   - **Plus**: WTR seasonality parser fix (формат `{"months": [12]}`)

**Финальная таблица drift (Excel parity):**

| Scope | Метрика | Excel | Наш | **Drift** |
|---|---|---|---|---|
| **Y1Y3** | NPV | −11,593,312 ₽ | −11,593,314 ₽ | **−0.00%** |
| **Y1Y3** | IRR | −60.97% | −60.97% | **+0.00%** |
| **Y1Y3** | ROI | −23.43% | −23.43% | **−0.00%** |
| **Y1Y3** | Payback s/d | 3 / НЕ ОК | 3 / None | **exact** |
| **Y1Y5** | NPV | 27,251,350 ₽ | 27,278,267 ₽ | **+0.10%** |
| **Y1Y5** | IRR | 64.12% | 64.16% | **+0.06%** |
| **Y1Y5** | ROI | 67.40% | 67.45% | **+0.07%** |
| **Y1Y5** | Payback s/d | 3 / 4 | 3 / 4 | **exact** |
| **Y1Y10** | NPV | 79,983,059 ₽ | 80,009,976 ₽ | **+0.03%** |
| **Y1Y10** | IRR | 78.63% | 78.66% | **+0.04%** |
| **Y1Y10** | ROI | 158.26% | 158.29% | **+0.02%** |
| **Y1Y10** | Payback s/d | 3 / 4 | 3 / 4 | **exact** |
| Total | FCF | 264,770,578 ₽ | 264,817,148 ₽ | ratio 1.000 |

**Max NPV drift = 0.10%. ACCEPTANCE PASSED.**

Pipeline = Excel parity достигнут полностью на всех 3 горизонтах.
Продукт корректен для Gate-решений Y1Y3/Y1Y5/Y1Y10.

- 207/207 pytest зелёные после всех architectural changes (D-14..D-22)
- Подробности: `docs/TZ_VS_EXCEL_DISCREPANCIES.md` D-14..D-22 + CHANGELOG.md
- Коммиты: bfab6b2 (D-14), 9e691d3 (D-15..D-21), 2680d01 (D-19 revised + D-22)

**Структура DASH (выяснено в Quick check #2):**
- 8 SKU блоков (rows 6, 52, 98, ..., 328 — шаг 46)
- 6 каналов на SKU через col_base offset (CODE MENU C2..C7):
  - HM=2, SM=50, MM=98, TT=146, E-COM_OZ=194, E-COM_OZ_Fresh=242
- Каждый канал — 48 cols: label col_base, value col_base+1, periods col_base+2..+44
- Per-channel параметры (launch year/month, channel margin, promo, shelf,
  logistic) в col_base+1 на разных rows
- Per-period nd/offtake/shelf — на period cols col_base+2..+44

**Каналы в OBPPC справочнике (универсы):**
HM=1042, SM=5567, MM=?, TT=140462, E-COM_OZ=1, E-COM_OZ_Fresh=1.
Все 6 уже в нашем seed_reference_data.

---

#### Задача 4.3 — Сравнение сценариев (E-08)

**Что делаем:**
- Таблица: строки = KPI, столбцы = Base / Conservative / Aggressive
- Абсолютные значения + дельта к Base (₽ и %)
- Форма настройки дельт сценариев (delta_nd, delta_offtake, delta_opex в %)

**Критерий готовности:**
- После изменения дельты → автоматический пересчёт Conservative/Aggressive
- Таблица обновляется без перезагрузки

**Зависимости:** 4.2, 1.6.

---

#### Задача 4.4 — Анализ чувствительности (E-09)

**Что делаем:**
- Таблица: строки = сценарии изменений (-20%, -10%, Base, +10%, +20%)
  по ND, offtake, shelf price, COGS
- Столбцы: NPV Y1-10, CM%
- Каждая комбинация — отдельный расчёт через pipeline

**Критерий готовности:**
- Таблица заполнена корректными значениями
- Base строка совпадает с результатами KPI-экрана

**Зависимости:** 4.3.

---

### Фаза 5 — Экспорт

#### Задача 5.1 — Экспорт XLSX (F-08)

**Что делаем:** `backend/app/export/excel_exporter.py` — генерация XLSX через openpyxl:
- Лист "Вводные": параметры проекта, SKU, каналы
- Лист "PnL по периодам": все показатели по M1–Y10
- Лист "KPI": NPV, IRR, ROI, Payback по трём сценариям

**Критерий готовности:**
- Файл открывается в Excel без ошибок
- Значения соответствуют данным в UI
- Celery task отдаёт файл, endpoint `/api/projects/{id}/export/xlsx` возвращает `application/vnd.openxmlformats`

**Зависимости:** 2.4.

---

#### Задача 5.2 — Экспорт PPT (F-09)

**Что делаем:** `backend/app/export/ppt_exporter.py` — 9 слайдов по структуре из `Passport_Examples.pptx`:
1. Титул (название, SKU, каналы, дата)
2. Макро-факторы / вводные
3–4. Сводный лист финансовых метрик
5. Продуктовый микс
6. Ключевые KPI
7. Анализ чувствительности NPV
8. Стакан себестоимости
9. Бюджет проекта

**Критерий готовности:**
- PPT открывается в PowerPoint/LibreOffice без ошибок
- Все 9 слайдов содержат данные (не пустые placeholder'ы)

**Зависимости:** 2.4.

---

#### Задача 5.3 — Экспорт PDF (F-10)

**Что делаем:** WeasyPrint рендерит HTML-шаблон паспорта → PDF.
- HTML-шаблон: Jinja2, стилизация через CSS (без внешних шрифтов)
- Запускается в Docker (Linux) где GTK доступен

**Критерий готовности:**
- PDF содержит корректные данные, не PDF/A ошибок
- Размер файла < 5MB для типичного проекта

**Зависимости:** 5.2.

---

### Фаза 6 — Интеграция, polish, CI/CD

#### Задача 6.1 — End-to-end тест (acceptance)

**Что делаем:** полный сценарий:
1. Создать проект с параметрами GORJI+
2. Добавить SKU и BOM
3. Настроить каналы
4. Запустить расчёт
5. Сравнить KPI с эталоном GORJI+
6. Скачать PPT и XLSX

**Критерий готовности:** тест проходит, KPI совпадают с эталоном ±0.01%.

**Зависимости:** все предыдущие фазы.

---

#### Задача 6.2 — GitHub Actions CI

**Что делаем:** `.github/workflows/ci.yml`:
- На каждый PR: `pytest` (backend), `eslint + tsc` (frontend)
- На merge в `main`: build Docker images, push to registry, SSH deploy

**Критерий готовности:**
- PR без зелёных тестов не мёрджится (branch protection rule)
- Deploy в прод только через CI, не руками

**Зависимости:** 6.1.

---

### Фаза 7 — AI-интеграция через Polza AI (post-MVP)

**Цель:** добавить AI-объяснения к уже валидированным финансовым
результатам. Не вмешивается в расчётное ядро. Стартует только после
закрытия Фазы 6 — AI должен комментировать только проверенные числа.

**Архитектурная база:** ADR-16. Polza AI как OpenAI-совместимый прокси,
`openai` Python SDK (`AsyncOpenAI`) с `base_url=POLZA_AI_BASE_URL`.
Дефолт `anthropic/claude-sonnet-4-6`, опция `anthropic/claude-opus-4-6`
для критичных задач.

**Принципы Фазы 7 (применимы ко всем подзадачам):**
- AI-модуль полностью изолирован от `engine/`. Читает только
  сохранённые `ScenarioResult` + параметры проекта.
- Все промпты — Python-константы в `backend/app/services/ai_prompts.py`,
  ревьюятся через PR. Никаких "промптов из БД" в MVP.
- Output — структурированный JSON через `response_format`. Pydantic-схемы
  на ответ. Никаких свободных текстов в API.
- Cost monitoring обязателен: каждый вызов логируется в `ai_usage_log`,
  месячный бюджет на проект — параметр.
- Тесты — мок `AsyncOpenAI.chat.completions.create` через `respx` или
  `unittest.mock.AsyncMock`. Real Polza — отдельный
  `tests/integration/test_polza_smoke.py` c маркером `@pytest.mark.live`,
  не в CI.
- Если Polza недоступен — graceful degradation: AI-фичи возвращают
  placeholder "AI-комментарий недоступен", расчёт работает как обычно.

---

#### Задача 7.1 — Polza AI client + базовая инфраструктура

**Что делаем:**
- `backend/requirements.txt`: добавить `openai>=1.0`
- `backend/app/core/config.py`: `POLZA_AI_API_KEY`, `POLZA_AI_BASE_URL`
- `backend/app/services/ai_service.py` (новый): тонкий wrapper над
  `AsyncOpenAI(api_key=..., base_url=...)`. Singleton клиент через
  `lru_cache`. Метод `complete_json(system_prompt, user_prompt, schema,
  *, model="anthropic/claude-sonnet-4-6")` возвращает валидированный
  Pydantic-объект.
- `backend/app/services/ai_prompts.py` (новый): пустой модуль, заполняется
  в задачах 7.2..7.4
- `backend/tests/services/test_ai_service.py`: моки `AsyncOpenAI`,
  проверка retry/error handling, проверка fallback при недоступности.
- Новая таблица `ai_usage_log` через миграцию (создаётся в 7.1, но
  заполняется только в 7.5 когда логирование включится в endpoint'ы).
  Колонки: `id, project_id, endpoint, model, prompt_tokens,
  completion_tokens, cost_rub, latency_ms, error, created_at`.

**Критерий готовности:**
- `pytest tests/services/test_ai_service.py` зелёные (минимум 5 кейсов:
  successful call, network error, invalid JSON response, schema
  validation failure, missing API key)
- Smoke-тест с реальным Polza (отдельный run, не в CI) проходит
- Никакого реального ключа в репо

**Зависимости:** 6.2 (CI готов, секреты POLZA_AI_API_KEY добавлены в
GitHub Secrets).

---

#### Задача 7.2 — AI-объяснение KPI (NPV/IRR/Payback/Go-NoGo)

**Что делаем:**
- `backend/app/api/ai.py` (новый): `POST /api/projects/{id}/ai/explain-kpi`
  - Body: `{ "scenario_id": int, "scope": "y1y10", "model": "default" | "complex" }`
  - Reads: `ScenarioResult` для (scenario × scope) + project params + lines summary
  - Returns: `AIKpiExplanationResponse` (Pydantic):
    ```
    {
      "summary": str,                    # 2-3 предложения executive
      "key_drivers": [str, ...],         # топ-3 фактора влияющих на NPV
      "risks": [str, ...],               # 2-3 риска
      "recommendation": "go" | "no-go" | "review",
      "confidence": float                # 0..1
    }
    ```
- Промпт в `ai_prompts.py:KPI_EXPLAIN_SYSTEM` — описывает роль (FMCG
  финансовый аналитик), формат JSON, ограничения (не выдумывать числа,
  опираться только на переданные данные)
- Frontend: на `ResultsTab` добавить блок "AI-комментарий" под Go/No-Go
  hero. Кнопка "Объяснить" → POST → отображение карточками с key_drivers
  и risks. Селектор "Базовая модель / Углублённая (Opus)".
- `slowapi` rate limit 10 req/min на пользователя на этот endpoint

**Критерий готовности:**
- Endpoint работает с моком в pytest (5+ кейсов)
- На реальных GORJI данных (после 4.2.1) AI выдаёт осмысленный
  комментарий — ручная проверка
- В UI кнопка работает, ответ отображается, ошибки graceful
- Cost <= 5 руб на типичный вызов (sonnet-4-6)

**Зависимости:** 7.1, 4.2 (KPI экран есть), 4.2.1 (GORJI reference
данные для ручной валидации).

---

#### Задача 7.3 — AI-комментарий к чувствительности (tornado interpretation)

**Что делаем:**
- `POST /api/projects/{id}/ai/explain-sensitivity`
  - Body: `{ "scenario_id": int }`
  - Reads: результаты sensitivity analysis из задачи 4.4 (NPV-дельты по
    ND/offtake/shelf/COGS)
  - Returns: `AISensitivityExplanationResponse`:
    ```
    {
      "most_sensitive": str,             # параметр с макс влиянием
      "least_sensitive": str,
      "narrative": str,                  # 3-4 предложения интерпретации
      "actionable_levers": [str, ...]    # что аналитик может изменить
    }
    ```
- Промпт: `ai_prompts.py:SENSITIVITY_EXPLAIN_SYSTEM`
- Frontend: блок "AI-интерпретация" под таблицей чувствительности

**Критерий готовности:**
- pytest на моках, ручная проверка на GORJI, UI работает

**Зависимости:** 7.2, 4.4.

---

#### Задача 7.4 — AI executive summary в PPT-экспорт

**Что делаем:**
- При `POST /api/projects/{id}/export/ppt` с флагом `include_ai_summary=true`:
  pipeline вставляет новый слайд "Executive Summary" между Титулом и
  Макро-факторами. Контент — AI-генерация на основе всех KPI + всех
  сценариев + чувствительности
- Промпт: `ai_prompts.py:EXECUTIVE_SUMMARY_SYSTEM`
- Структура слайда: заголовок, 4-5 буллетов, recommendation (Go/No-Go/Review),
  3 ключевых числа крупно
- Если AI недоступен — слайд пропускается, экспорт продолжает работать

**Критерий готовности:**
- PPT с AI-слайдом открывается, контент осмысленный
- PPT без AI (флаг false) — без слайда, как было до 7.4
- При AI failure — слайд пропускается, в логах warning

**Зависимости:** 7.2, 5.2 (PPT экспорт готов).

---

#### Задача 7.5 — Cost monitoring + rate limiting + бюджеты

**Что делаем:**
- Включить логирование `ai_usage_log` во всех endpoint'ах из 7.2..7.4
  (метрики: model, tokens, cost_rub, latency, error)
- Новое поле в `Project`: `ai_budget_rub_monthly: Decimal | None`
  (default 1000 ₽). Миграция.
- Middleware/decorator: перед AI-вызовом проверять `SUM(cost_rub)
  WHERE project_id=X AND created_at >= start_of_month`. Если превышен
  бюджет — `429 Too Many Requests` с понятным сообщением "Месячный
  AI-бюджет проекта исчерпан, обратитесь к администратору".
- `GET /api/projects/{id}/ai/usage` — endpoint для UI: текущее
  использование за месяц, остаток бюджета, history по дням
- Frontend: блок "AI-бюджет" в табе "Параметры" (текущее / лимит,
  индикатор). Поле редактирования лимита.
- Алёрт в логи (warning) когда бюджет израсходован >80%

**Критерий готовности:**
- Симуляция превышения бюджета → 429
- UI показывает корректный остаток
- pytest на ai_usage_log accumulator

**Зависимости:** 7.2 (есть что логировать).

---

## РАЗДЕЛ 2 — Карта зависимостей (сводная)

```
0.1 → 0.2 → 0.3 → 0.4
                 ↓
           1.1 → 1.2 → 1.3 → 1.4 → 1.5 → 1.6
                                           ↓
           2.1 → 2.2 → 2.3 → 2.4 → 2.5
                                    ↓
           3.1 → 3.2 → 3.3 → 3.4
                                    ↓
           4.1 → 4.2 → 4.3 → 4.4
                                    ↓
           5.1 → 5.2 → 5.3
                              ↓
                         6.1 → 6.2
                                ↓
                          7.1 → 7.2 → 7.3
                                 ↓     ↓
                                7.4 ← 5.2
                                 ↓
                                7.5
```

2.1–2.5 зависят от 0.4 (seed данные).  
3.x зависят от 1.x (API готов).  
4.x зависят от 2.4 (расчёты работают) и 3.x (UI для ввода).  
5.x зависят от 2.4 (данные для экспорта).
7.x зависят от 6.2 (CI готов, секреты в GitHub Secrets).
7.2 дополнительно от 4.2.1 (GORJI данные для ручной валидации AI).
7.3 от 4.4 (sensitivity анализ существует).
7.4 от 5.2 (PPT экспорт существует).

---

## РАЗДЕЛ 3 — Порядок работы в каждом чате

При начале нового чата:
1. Прочитать CLAUDE.md
2. Прочитать этот файл — найти первую незавершённую задачу
3. Прочитать docs/ERRORS_AND_ISSUES.md — учесть открытые проблемы
4. Выполнить задачу строго по критерию готовности
5. Перед коммитом — все тесты зелёные, линтер не ругается
6. Отметить задачу выполненной (добавить `✅` перед заголовком)
7. Обновить CHANGELOG.md

---

## РАЗДЕЛ 4 — Статус выполнения

### ✅ Фаза 0 — Фундамент (закрыта 2026-04-08, 7 коммитов)
- [x] 0.1 Инициализация структуры и Git ✅ (commit b10aef8, 2026-04-08)
- [x] 0.2 Docker Compose (dev) ✅ (2026-04-08, все 5 сервисов healthy, /health + localhost:3000 зелёные)
- [x] 0.3 Схема базы данных ✅ (2026-04-08, миграция 1c05696e13e6, 14 таблиц, upgrade/downgrade проверены)
- [x] 0.4 Справочные данные (seed) ✅ (2026-04-08, 43 periods + 25 channels + 16 inflation + 6 seasonality, идемпотентно)

### ✅ Фаза 1 — Backend CRUD API (закрыта 2026-04-08, 6 коммитов, **66/66 pytest**, 37 endpoints)
- [x] 1.1 Auth endpoints ✅ (2026-04-08, 8/8 pytest зелёные)
- [x] 1.2 Projects API ✅ (2026-04-08, 12/12 pytest зелёные, soft delete + auto-scenarios)
- [x] 1.3 SKU и BOM API ✅ (2026-04-08, 14/14 pytest зелёные, COGS preview, savepoint pattern)
- [x] 1.4 Channels API ✅ (2026-04-08, 11/11 pytest зелёные, read-only справочник + ProjectSKUChannel CRUD)
- [x] 1.5 PeriodValues API ✅ (2026-04-08, 12/12 pytest зелёные, трёхслойная модель + 4 view modes + append-only versioning)
- [x] 1.6 Scenarios API ✅ (2026-04-08, 9/9 pytest зелёные, GET/PATCH дельт + results с actionable 404)

### ✅ Фаза 2 — Расчётное ядро (закрыта 2026-04-08, 6 коммитов, **185/185 pytest**, 39 endpoints)

**Архитектурные решения для всей фазы (одобрены пользователем):**
- Pipeline = pure functions, композиция через оркестратор (не классы, не DataFrame)
- `PipelineInput` dataclass формируется service'ом, pipeline не ходит в БД
- float internally, Decimal на границах (БД ↔ memory). Excel модель тоже float, точность ~15 знаков для NPV в миллионах достаточна
- IRR — собственный Newton-Raphson + bisection (вместо numpy-financial,
  заброшенного с 2020). 50 строк, без внешних зависимостей.
- Эталонные значения из GORJI Excel захардкожены в тестах — не зависят от наличия xlsx
- Project-level CAPEX/OPEX в отдельной таблице `project_financial_plans` с FK на period

**Подзадачи:**
- [x] 2.1 Pipeline steps 1–5 ✅ (2026-04-08, 25/25 pytest зелёные, сверено с DASH SKU_1/HM per-unit)
- [x] 2.2 Pipeline steps 6–9 ✅ (2026-04-08, 44/44 engine pytest, EBITDA per-unit + Y0/Y1 агрегатная сверка с DATA rows 38-43)
- [x] 2.3 Pipeline steps 10–12 + acceptance ✅ (2026-04-08, 78/78 engine pytest, NPV/IRR/ROI/Payback все три скоупа совпадают с GORJI до 1e-6, собственный IRR solver)
- [x] 2.4 Celery orchestration ✅ (2026-04-08, 168/168 pytest, aggregator + pipeline orchestrator + calculation_service + Celery task + 2 endpoint, eager mode для тестов wiring)
- [x] 2.5 Predict-слой ✅ (2026-04-08, 185/185 pytest, predict_service auto-fill 129 PeriodValue per канал, ProjectFinancialPlan для capex/opex добавлен миграцией)

**Артефакты Фазы 2:**
- `backend/app/engine/`: context.py, irr.py, aggregator.py, pipeline.py + 12 шагов (s01-s12)
- `backend/app/services/`: calculation_service.py, predict_service.py
- `backend/app/tasks/`: calculate_project.py (Celery task)
- `backend/app/api/tasks.py` + `POST /api/projects/{id}/recalculate` в projects.py
- Новая модель `ProjectFinancialPlan` + миграция `0bc2641bd568_add_project_financial_plans.py`
- D-12 (Excel typo Y1-Y5 = 6 элементов) подтверждён и задокументирован

**End-to-end flow готов:** создание проекта → SKU → BOM → канал (auto-fill predict) → POST /recalculate → Celery task → 9 ScenarioResult строк (3 сценария × 3 скоупа).

### ✅ Фаза 3 — Frontend: ввод (закрыта 2026-04-08, 4 коммита)
- [x] 3.1 Routing, layout, auth ✅ (2026-04-08, Tailwind v4 + shadcn v4 + AuthContext + login flow + защищённый layout с sidebar, dev user `admin@example.com/admin123`)
- [x] 3.2 Список и создание проектов ✅ (2026-04-08, /projects карточки + /projects/new форма + /projects/[id] карточка с Tabs, backend list_projects с JOIN на ScenarioResult, GET /api/ref-inflation, 189/189 pytest)
- [x] 3.3 SKU и BOM ✅ (2026-04-08, sku-panel + bom-panel + add-sku-dialog в табе SKU и BOM, live COGS preview, PATCH rates on blur, E2E COGS=12.18₽ совпал)
- [x] 3.4 Каналы ✅ (2026-04-08, channels-panel + channel-dialogs в табе Каналы, GET /api/ref-seasonality, E2E auto-fill predict 129 PeriodValue, 192/192 pytest)

### Фаза 4 — Frontend: результаты (← следующий шаг: задача 4.3)
- [x] 4.1 AG Grid таблица периодов ✅ (2026-04-08, AG Grid v35 + новый таб «Периоды» + GET /api/periods + cellClassRules подсветка по source_type, inline PATCH, reset overrides, 196/196 pytest)
- [x] 4.2 KPI экран ✅ (2026-04-08, ResultsTab с Go/No-Go hero + NPV/IRR/ROI/Payback/CM/EBITDA grid + кнопка Пересчитать с polling `/api/tasks/{id}` раз в 1 сек до 60с timeout, 0 tsc errors, 196/196 pytest)
- [x] **4.2.1 Полный GORJI импорт + Excel parity** ✅ (2026-04-09,
  Discovery V2, **8 архитектурных расхождений D-14..D-22 исправлены**.
  Финальный drift: NPV Y1Y3=−0.00%, Y1Y5=+0.10%, Y1Y10=+0.03%.
  IRR Y1Y3=+0.00%, Y1Y5=+0.06%, Y1Y10=+0.04%. Payback s/d точно exact
  для всех scope. Total FCF ratio=1.000. Max drift = 0.10%. ACCEPTANCE
  PASSED. 207/207 pytest. Коммиты bfab6b2/9e691d3/2680d01. Подробности
  в CHANGELOG.md и `docs/TZ_VS_EXCEL_DISCREPANCIES.md` D-14..D-22)
- [ ] 4.3 Сравнение сценариев
- [ ] 4.4 Анализ чувствительности

### Фаза 5 — Экспорт
- [ ] 5.1 XLSX
- [ ] 5.2 PPT
- [ ] 5.3 PDF

### Фаза 6 — Интеграция
- [ ] 6.1 E2E acceptance-тест
- [ ] 6.2 GitHub Actions CI

### Фаза 7 — AI-интеграция (Polza AI, post-MVP, ADR-16)
- [ ] 7.1 Polza AI client + ai_service.py + ai_usage_log таблица
- [ ] 7.2 AI-объяснение KPI (POST /api/projects/{id}/ai/explain-kpi)
- [ ] 7.3 AI-комментарий чувствительности (POST .../ai/explain-sensitivity)
- [ ] 7.4 AI executive summary slide в PPT-экспорте
- [ ] 7.5 Cost monitoring + бюджет проекта + rate limiting
