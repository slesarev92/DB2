# Changelog

Все заметные изменения проекта фиксируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
проект следует [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

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
