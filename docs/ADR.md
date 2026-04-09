# Architecture Decision Record — Цифровой паспорт проекта

**Версия:** 1.0  
**Дата:** 2026-04-08  
**Статус:** На согласовании  
**Автор:** Claude (senior full-stack, роль по CLAUDE.md)

---

## Содержание

- [ADR-01 Backend-стек](#adr-01-backend-стек)
- [ADR-02 Frontend-стек](#adr-02-frontend-стек)
- [ADR-03 База данных](#adr-03-база-данных)
- [ADR-04 Хранение PeriodValue](#adr-04-хранение-periodvalue)
- [ADR-05 Трёхслойная модель данных](#adr-05-трёхслойная-модель-данных)
- [ADR-06 Расчётное ядро — архитектура](#adr-06-расчётное-ядро--архитектура)
- [ADR-CE-01 Источник истины для формул](#adr-ce-01-источник-истины-для-формул)
- [ADR-CE-02 Формула Operating Cash Flow (D-01)](#adr-ce-02-формула-operating-cash-flow-d-01)
- [ADR-CE-03 VAT-стрипинг в ex-factory цене (D-02)](#adr-ce-03-vat-стрипинг-в-ex-factory-цене-d-02)
- [ADR-CE-04 База налога на прибыль (D-03)](#adr-ce-04-база-налога-на-прибыль-d-03)
- [ADR-07 Асинхронный пересчёт](#adr-07-асинхронный-пересчёт)
- [ADR-08 Аутентификация в MVP](#adr-08-аутентификация-в-mvp)
- [ADR-09 Экспорт документов](#adr-09-экспорт-документов)
- [ADR-10 Таблицы на фронте](#adr-10-таблицы-на-фронте)
- [ADR-11 Инфраструктура и окружения](#adr-11-инфраструктура-и-окружения)
- [ADR-16 AI-интеграция через Polza AI (Фаза 7)](#adr-16-ai-интеграция-через-polza-ai-фаза-7)

> **Примечание о нумерации:** ADR-12..15 пропущены умышленно (зарезервировано
> под будущие архитектурные решения вне scope MVP). ADR-16 создан под
> AI-интеграцию по согласованию с пользователем.

---

## ADR-01 Backend-стек

### Контекст
Нужен backend для расчётного ядра с ~12-шаговым pipeline, хранения финансовых моделей и генерации документов. Вычислительная нагрузка умеренная: одна сессия пересчёта ≤ 50 SKU × 6 каналов × 43 периода ≈ 13 000 ячеек, каждая — несколько арифметических операций.

### Решение
**Python 3.12 + FastAPI + SQLAlchemy 2.x + Alembic**

### Обоснование
- Python — единственный язык с полноценным финансовым ecosystem: numpy для векторных расчётов, numpy_financial для IRR/NPV/Payback, pandas для агрегаций. Переписывать финансовые функции на других языках — риск ошибок.
- FastAPI: async, автогенерация OpenAPI, Pydantic v2 для валидации. Производительность достаточна — bottleneck здесь не I/O, а CPU расчётного ядра (которое будет вынесено в Celery).
- SQLAlchemy 2.x: поддержка async sessions, явная типизация через mapped_column, надёжная ORM с 15-летней историей.
- Alembic: единственный зрелый инструмент миграций для SQLAlchemy.

### Альтернативы
- **Node.js + TypeScript:** нет numpy_financial, IRR и NPV нужно писать самим и тестировать. Отклонено.
- **Go:** нет экосистемы финансовых вычислений вообще. Отклонено.
- **Django + DRF:** тяжелее FastAPI, Django ORM хуже SQLAlchemy для сложных запросов. Отклонено.

### Последствия
- Зависимость от Python GIL снята через Celery (расчёты в отдельных процессах).
- Тесты расчётного ядра пишутся как чистые unit-тесты (pure functions, без HTTP).

---

## ADR-02 Frontend-стек

### Контекст
Интерфейс — финансовые таблицы с инлайн-редактированием, графики, экспорт. Основной паттерн использования: desktop-браузер, одна активная сессия (MVP — один пользователь).

### Решение
**Next.js 14 App Router + TypeScript + Tailwind CSS + shadcn/ui**

### Обоснование
- Next.js App Router: Server Components для страниц с тяжёлой начальной загрузкой данных (паспорт проекта); Client Components только там где нужна интерактивность (grid, forms). Это позволяет держать JS-бандл маленьким.
- TypeScript: финансовые типы должны быть строгими. `Contribution` не может случайно стать `string`.
- Tailwind: нет design-system с нуля — shadcn/ui даёт готовые компоненты на Tailwind.
- shadcn/ui: компоненты копируются в репо (не npm-зависимость), кастомизируются без ограничений.

### Альтернативы
- **Vite + React SPA:** нет SSR, но для одного пользователя это некритично. Однако App Router лучше структурирует routing + data fetching. Не отклонено полностью — если возникнет проблема с App Router, переход к SPA возможен без смены стека.
- **Vue 3:** меньше TypeScript-экосистемы, меньше компонентных библиотек для финансовых таблиц. Отклонено.

### Последствия
- Server Actions использовать только для простых мутаций. Расчёты всегда через REST API (не Server Actions) — иначе теряем контроль над таймаутами.
- Все финансовые типы определяются в `frontend/types/` и генерируются из OpenAPI схемы backend.

---

## ADR-03 База данных

### Контекст
Нужно хранить: проекты, сценарии, версии, SKU, каналы, периодические значения с историей изменений и метаданными слоёв (predict/finetuned/actual). Плюс справочники: каналы, сезонность, инфляция, BOM.

### Решение
**PostgreSQL 16**

### Обоснование
- JSONB: нужен для хранения PeriodValue (см. ADR-04). PostgreSQL — единственная RDBMS с production-grade JSONB и GIN-индексами.
- ACID: финансовые данные. Eventual consistency недопустима.
- Зрелость: 30+ лет, используется в банках и ERP. Нет вопросов к надёжности.
- Алembic+SQLAlchemy работают нативно с PostgreSQL.

### Альтернативы
- **MySQL 8:** JSONB слабее, меньше аналитических функций (window functions менее мощные). Отклонено.
- **SQLite:** однопользовательский MVP мог бы работать, но нет JSONB, нет конкурентного доступа, нет горизонтального масштабирования. Отклонено.
- **TimescaleDB:** для временных рядов, но избыточно — у нас максимум 43 точки на один SKU×канал×сценарий. Отклонено.

### Последствия
- Миграции только через Alembic. Прямые ALTER TABLE в prod запрещены.
- Версия PostgreSQL фиксирована в docker-compose как `postgres:16-alpine`.

---

## ADR-04 Хранение PeriodValue

### Контекст
Ключевая структура данных: набор показателей за каждый период (M1–M36, Y4–Y10) для каждой тройки (ProjectSKU × Channel × Scenario). Варианты хранения принципиально разные по производительности и гибкости.

**Объём:** 1 проект × 3 сценария × 10 SKU × 6 каналов × 43 периода = 7 740 "ячеек". Каждая ячейка — ~50 показателей. Итого ~387 000 значений. С историей версий × 5 (в среднем) = ~2M строк на активный проект при EAV.

### Решение
**Одна строка на (project_sku_channel_id, scenario_id, period_id) с JSONB-колонкой `values`**

Схема:
```sql
period_value (
    id              uuid PRIMARY KEY,
    psk_channel_id  uuid NOT NULL REFERENCES project_sku_channels(id),
    scenario_id     uuid NOT NULL REFERENCES scenarios(id),
    period_id       uuid NOT NULL REFERENCES periods(id),
    values          jsonb NOT NULL,          -- все показатели периода
    source_type     source_type_enum,        -- predict | finetuned | actual | scenario_adjusted
    version_id      integer NOT NULL DEFAULT 1,
    is_overridden   boolean NOT NULL DEFAULT false,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (psk_channel_id, scenario_id, period_id, version_id)
)
```

JSONB содержит поля из Data Dictionary: `nd_plan`, `offtake_plan`, `shelf_price_reg`, `volume_units`, `net_revenue`, `cogs_total`, и т.д.

### Обоснование
- **EAV (строка на каждый показатель):** 50 показателей × 7740 ячеек = 387 000 строк на слой, плюс история. Агрегация одного проекта = JOIN на 387 000 строк. Антипаттерн.
- **JSONB с одной строкой на период:** 7 740 строк. Агрегация = 7 740 строк. Чтение всего проекта за один SELECT.
- **Отдельные колонки (wide table):** ~50 колонок × не расширяемо при добавлении показателей. Каждое новое поле = миграция.
- GIN-индекс по `values` позволяет фильтровать по содержимому JSONB.
- При необходимости конкретный показатель индексируется: `CREATE INDEX ON period_value ((values->>'nd_plan'));`

### Альтернативы
- **EAV:** отклонено (производительность, читаемость SQL).
- **Wide columnar table:** отклонено (жёсткость схемы).
- **TimescaleDB hypertable:** избыточно при 43 точках. Отклонено.

### Последствия
- Валидация структуры JSONB — на уровне Pydantic при записи (не в БД).
- History хранится как insert новой версии с инкрементом `version_id`. Текущая версия = MAX(version_id) для каждой комбинации (psk_channel_id, scenario_id, period_id).
- "Reset to predict" = soft-delete текущей версии (is_overridden = false) без удаления данных.

---

## ADR-05 Трёхслойная модель данных

### Контекст
Система должна поддерживать три источника значений с приоритетом `actual > finetuned > predict` и возможностью отката. Это архитектурное ядро — от него зависит всё поведение UI и расчётного ядра.

### Решение
**Три источника как значения `source_type` в одной таблице `period_value`, приоритет применяется в слое сервиса**

Логика выборки (Python, слой сервиса):
```python
def get_effective_value(psk_channel_id, scenario_id, period_id, field: str) -> Decimal:
    actual    = get_latest(source_type='actual', ...)
    finetuned = get_latest(source_type='finetuned', ...)
    predict   = get_latest(source_type='predict', ...)

    if actual and actual.values.get(field) is not None:
        return actual.values[field]
    if finetuned and finetuned.values.get(field) is not None:
        return finetuned.values[field]
    return predict.values[field]
```

Сценарные значения (Conservative/Aggressive) — не отдельный source_type, а дельта-применение к Base на лету в pipeline (не хранятся как отдельные записи, кроме ScenarioResult).

### Обоснование
- Хранение в одной таблице с `source_type` даёт полный audit trail без разнесения по разным таблицам.
- Логика приоритета в сервисе — не в БД — позволяет тестировать изолированно.
- ScenarioResult (Conservative/Aggressive KPI) — кешируется как отдельная сущность, пересчитывается при изменении Base.

### Последствия
- Каждый запрос к значению требует чтения до 3 строк (actual, finetuned, predict). Кешируется в Redis на время сессии.
- History: при каждом fine-tune создаётся новая строка с `version_id+1`. Старые версии не удаляются.

---

## ADR-06 Расчётное ядро — архитектура

### Контекст
Pipeline из 12+ шагов (раздел 7.6 ТЗ) должен выполняться строго последовательно, на бэкенде, с фиксированным порядком. Входные данные — эффективные значения всех PeriodValue с применением приоритета источников.

### Решение
**Чистый Python-модуль `backend/app/engine/` без side effects, вызываемый асинхронно через Celery**

Структура:
```
engine/
├── pipeline.py        # оркестратор: запускает шаги по порядку
├── steps/
│   ├── s01_volume.py
│   ├── s02_price.py
│   ├── s03_cogs.py
│   ├── s04_gross_profit.py
│   ├── s05_contribution.py
│   ├── s06_ebitda.py
│   ├── s07_working_capital.py
│   ├── s08_tax.py
│   ├── s09_cash_flow.py
│   ├── s10_discount.py
│   ├── s11_kpi.py       # NPV, IRR, ROI, Payback
│   └── s12_gonogo.py
└── context.py         # dataclass с промежуточными результатами
```

Каждый step — **чистая функция**: `def step(ctx: PipelineContext) -> PipelineContext`. Нет глобального состояния, нет обращений к БД внутри step. Данные загружаются до вызова pipeline, результаты записываются после.

### Обоснование
- Чистые функции тестируются без БД, без HTTP — unit-тест за миллисекунды.
- Фиксированный порядок шагов исключает зависимостные ошибки.
- Celery изолирует долгие расчёты от HTTP-воркеров (нет таймаутов).

### Последствия
- Изменение любой формулы в step требует теста, сравнивающего с эталонными числами GORJI+.
- Шаги нумерованы — добавление нового шага только в конец или с явным обоснованием.

---

## ADR-CE-01 Источник истины для формул расчётного ядра

### Контекст
В процессе верификации (документ `docs/TZ_VS_EXCEL_DISCREPANCIES.md`) выявлены расхождения между ТЗ и рабочей Excel-моделью `PASSPORT_MODEL_GORJI_2025-09-05.xlsx`. Excel-модель используется в production и даёт корректные результаты — её цифры (NPV, IRR, ROI, Payback) проверены бизнесом.

### Решение
**Excel-модель `PASSPORT_MODEL_GORJI_2025-09-05.xlsx` является единственным источником истины для всех финансовых формул расчётного ядра.**

При любом расхождении между ТЗ и Excel-моделью — реализуется формула из Excel.

ТЗ является источником истины для:
- Структуры сущностей (Project, Scenario, Version, ProjectSKU, ProjectSKUChannel, PeriodValue)
- UI/UX требований
- Ролевой модели и прав доступа
- Требований к экспорту

ТЗ **не является** источником истины для математических формул там, где Excel-модель противоречит ему.

### Обоснование
- ТЗ писался как спецификация намерений, Excel-модель — как рабочий инструмент с реальными данными. Расхождения возникли из-за упрощений при написании ТЗ.
- Бизнес-пользователь валидирует числа по Excel, не по ТЗ.
- Три критических расхождения (D-01, D-02, D-03) дают погрешность до 15% в NPV при 5-летнем горизонте.

### Последствия
- Каждый step расчётного ядра содержит комментарий с ссылкой на лист и строку Excel-модели.
- Финальный acceptance-тест: ввести данные GORJI+ → получить KPI ± 0.01% от эталона.
- При обновлении Excel-модели — повторить верификацию и обновить этот ADR.

---

## ADR-CE-02 Формула Operating Cash Flow (D-01)

### Контекст
ТЗ (раздел 7.5.5) задаёт формулу OCF как:
```
OPERATING_CASH_FLOW = CONTRIBUTION × (1 − 0.12) − PROFIT_TAX
```
Верификация против Excel-модели (лист DATA, строки 38–41) показала: эта формула математически неверна — она не учитывает, что оборотный капитал замораживается один раз при росте выручки, а не удерживается каждый период.

### Решение
**Реализовать формулу из Excel-модели (лист DATA, строки 38–41):**

```python
# WC_RATE = параметр уровня Project, default = 0.12
# NET_REVENUE — из шага s02_price

wc_current   = net_revenue[t] * wc_rate          # средний оборотный капитал периода t
wc_previous  = net_revenue[t-1] * wc_rate         # t=0: wc_previous = 0 (нет предыдущего периода)
delta_wc     = wc_previous - wc_current           # отток при росте выручки = отрицательный

ocf = contribution[t] + delta_wc + tax[t]
```

`WC_RATE` — именованный параметр уровня Project, `default = 0.12`, редактируемый пользователем.

### Почему ТЗ-формула неверна
Формула ТЗ `CONTRIBUTION × (1 − 0.12)` удерживает 12% от Contribution каждый период. Это ошибочно по двум причинам:
1. Оборотный капитал привязан к выручке, а не к Contribution.
2. При стабилизации выручки изменение оборотного капитала стремится к нулю — удержание исчезает. ТЗ-формула этого не отражает.

**Численный пример (из GORJI+, Y1):**
- NET_REVENUE = 38,9 млн ₽ → WC = 4,67 млн ₽
- Предыдущий WC (Y0) = 0,031 млн ₽
- ΔWC = 0,031 − 4,67 = **−4,64 млн ₽** (деньги заморожены)
- OCF = −104 т.₽ + (−4,64 М.₽) + 0 = **−4,74 млн ₽**
- ТЗ-формула даёт: −104 т.₽ × 0.88 = **−91 т.₽** — ошибка в 52 раза.

### Последствия
- В коде формула задокументирована ссылкой: `# SOURCE: GORJI+ DATA!B38:B41`
- Unit-тест проверяет граничный случай: t=0 (первый период), wc_previous=0.
- `WC_RATE` хранится в таблице `projects`, nullable = false, default = 0.12.

---

## ADR-CE-03 VAT-стрипинг в формуле ex-factory цены (D-02)

### Контекст
ТЗ (раздел 7.5.2) задаёт:
```
EX_FACTORY_PRICE = SHELF_PRICE_WEIGHTED × (1 − CHANNEL_MARGIN) × (1 − VAT_RATE)
```
Использование `× (1 − VAT_RATE)` для конвертации "цена с НДС → цена без НДС" математически неверно.

### Решение
**Реализовать формулу из Excel-модели (лист DASH, строки 33–35):**

```python
# VAT_RATE — параметр уровня Project, default = 0.20

shipping_reg   = (shelf_price_reg   / (1 + vat_rate)) * (1 - channel_margin)
shipping_promo = (shelf_price_promo / (1 + vat_rate)) * (1 - channel_margin)
ex_factory     = shipping_reg * (1 - promo_share) + shipping_promo * promo_share
```

Алгебраически эквивалентная запись:
```python
ex_factory = (shelf_price_weighted / (1 + vat_rate)) * (1 - channel_margin)
```

### Почему ТЗ-формула неверна
НДС 20% означает: цена с НДС = цена без НДС × 1.20. Следовательно:
```
цена без НДС = цена с НДС / 1.20 = цена с НДС × 0.8333
```
ТЗ применяет `× (1 − 0.20) = × 0.80` — это неверное "обратное" вычисление.

**Численная разница для VAT = 20%:**
- Корректно: `/ 1.20 = 83.33%` от цены с НДС
- ТЗ-формула: `× 0.80 = 80%` от цены с НДС
- **Систематическая ошибка: −4.17% от ex-factory цены → −4.17% от выручки → смещение всех downstream метрик**

На горизонте Y1–Y10 при выручке 1.86 млрд ₽ (GORJI+ etalon) ошибка в выручке составит ~77 млн ₽.

### Последствия
- В коде: `# SOURCE: GORJI+ DASH!D33-D35`
- Unit-тест: `ex_factory(shelf=100, vat=0.20, margin=0.30)` → `100/1.20*(1-0.30)` = `58.33`, не `100*0.80*0.70 = 56.00`.
- `VAT_RATE` хранится в таблице `projects`, nullable = false, default = 0.20.

---

## ADR-CE-04 База налога на прибыль (D-03)

### Контекст
ТЗ (раздел 7.6, шаг 11) задаёт:
```
PROFIT_TAX = TAXRATE × TAXBASE
```
TAXBASE оставлен неопределённым ("упрощённая модель, см. Excel"). Верификация Excel-модели (лист DATA, строка 40) уточняет.

### Решение
**Реализовать формулу из Excel-модели (лист DATA, строка 40):**

```python
# TAX_RATE — параметр уровня Project, default = 0.20
# contribution — значение из шага s05

if contribution[t] >= 0:
    tax[t] = -(contribution[t] * tax_rate)
else:
    tax[t] = 0  # убыток налогом не облагается
```

Знак `tax[t]` отрицательный (отток), складывается с OCF в ADR-CE-02.

### Архитектурные решения в этой формуле
1. **База — Contribution, не EBITDA и не бухгалтерская прибыль.** Это упрощение (реальный налог считается иначе), но оно зафиксировано в Excel и принято как эталон MVP. Для корректной реализации потребуется уточнение при переходе к Этапу 2.
2. **Убытки не создают налоговый щит** (нет переноса убытков). Снова упрощение эталонной модели — принимается как есть.
3. **`TAX_RATE` — параметр уровня Project**, не хардкод. `default = 0.20` (ставка налога на прибыль РФ).

### Последствия
- В коде: `# SOURCE: GORJI+ DATA!B40, formula: -IF(B27<0, 0, B27*0.2)`
- Unit-тест: при negative Contribution → tax = 0.
- При реализации Этапа 2 (корректный налоговый учёт) — заменить эту функцию, не ломая интерфейс step.

---

## ADR-07 Асинхронный пересчёт

### Контекст
Pipeline (12 шагов, все периоды, все SKU×каналы×сценарии) выполняется за неизвестное время — потенциально 2–10 секунд. Синхронный HTTP-запрос упрётся в таймауты и заблокирует UI.

### Решение
**Celery + Redis (broker) для расчётных задач. Frontend опрашивает статус через polling.**

Флоу:
1. POST `/api/projects/{id}/recalculate` → создаёт Celery task, возвращает `task_id`.
2. Frontend: GET `/api/tasks/{task_id}/status` каждые 2 сек.
3. По завершении: GET `/api/projects/{id}/results` — получает ScenarioResult.

Redis уже в стеке (CLAUDE.md) — использовать как Celery broker. Отдельный Redis instance не нужен.

### Обоснование
- Celery с Redis broker — стандартное решение для Python async tasks.
- Polling проще WebSocket для MVP: не нужна persistent connection, нет сложностей с reconnect.
- WebSocket — опция для V2 если polling окажется медленным.

### Альтернативы
- **FastAPI BackgroundTasks:** не masshtabiruetsya, выполняется в том же процессе, нет retry. Отклонено.
- **WebSocket:** overengineering для MVP. Отклонено.

### Последствия
- При запуске нового пересчёта предыдущая задача для того же проекта отменяется (revoke).
- Если задача упала — статус `FAILED` с сообщением ошибки, пользователь видит причину.

---

## ADR-08 Аутентификация в MVP

### Контекст
MVP — один пользователь (инициатор/владелец модели). ТЗ указывает Keycloak для финального продукта. Keycloak требует отдельного контейнера, настройки realm, clients, flows — ~2–3 дня работы до первой строки кода.

### Решение
**MVP: JWT-аутентификация на FastAPI (python-jose + passlib/bcrypt). Keycloak — Этап 2.**

Реализация:
- `POST /api/auth/login` → возвращает `access_token` (JWT, 8h) + `refresh_token` (30d).
- Middleware проверяет токен на каждом защищённом маршруте.
- Пользователь хранится в таблице `users` (id, email, hashed_password, role).

Миграция на Keycloak (Этап 2):
- JWT claims остаются теми же (sub, role).
- Замена только auth middleware — не трогает бизнес-логику.

### Обоснование
- MVP = 1 пользователь. Keycloak для одного пользователя — 100x overkill.
- Архитектурно: все эндпоинты защищены через `Depends(get_current_user)` — при смене auth-провайдера меняется только эта зависимость.

### Последствия
- Не реализовывать SSO, LDAP, MFA в MVP.
- При добавлении ролей (Этап 2) — добавить `role` claim в JWT и проверки в middleware.

---

## ADR-09 Экспорт документов

### Контекст
Система должна генерировать PPT, XLSX и PDF на основе данных проекта. Это CPU-интенсивные операции.

### Решение
**python-pptx (PPT), openpyxl (XLSX), WeasyPrint (PDF) — все через Celery (отдельная очередь `export`)**

Важно: WeasyPrint требует установленного GTK в окружении. В Docker (Linux-контейнер) это решается одной строкой в Dockerfile:
```dockerfile
RUN apt-get install -y libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0
```
В локальной разработке на Windows — использовать Docker для export-задач (не нативный Python).

### Последствия
- Шаблоны PPT хранятся в `backend/app/export/templates/`.
- Export — отдельная Celery queue с низким приоритетом (не мешает расчётам).
- Тест экспорта: проверяет что файл создаётся и не падает с ошибкой, не проверяет визуальный вид.

---

## ADR-10 Таблицы на фронте

### Контекст
Основной интерфейс — финансовые таблицы с инлайн-редактированием, подсветкой слоёв (predict/finetuned/actual), переключением периодов (месяц/год). AG Grid выбран в CLAUDE.md.

### Решение
**AG Grid Community Edition (MIT)**

Перед началом разработки верифицированы необходимые функции Community-версии:
- Inline cell editing ✓
- Cell renderers (цветовая подсветка) ✓
- Row grouping (базовое) ✓
- Column pinning ✓
- Value formatters ✓

Функции которых нет в Community и потребуют кастомной реализации:
- Excel-like Undo/Redo (нужна собственная история изменений через Zustand)
- Clipboard paste от Excel (нужен кастомный handler через `onCellValueChanged`)

### Последствия
- Undo/Redo реализуется на уровне стейта фронта (Zustand store), не через AG Grid API.
- При необходимости Enterprise-фич — обосновать стоимость лицензии пользователю (не принимать самостоятельно).

---

## ADR-11 Инфраструктура и окружения

### Контекст
Нужны окружения dev/staging/prod с чёткими правилами.

### Решение
**Docker Compose (dev + prod варианты) + GitHub Actions CI/CD**

```
infra/
├── docker-compose.dev.yml    # volumes для hot-reload, порты открыты
└── docker-compose.prod.yml   # no volumes, restart: always, nginx reverse proxy
```

Сервисы:
| Сервис | Dev port | Prod |
|--------|----------|------|
| backend (FastAPI) | 8000 | за nginx |
| frontend (Next.js) | 3000 | за nginx |
| postgres | 5432 | только внутренняя сеть |
| redis | 6379 | только внутренняя сеть |
| celery worker | — | — |

CI/CD:
- Push в `main` → GitHub Actions → build images → push to registry → SSH deploy on VPS → `docker compose pull && docker compose up -d`.
- Staging: отдельная ветка `staging`, деплой на тот же VPS в другой Docker namespace.

### Последствия
- `.env.example` содержит все переменные окружения с placeholder-значениями.
- Prod secrets хранятся только в GitHub Secrets и в `.env` на VPS (не в репо).
- Прямой доступ к prod-БД — только через SSH tunnel, никогда напрямую.

---

## ADR-16 AI-интеграция через Polza AI (Фаза 7)

**Статус:** Утверждено пользователем 2026-04-09. Реализация — Фаза 7
(post-MVP). До закрытия Фазы 6 (E2E + CI/CD) код AI-модуля не пишется.

### Контекст

Финансовый паспорт проекта — это **числа + интерпретация**. Текущий
MVP даёт числа: NPV/IRR/ROI/Payback по 3 сценариям и анализ
чувствительности. Аналитик-пользователь должен сам формулировать ответы
на бизнес-вопросы: "Почему NPV Y1-Y10 = 13.5М но Y1-Y5 = 27М?", "Что
больше всего давит на маржу?", "Какие риски сценария Conservative?".

В корпоративной FMCG-среде эти интерпретации каждый раз пишет
аналитик руками в PowerPoint. Это:
- **Часы работы** на проект (1-2 ч на стандартный паспорт)
- **Неконсистентность** — разные аналитики формулируют по-разному
- **Барьер для не-финансистов** (продакт-менеджеры, бренд-менеджеры) —
  они смотрят на цифры в готовом PPT, но не могут сами "поговорить"
  с моделью

LLM хорошо решают именно эту задачу: дано структурированное состояние
(KPI + параметры + дельты), выдать связный текст-комментарий. Это
**post-processing над уже валидированными числами**, а не часть
расчётного ядра.

**Технические ограничения для российской разработки:**
1. Прямой Anthropic API недоступен без VPN из РФ
2. OpenAI API недоступен без VPN из РФ
3. Биллинг в USD требует валютной операции — для корпоративных
   закупок неудобно
4. Yandex GPT / GigaChat — другая стилистика, заметно ниже качество
   на длинных финансовых рассуждениях (по нашему внутреннему тесту)

### Решение

**Polza AI** как единая точка доступа к LLM, image generation и web search.

**Base URL (верифицирован live smoke-тестом Phase 7.1, 2026-04-09):**
- **`https://polza.ai/api/v1`** — для openai SDK (chat completions,
  images, embeddings — стандартные OpenAI-compat endpoints).
  **ЭТО используем.** Полный URL chat endpoint'а:
  `https://polza.ai/api/v1/chat/completions`.

⚠️ **История корректировок URL (важно для будущих читателей):**

1. Первая версия ADR-16 (до Phase 7.1, 2026-04-09 утро): указан
   `https://api.polza.ai/api/v1` со своим subdomain `api.` — **неверно**.
2. Вторая версия (правка после первичного чтения polza.ai/docs/llms.txt):
   `https://polza.ai/v1` без `/api` префикса — **тоже неверно**. Этот
   URL возвращает 404 HTML polza.ai-лендинга (Next.js app), поэтому
   SDK не падает на AuthenticationError или APIError, а получает
   валидный HTTP 200 с HTML телом и пытается его парсить как JSON.
3. **Финальная версия (после live smoke-теста Phase 7.1):**
   `https://polza.ai/api/v1` — подтверждён curl-примером в
   `polza.ai/docs/api-reference/chat/completions.md`, live smoke-тест
   успешно выполняет chat completion.

**Урок:** до первого реального вызова любой внешний API нельзя
считать верифицированным. Документация может противоречить сама себе
или быть неполной. См. ERRORS_AND_ISSUES.md запись
"Polza AI base URL and model naming corrections (Phase 7.1)".

- **OpenAI SDK совместимость:** 100%. Используем `openai` Python SDK
  (`AsyncOpenAI` с кастомным `base_url='https://polza.ai/v1'`) — никаких
  ad-hoc HTTP-клиентов.
- **Bearer token auth:** `Authorization: Bearer <POLZA_AI_API_KEY>`,
  ключ из dashboard `https://polza.ai/dashboard/api-keys`.
- **Оплата:** в рублях по корпоративному счёту, без VPN, без валютных операций.
- **Лимиты:** max file size 50 MB, request timeout 600 сек, rate limiting
  через HTTP 429 (retry-after header).
- **OpenAPI spec:** `https://polza.ai/openapi.json` — для type generation
  если понадобится.

#### Доступные модальности (verified)

**1. Chat / text completions (`/api/v1/chat/completions`):**
- 379+ моделей из 70+ провайдеров (Anthropic, OpenAI, Google, DeepSeek,
  Meta, Yandex, etc — верифицировано через `/models` в Phase 7.1:
  `len(models.data) == 379`, 12 Claude моделей доступны)
- Дефолт для текстового AI:
  - `"anthropic/claude-sonnet-4.6"` — обычные задачи (executive summary,
    комментарии, объяснения дельт сценариев)
  - `"anthropic/claude-opus-4.6"` — критичные задачи (аудит формул,
    open-ended ответы)
  - Fallback: `"openai/gpt-4o"` (тот же SDK)
- **Формат имени модели: с точками, не с дефисами.** Polza использует
  `claude-sonnet-4.6` (точка между major.minor), а не `claude-sonnet-4-6`
  как могло показаться интуитивно. Первая версия ADR-16 была написана
  с дефисами — исправлено после Phase 7.1 smoke-теста.

**2. Image generation (`/v1/images/generations`, OpenAI compat):**
- ✅ **Подтверждено в Polza docs.** Endpoint OpenAI-совместим (тот же
  `openai` SDK, метод `images.generate()`)
- **Доступные модели для генерации упаковки/мокапов:**
  - `"black-forest-labs/flux-2-pro"` — high quality, mockup-friendly
  - `"black-forest-labs/flux-2-flex"` — быстрее/дешевле
  - `"openai/gpt-image-1"` (бывш. DALL-E 3 переименован) — натуральные
    изображения, OpenAI compatibility
  - `"x-ai/grok-imagine"` — новая модель xAI
  - `"qwen/qwen-image"` — Alibaba
  - `"bytedance/seedream-3"` / `"-4"` / `"-5-lite"` — ByteDance Seedream
- **Использование в задаче 7.8 (AI генерация package mockup):**
  начнём с `flux-2-pro` (баланс качества и цены), при необходимости
  переключимся на `gpt-image-1` или альтернативу.

**3. Web search (доступно как tool/feature):**
- ✅ **Подтверждено в Polza docs:** "Поиск в интернете — Как добавить
  веб-поиск к любой AI модели" (раздел `/docs/features/...`).
- **Точный API формат на момент написания ADR неясен** — возможны
  варианты: Anthropic native `web_search` tool в `tools[]` параметре,
  или special `extra_body` параметр Polza, или query string flag.
- **Решение:** уточнить через `polza.ai/openapi.json` или `support@polza.ai`
  при разработке задачи **7.7 (AI marketing research)**. Не блокирует
  начало 4.5/5.2 — это нужно только для Phase 7.

**4. Universal media endpoint (`/api/media`, native Polza):**
- POST /media с параметром `kind: 'image' | 'video' | 'audio'`
- Удобно если нужны не-image модальности (видео/аудио) — для нашего
  паспорта **не нужно**, опускаем.

**Конфигурация (`.env.example`):**
```
POLZA_AI_API_KEY=<секрет, выдаётся в polza.ai/dashboard/api-keys>
POLZA_AI_BASE_URL=https://polza.ai/api/v1
```

**Модули (создаются в Фазе 7):**
```
backend/app/services/ai_service.py        # AsyncOpenAI wrapper для chat
backend/app/services/ai_image_service.py  # AsyncOpenAI wrapper для image
backend/app/api/ai.py                     # /api/projects/{id}/ai/* endpoints
```

**Зависимости (Фаза 7, не сейчас):**
```
openai>=1.0
```

### Обоснование

| Критерий | Polza AI | Прямой Anthropic | OpenAI напрямую | Yandex GPT |
|---|---|---|---|---|
| Доступ из РФ без VPN | ✅ | ❌ | ❌ | ✅ |
| Оплата в рублях | ✅ | ❌ | ❌ | ✅ |
| Корпоративный счёт | ✅ | ❌ | ❌ | ✅ |
| Доступ к Claude 4.6 | ✅ | ✅ | ❌ | ❌ |
| OpenAI SDK совместимость | ✅ | ⚠️ (отд. SDK) | ✅ | ❌ (свой API) |
| Качество финансовых интерпретаций | ✅ (Claude 4.6) | ✅ | ⚠️ | ❌ |
| Vendor lock-in | низкий (можно сменить base_url) | средний | средний | высокий |

**Почему именно Claude 4.6 как дефолт:** в наших задачах (длинный
структурированный финансовый текст с числами, без галлюцинаций по
формулам) Claude 4.6 показывает лучшие результаты — особенно при
аудите ТЗ vs Excel (см. `TZ_VS_EXCEL_DISCREPANCIES.md` D-01..D-13:
из 13 расхождений 12 финального вердикта построены на Claude-объяснениях).

**Почему Sonnet дефолт, Opus опция:** Sonnet 4.6 покрывает 80% задач
(комментарии, summary) с хорошим балансом цена/латентность. Opus
включается осознанно для критических 20% (аудит формул, ответы
"почему модель так считает") где цена ошибки выше цены вызова.

**Почему openai SDK:** не пишем свой HTTP-клиент → меньше кода,
меньше багов, бесплатные фичи (стриминг, retry, rate limit handling).
Polza рекламирует 100% совместимость — отдельные провайдер-специфичные
параметры (например, `anthropic_beta`) пробрасываются через
`extra_body` параметр SDK.

### Альтернативы

1. **Прямой Anthropic API через корпоративный VPN** — отклонено:
   операционно дорого (поддержка VPN-инфры, флаки на CI), и не решает
   проблему оплаты в USD.

2. **OpenRouter** (международный аналог Polza) — отклонено: тоже USD,
   тоже VPN. Polza конкретно нацелен на российскую корпоративную нишу.

3. **GigaChat / Yandex GPT** — отклонено для финансовой интерпретации
   как дефолт, но **может быть добавлен в Фазе 7+ как secondary
   fallback** для compliance-сценариев "AI должен быть российский".

4. **Локальный LLM (Llama / DeepSeek) на GPU** — отклонено: capex на
   железо, отсутствие специализации на финансовых текстах, нагрузка на
   on-prem инфру не оправдана для side-функции.

5. **Не делать AI вообще** — отклонено по бизнес-обоснованию выше,
   но **реализуется только после закрытия Фазы 6**. AI должен
   комментировать только валидированные числа.

### Последствия

- **Полная изоляция AI-модуля от расчётного ядра.** `ai_service.py`
  читает уже сохранённые `ScenarioResult` + параметры проекта, не
  трогает `engine/`. Если Polza недоступен — расчёты продолжают
  работать, AI-фичи деградируют до placeholder'а "AI-комментарий
  недоступен".

- **Cost monitoring обязателен.** Polza тарифицируется в рублях за
  токены. Каждый AI-вызов логируется (`project_id, model, prompt_tokens,
  completion_tokens, cost_rub, ts`) в новой таблице `ai_usage_log`
  (создаётся в задаче 7.5). Месячный лимит на проект — параметр
  уровня Project (`ai_budget_rub_monthly`, default 1000 ₽).

- **Безопасность секретов.** `POLZA_AI_API_KEY` хранится только в
  `.env` (gitignored) и GitHub Secrets для CI/CD. Никогда не
  логируется, не возвращается в API.

- **Промпты — в коде, версионируются.** Все system/user prompts
  хранятся как Python-константы в `backend/app/services/ai_prompts.py`.
  Никаких "промпт из БД" в MVP — это создаёт surface для prompt
  injection. Промпты ревьюятся через PR как обычный код.

- **Output validation.** AI-ответы валидируются Pydantic-схемой
  (`AIExplanationResponse`) — структурированный JSON через
  `response_format={"type": "json_schema", ...}`. Никаких свободных
  текстов в API — всегда строго типизированный JSON, фронт его
  отображает в готовых компонентах.

- **Rate limiting на endpoint.** `/api/projects/{id}/ai/*` лимитированы
  10 запросов/минуту на пользователя через slowapi (или аналог) —
  чтобы не сжечь бюджет случайным циклом в UI.

- **Тесты.** AI-вызовы мокируются в pytest через `respx` или
  `unittest.mock.AsyncMock` на уровне `AsyncOpenAI.chat.completions.create`.
  Реальный Polza дёргается только в отдельном `tests/integration/test_polza_smoke.py`
  с маркером `@pytest.mark.live` — запускается вручную, не в CI.

- **Зависимость от Polza как SPOF.** Mitigation: документировать в
  ERRORS_AND_ISSUES возможный fallback на OpenRouter (тот же SDK,
  смена `base_url`). Реальная миграция — отдельная задача, если
  понадобится.

- **Image generation для package mockups (задача 7.8).** Используем
  `flux-2-pro` через `/v1/images/generations` (OpenAI compat). Полученные
  PNG/JPEG сохраняются как `MediaAsset` (kind=`concept_design`) в
  filesystem volume и линкуются с `ProjectSKU.package_image_id`. AI
  даёт **mockup для презентации**, не production-ready дизайн —
  это явно коммуницируется в UI рядом с кнопкой генерации.

- **Web search для marketing research (задача 7.7).** Точный API
  формат уточнить при разработке (Anthropic native `web_search` tool
  vs Polza `extra_body` parameter vs query string flag — выяснить через
  `polza.ai/openapi.json` или support). Результат сохраняется в новое
  поле `Project.marketing_research_text` (TEXT) или JSONB structure
  с цитированными источниками — finalized в 7.7. **Не блокирует**
  4.5 / 5.2 / 6.x — это Phase 7 only.

- **Pricing image generation:** flux-2-pro дороже chat completions
  (~5-10₽ за изображение vs <1₽ за chat). Cost monitoring обязателен,
  лимитируем количество image generations per project в `ai_budget_rub_monthly`.

---

## Сводная таблица решений

| # | Область | Решение | Статус |
|---|---------|---------|--------|
| ADR-01 | Backend | Python 3.12 + FastAPI + SQLAlchemy | Финально |
| ADR-02 | Frontend | Next.js 14 + TypeScript + shadcn/ui | Финально |
| ADR-03 | БД | PostgreSQL 16 | Финально |
| ADR-04 | PeriodValue | JSONB в одной строке на период | Финально |
| ADR-05 | Слои данных | source_type enum + приоритет в сервисе | Финально |
| ADR-06 | Engine | Чистые функции + Celery | Финально |
| ADR-CE-01 | Формулы | Excel-модель = источник истины | **Финально, не пересматривать** |
| ADR-CE-02 | OCF (D-01) | ΔWC-формула, WC_RATE=0.12 | **Финально, не пересматривать** |
| ADR-CE-03 | VAT (D-02) | Делить на (1+VAT), не умножать на (1-VAT) | **Финально, не пересматривать** |
| ADR-CE-04 | Налог (D-03) | База = Contribution, TAX_RATE=0.20 | **Финально, не пересматривать** |
| ADR-07 | Async | Celery + Redis, polling | Финально |
| ADR-08 | Auth | JWT в MVP, Keycloak в Этап 2 | Финально |
| ADR-09 | Экспорт | python-pptx + openpyxl + WeasyPrint | Финально |
| ADR-10 | Grid | AG Grid Community | Финально |
| ADR-11 | Infra | Docker Compose + GitHub Actions | Финально |
| ADR-16 | AI-интеграция | Polza AI (`https://polza.ai/api/v1`, OpenAI-совместимый), Claude 4.6 Sonnet/Opus chat + Flux-2-pro image gen + web search, Фаза 7 post-MVP. URL и формат имени моделей верифицированы live smoke-тестом Phase 7.1. | Финально |
