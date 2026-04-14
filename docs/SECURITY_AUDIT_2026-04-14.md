# Security audit — Цифровой паспорт проекта

**Дата:** 2026-04-14
**Scope:** backend API, прод-инфраструктура, prod creds, rate limiting, CORS, XSS/SQLi.
**Контекст:** аудит готовности к продажам enterprise FMCG-клиентам.
Соответствие 152-ФЗ и стандартным вопросам security-review клиента.

---

## Сводка

| # | Severity | Finding | Статус |
|---|---|---|---|
| S-01 | 🔴 **CRITICAL** | IDOR: endpoints не проверяют ownership | ✅ **FIXED 2026-04-14** (коммит в main) |
| S-02 | 🔴 **CRITICAL** | Hardcoded prod admin creds (admin/admin123) | Блокер продаж |
| S-03 | 🟡 MEDIUM | CORS конфиг ок, но нужна верификация prod env | Low effort |
| S-04 | 🟡 MEDIUM | Rate limiting только на AI endpoints | Low effort |
| S-05 | 🟢 OK | XSS в PDF защищён через Jinja2 autoescape | — |
| S-06 | 🟢 OK | Raw SQL только в test conftest (безопасно) | — |
| S-07 | 🟢 OK | SQL-injection защита через SQLAlchemy ORM | — |
| S-08 | ℹ️ INFO | Flaky acceptance test (async pool) | Не security, но запись |

---

## S-01 (CRITICAL) — IDOR (Insecure Direct Object Reference)

