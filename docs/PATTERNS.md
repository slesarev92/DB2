# Архитектурные паттерны DB2

Установлены в Фазе 1, применяются во всём проекте. При написании нового
кода — следуй им. Отступление — только с явным обоснованием в ADR или PR.

---

## 1. Async-safe relationships: `lazy="raise_on_sql"`

Все relationships в SQLAlchemy моделях объявлены с `lazy="raise_on_sql"` —
это запрещает случайные ленивые загрузки в async-сессиях. Любая попытка
обратиться к unloaded relationship поднимет понятную ошибку, а не
зависнет в greenlet warmup.

В service всегда явно использовать `selectinload(Model.relation)` при
чтении nested данных. Без selectinload Pydantic упадёт при сериализации.

## 2. Savepoint pattern для retry на UNIQUE constraints

При вставке с риском `IntegrityError` (нарушение UNIQUE):

```python
try:
    async with session.begin_nested():
        session.add(obj)
        await session.flush()
except IntegrityError as exc:
    raise DomainDuplicateError() from exc
```

`begin_nested()` создаёт savepoint. При IntegrityError откатывается
только savepoint, outer-транзакция остаётся живой. Без savepoint простой
`session.rollback()` в сервисе ломает outer transaction в тестах
(`SAWarning: transaction already deassociated from connection`).

## 3. Custom exceptions в service → HTTPException в API

Service-слой ничего не знает про HTTP. Поднимает доменные исключения
(`SKUInUseError`, `ScenarioMismatchError`, `ProjectSKUDuplicateError`...).
Endpoint ловит и переводит в `HTTPException` с правильным кодом и detail.
Чище чем ловить SQLAlchemy исключения в API.

## 4. Soft delete через `deleted_at` колонку + фильтр `IS NULL`

Финансовый продукт — данные не теряем. Для сущностей с soft delete:
- Колонка `deleted_at: Mapped[datetime | None]` (TIMESTAMPTZ NULL)
- Все service-методы чтения фильтруют `WHERE deleted_at IS NULL`
- DELETE endpoint проставляет `datetime.now(timezone.utc)`
- Никакого `is_deleted` boolean — `deleted_at` несёт timestamp

## 5. Append-only versioning для history-friendly данных

Для `PeriodValue` (и подобных): новая версия = новая строка с
`version_id = MAX(version_id) WHERE … + 1`. Старые версии остаются
как audit log "кто и когда менял". UNIQUE constraint включает
`version_id`. DELETE override = `DELETE WHERE source_type=finetuned`,
после чего GET возвращает predict.

## 6. `Numeric` (не Float) для денежных полей в БД

Все процентные ставки, цены, суммы — `Numeric(precision, scale)`.
`Float` теряет точность в финансовых расчётах. Pydantic v2 сериализует
`Decimal` как строку с трейлинг-нулями (`"0.190000"`, не `"0.19"`).
В тестах сравнивать через `Decimal(value) == Decimal("0.19")`,
не строки. Frontend нормализует отображение.

В **расчётном ядре** — float internally, Decimal на границах
(БД ↔ memory). Excel-модель работает с float (double precision),
точность ~15 знаков для NPV в миллионах рублей более чем достаточна.

## 7. Enums через `varchar_enum()` (не PG native enum)

Helper в `backend/app/models/base.py`:
```python
SAEnum(EnumCls, native_enum=False, length=N,
       values_callable=lambda x: [e.value for e in x])
```

Хранит `.value` (lowercase: `"monthly"`, не `"MONTHLY"`). Создаётся
как VARCHAR + CHECK constraint, а не PG ENUM type — расширение enum
без `ALTER TYPE ADD VALUE`. Type-safe в Python через декларацию
`Mapped[EnumCls]`.

## 8. Тесты против реального postgres + transaction-rollback изоляция

`backend/tests/conftest.py`:
- `test_db_url` (session): создаёт чистую `dbpassport_test` через admin
  connection к default `postgres` БД
- `test_engine` (session): применяет `Base.metadata.create_all` (без
  Alembic в test path — быстрее) + сидирует справочники один раз через
  `scripts.seed_reference_data`
- `db_session` (function): `connection.begin()` → session с привязкой
  к connection → `yield` → `transaction.rollback()`. Каждый тест
  изолирован
- `client` (function): HTTPX `AsyncClient` с подменой `get_db`
  dependency через `app.dependency_overrides`
- `test_user` + `auth_client` (function): для защищённых endpoint'ов

В `pytest.ini`: `asyncio_mode=auto`, обе scope (fixture и test) =
`session`, иначе `RuntimeError: Future attached to a different loop`
в asyncpg (см. ERRORS_AND_ISSUES.md).

## 9. JSONB без жёсткой схемы для эволюции

`PeriodValue.values: dict[str, Any]` — Pydantic не валидирует ключи
внутри. Состав показателей можно расширять без миграций.

**Mutation gotcha:** SQLAlchemy не отслеживает изменения внутри JSONB
автоматически. Если меняешь nested dict в loaded объекте — обязательно
`flag_modified(obj, "values")`, иначе UPDATE не выполнится:

```python
from sqlalchemy.orm.attributes import flag_modified
obj.values["new_key"] = 42
flag_modified(obj, "values")
```

## 10. Explicit order maps в Python для бизнес-сортировки

Когда алфавит даёт неправильный порядок (`'aggressive' < 'base' <
'conservative'`, `'y1y10' < 'y1y3' < 'y1y5'`) — сортировать в Python
после fetch через explicit dict-маппинги (`SCENARIO_ORDER`,
`SCOPE_ORDER`). Не делать `CASE` в SQL — для CRUD это micro-overhead,
читаемость важнее.

## 11. Integration smoke-test для каждого нового endpoint

**Lazy imports внутри endpoint функций (`def f(): from x import y`) не
валидируются ни линтером, ни pytest до первого вызова endpoint'а.**
Если endpoint никогда не покрыт тестом — `ModuleNotFoundError` или
`NameError` доходит до runtime, и пользователь видит 500 ошибку.

При создании любого нового endpoint **обязательно** написать хотя бы
один integration smoke-test — даже простой 200 OK с пустым проектом
ловит большинство import/typo ошибок:

```python
async def test_pnl_endpoint_returns_200(auth_client, db_session):
    project = await _seed_minimal_project(db_session)
    resp = await auth_client.get(f"/api/projects/{project.id}/pnl")
    assert resp.status_code == 200
```

Использовать `from app.models import X` (через `__init__.py` re-export)
для согласованности — все entities + enums экспортируются через
`backend/app/models/__init__.py`.
