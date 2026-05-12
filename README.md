# Цифровой паспорт проекта (DB2)

Корпоративная система расчёта и управления проектами вывода SKU на
рынок для FMCG-компаний. Автоматизирует Gate Reviews (G0-G5) на основе
финансового моделирования: NPV, IRR, ROI, Payback, Go/No-Go по 3
сценариям (Base / Conservative / Aggressive) на горизонте 10 лет.

- **Prod:** https://db2.medoed.work (версия [`v2.4.0`](CHANGELOG.md) от 2026-04-15)
- **Repo:** https://github.com/slesarev92/DB2

## Стек

- **Backend:** Python 3.12 · FastAPI · SQLAlchemy (asyncpg) · Alembic
  · Celery · Redis · PostgreSQL 16
- **Frontend:** Next.js 14 App Router · TypeScript · Tailwind CSS
  · shadcn/ui · AG Grid Community · Recharts
- **Экспорт:** openpyxl (XLSX) · python-pptx (PPTX) · WeasyPrint (PDF)
- **AI:** Polza AI (OpenAI-совместимый прокси) через AsyncOpenAI
- **Инфра:** Docker Compose (dev) · GitHub → SSH deploy (prod)
  · Let's Encrypt SSL · MinIO (S3-compatible media storage)

Обоснования выбора — [`docs/ADR.md`](docs/ADR.md).

## Quick start (dev)

```bash
# 1. Поднять стек
docker compose -f infra/docker-compose.dev.yml up -d --build

# 2. Применить миграции + засеять справочники
docker compose -f infra/docker-compose.dev.yml exec backend alembic upgrade head
docker compose -f infra/docker-compose.dev.yml exec backend python -m scripts.seed_reference_data

# 3. Прогнать тесты (без тяжёлых E2E)
docker compose -f infra/docker-compose.dev.yml exec backend pytest -q -m "not acceptance"
```

Открыть:

- http://localhost:3000 — frontend
- http://localhost:8000/docs — Swagger UI (FastAPI auto-генерация)
- http://localhost:8000/health — backend healthcheck

Dev-пользователь создаётся через `backend/scripts/create_dev_user.py`.
Подробные команды dev-стека и frontend-проверок — в
[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

## Структура

```
DB2/
├── backend/            # Python / FastAPI / SQLAlchemy / Alembic / Celery
│   ├── app/
│   │   ├── api/        # HTTP endpoints
│   │   ├── engine/     # Расчётное ядро (s01..s12 pipeline)
│   │   ├── export/     # XLSX / PPTX / PDF экспортёры
│   │   ├── models/     # ORM модели
│   │   ├── schemas/    # Pydantic контракты
│   │   └── services/   # Бизнес-логика
│   ├── migrations/     # Alembic
│   └── tests/          # pytest (unit + integration + acceptance)
├── frontend/           # Next.js / TypeScript
│   ├── app/            # App Router роуты
│   ├── components/
│   └── lib/
├── infra/              # docker-compose для dev и prod
├── docs/               # ТЗ compliance, аудиты, гайды (см. docs/README.md)
├── scripts/            # Seed-скрипты, демо-импорт
└── CLAUDE.md           # Системный промт + правила работы
```

## Документация

Главный entry point — [`docs/README.md`](docs/README.md) (индекс всех
актуальных документов: ADR, ROADMAP, 3 аудита,
TZ_VS_EXCEL_DISCREPANCIES, CLIENT_FEEDBACK, SSL_SETUP).

Для LLM-агента читать [`CLAUDE.md`](CLAUDE.md) в корне — содержит роль,
стек, архитектуру, правила работы, команды, deploy workflow.

## Workflow разработки

1. Работа в dev через Docker Compose
   (см. [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)).
2. Коммит с осмысленным message (формат `тип(scope): краткое описание`
   — `feat` / `fix` / `refactor` / `test` / `docs` / `chore` / `ci`).
3. `git push origin main` → GitHub.
4. **Deploy на prod — только по явной команде**
   (см. `docs/DEVELOPMENT.md` раздел "Деплой на production").

## Лицензия

Proprietary. Все права у заказчика.