**OWASP:** [A01:2021 – Broken Access Control](https://owasp.org/Top10/A01_2021-Broken_Access_Control/).

### Проблема

`backend/app/services/project_service.py:73-81`:
```python
async def get_project(
    session: AsyncSession, project_id: int
) -> Project | None:
    stmt = select(Project).where(
        Project.id == project_id,
        Project.deleted_at.is_(None),
    )
    return await session.scalar(stmt)
```

Фильтр по `deleted_at`, но **не по `created_by`**. Любой залогиненный
пользователь получает любой проект по числовому id.

`backend/app/api/projects.py` endpoints принимают `current_user:
Depends(get_current_user)`, но используют его **только для authn**,
не для authz. Нет проверки `project.created_by == current_user.id`.

### Затронутые endpoints

Подтверждённо уязвимы (прямая работа с project_id):
- `GET    /api/projects/{project_id}` — чтение чужого проекта
- `PATCH  /api/projects/{project_id}` — редактирование чужого
- `DELETE /api/projects/{project_id}` — soft delete чужого
- `POST   /api/projects/{project_id}/recalculate` — триггер расчёта чужого

**Предположительно уязвимы** (те же паттерны, нужен grep/аудит):
- `/api/projects/{id}/skus`, `/api/projects/{id}/channels`,
  `/api/projects/{id}/period-values`, `/api/projects/{id}/bom`,
  `/api/projects/{id}/scenarios`, `/api/projects/{id}/financial-plan`,
  `/api/projects/{id}/media`, `/api/projects/{id}/obppc`,
  `/api/projects/{id}/akb`, `/api/projects/{id}/sensitivity`,
  `/api/projects/{id}/pnl`, `/api/projects/{id}/pricing-summary`,
  `/api/projects/{id}/value-chain`, `/api/projects/{id}/actual-import`.

### Proof of concept

Регистрация двух пользователей, user-A создаёт проект id=10, user-B логинится
и делает `GET /api/projects/10` с Bearer token user-B → получает проект user-A.

### Impact

- **152-ФЗ нарушение** — персональные данные одного клиента (через
  project.name, sku.name, financial данные) становятся доступны другому.
- **Корпоративная утечка данных** — финансовые модели конкурентов одной
  компании могут попасть к другой (или к infiltrator'у).
- **Block enterprise sales** — security-аудит клиента моментально
  завалит этот пункт. Для FMCG корп-клиентов (целевая аудитория)
  это "go-no-go" пункт.

### Рекомендация по fix

1. Добавить в `project_service.get_project()` параметр `user_id`:
   ```python
   async def get_project(
       session: AsyncSession, project_id: int, user_id: int,
   ) -> Project | None:
       stmt = select(Project).where(
           Project.id == project_id,
           Project.deleted_at.is_(None),
           Project.created_by == user_id,
       )
       return await session.scalar(stmt)
   ```
2. Обновить все вызовы в `api/*.py` — передавать `current_user.id`.
3. Для связанных entities (sku, channel, period_value, bom, scenario, etc)
   — перед любой операцией сначала `await project_service.get_project(...)`
   с user_id, если None → 404. Иначе 404 раскрывает существование проекта.
4. Добавить integration-тесты: user-B пытается получить ресурс user-A → 404.
5. Альтернатива (роли): `UserRole.ADMIN` может всё, `ANALYST` — только своё.
   В модели роль уже есть (`scripts/create_dev_user.py:23`). Использовать.

Estimated effort: **3-5 часов** (fix + 10-15 integration-тестов + регрессия).

### ✅ Fix implemented 2026-04-14

- `project_service.get_project()` и `list_projects()` принимают `user: User | None`.
- `is_project_owned_by()` — короткая проверка owner'а для cascade endpoints.
- `require_owned_project` dependency в `app/api/deps.py` — применена через
  router-level `dependencies=[...]` на akb / obppc / ai / period_values
  batch routers (префикс `/api/projects/{project_id}/...`).
- Cascade endpoints (project_skus, project_sku_channels, bom, scenarios,
  period_values через psk_channel_id) — inline helper функции
  `_require_X_owned(session, id, user)` проверяют ownership через
  entity → psk → project.
- Admin (UserRole.ADMIN) bypass — админы видят все проекты.
- 7 regression tests в `backend/tests/api/test_security_idor.py`:
  GET/PATCH/DELETE/recalculate/list от чужого user → 404, от owner → 200,
  от admin → 200.

### ⚠️ S-01b — остаток (в backlog, не блокер для MVP)

`GET /api/media/{media_id}` **намеренно без auth** (используется в
`<img src>` тегах, которые не передают Authorization header). Если
attacker угадает media_id — скачает файл (дизайн упаковок).

Варианты fix на будущее:
- Pre-signed URLs с TTL (например minio direct links).
- Cookie-based session auth для media endpoints.
- Signed media tokens в query string.

Не критично для MVP демо, но для enterprise нужно закрыть.

---

## S-02 (CRITICAL) — Hardcoded prod admin credentials

### Проблема

`scripts/seed_demo_project.py:21-23`:
```python
API_URL = "https://db2.medoed.work"
EMAIL = "admin@example.com"
PASSWORD = "admin123"
```

Скрипт лупит по **прод-API** с открытым тривиальным паролем. Файл был
добавлен 2026-04-11 и находится в `scripts/` (добавлен в `.gitignore`
при аудите, но **может быть уже в git history** или у других разработчиков).

`backend/scripts/create_dev_user.py:26` создаёт того же пользователя
с паролем `admin123`. Скрипт помечен "dev only" в комментариях, но:
- Если кто-то запустил `seed_demo_project.py` против прода —
  пользователь `admin@example.com / admin123` **существует на проде**.
- Неясно, был ли создан этот user через Keycloak admin procedure или
  прямым запуском create_dev_user на prod БД.

### Impact

- Любой, кто знает email/password (брутфорс `admin123` — 1 попытка),
  получает admin-доступ на прод.
- Если IDOR (S-01) реализован — admin видит все проекты всех юзеров.

### Рекомендация по fix

1. **Немедленно:** зайти на прод через `psql` или БД-миграцию, поменять
   пароль admin-юзера на крипто-случайный (32 символа), записать в
   secure vault (1Password / Bitwarden для команды).
2. Проверить прод БД: какие пользователи зарегистрированы, нет ли
   ещё тестовых аккаунтов. `SELECT email, role, created_at FROM users;`
3. Рефакторить `scripts/seed_demo_project.py`:
   ```python
   EMAIL = os.environ["DEMO_ADMIN_EMAIL"]
   PASSWORD = os.environ["DEMO_ADMIN_PASSWORD"]
   API_URL = os.environ.get("DEMO_API_URL", "http://localhost:8000")
   ```
4. `backend/scripts/create_dev_user.py` — добавить явную проверку
   `assert os.environ.get("APP_ENV") == "dev"` в начале main(), падать
   с ошибкой если запущено где угодно кроме dev.
5. В `scripts/.gitignore` добавить `seed_demo_project.py` до рефакторинга
   (сделано в аудите).

Estimated effort: **30 минут** (смена пароля + рефакторинг script).

---

## S-03 (MEDIUM) — Верификация CORS на prod

### Проблема

`backend/app/core/config.py:40` — default `cors_origins = "http://localhost:3000"`.
Настраивается через env `CORS_ORIGINS`. Код корректен.
`docs/SSL_SETUP.md:147` упоминает что на prod должно быть
`https://db2.medoed.work`.

### Требуется верификация

```bash
ssh -i ~/.ssh/db2_deploy root@85.239.63.206 \
    "grep CORS_ORIGINS /opt/dbpassport/infra/.env"
```
Ожидаемое: `CORS_ORIGINS=https://db2.medoed.work`.
Если пусто или `*` — нужно поправить.

Estimated effort: **10 минут** (проверить, поправить env, перезапустить backend).

---

## S-04 (MEDIUM) — Rate limiting coverage

### Проблема

`backend/app/api/ai.py` — 13 AI endpoints с `@limiter.limit("10/minute"
per-key)`, 3 с `5/minute`. Хорошо.

**Остальные CRUD endpoints — без rate limit.** Потенциал для:
- Brute-force на `/api/auth/login`.
- DDoS на `/api/projects/{id}/recalculate` (Celery task per call —
  можно утопить worker).
- Генерация экспортов (`/api/projects/{id}/export/{format}`) — тяжёлая
  генерация PPTX/PDF.

### Рекомендация

Добавить на критичные endpoints:
- `/api/auth/login` — `5/minute` per IP.
- `/api/projects/{id}/recalculate` — `5/minute` per user.
- `/api/projects/{id}/export/*` — `10/minute` per user.

Estimated effort: **1 час**.

---

## S-05 (OK) — XSS в PDF exporter

`backend/app/export/pdf_exporter.py:67-70`:
```python
_jinja_env = Environment(
    loader=FileSystemLoader(...),
    autoescape=select_autoescape(["html", "xml"]),
)
```

Jinja2 autoescape включён → пользовательский ввод (project.name, sku.name)
автоматически экранируется при рендере в HTML для PDF.

PPTX — текст через python-pptx → попадает в OOXML, не рендерится как HTML,
XSS классический неприменим.

XLSX — openpyxl, формулы не создаются из пользовательского ввода.

---

## S-06 (OK) — Raw SQL

Один grep на `text(f"...")`:
```
backend/tests/conftest.py:63: DROP DATABASE IF EXISTS "{TEST_DB_NAME}"
backend/tests/conftest.py:64: CREATE DATABASE "{TEST_DB_NAME}"
```

Только в test conftest, `TEST_DB_NAME` hardcoded константа, не юзер-ввод.
Безопасно.

---

## S-07 (OK) — SQL-injection

Все запросы через SQLAlchemy ORM (`select(Model).where(...)` со
параметрами как Python values). Psycopg/asyncpg используют prepared
statements с bind-параметрами. SQL-injection невозможна.

---

## S-08 (INFO) — Flaky acceptance test

`backend/tests/api/test_ai.py::test_explain_sensitivity_cache_hit` —
`asyncpg.exceptions.ConnectionDoesNotExistError: connection was closed
in the middle of operation`.

Воспроизводится только при полном прогоне suite (444 тест-функций).
В одиночку — `1 passed in 1.02s`. Это async connection pool race
condition. Запись в `docs/ERRORS_AND_ISSUES.md`.

Не security, но regression-gate шумит → либо исправить, либо помечать
`@pytest.mark.flaky(reruns=2)`.

---

## Рекомендация по приоритету fixes

Перед любым выходом на enterprise-продажи:

1. **S-01 (IDOR)** — 3-5 часов. Критично.
2. **S-02 (prod admin password)** — 30 минут. Критично.
3. **S-03 (CORS verify)** — 10 минут.
4. **S-04 (rate limit coverage)** — 1 час.

Итого security-fix фаза: ~1 рабочий день.

## Не-security улучшения для enterprise (backlog)

- Sentry / централизованный error tracking на prod.
- Postgres backup стратегия (pg_dump ежедневно в S3).
- 152-ФЗ: политика хранения PII, журнал аудита изменений.
- Role-based access control (сейчас только `UserRole` enum, но не
  используется для авторизации).
- Multi-tenancy: сейчас один общий namespace. Для B2B SaaS нужны
  organisations и изоляция между ними.
