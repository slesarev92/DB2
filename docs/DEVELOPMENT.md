# Руководство разработчика DB2

Команды локальной разработки, frontend-проверки перед коммитом,
production deployment. Краткие правила работы — в [CLAUDE.md](../CLAUDE.md).

---

## Локальный dev-стек

```bash
# Поднять весь dev-стек (postgres + redis + backend + celery-worker + frontend)
docker compose -f infra/docker-compose.dev.yml up -d
docker compose -f infra/docker-compose.dev.yml ps        # все healthy?

# Логи конкретного сервиса
docker compose -f infra/docker-compose.dev.yml logs -f backend
```

URLs (когда compose работает):
- `http://localhost:8000/health` — backend healthcheck
- `http://localhost:8000/docs` — Swagger UI (FastAPI auto-генерация)
- `http://localhost:3000` — frontend
- `localhost:5432` — postgres (`dbuser` / `dbpassword` / `dbpassport`)
- `localhost:6379` — redis

---

## Тесты

```bash
# Запустить тесты (469 интеграционных против реального postgres,
# включая 4 тяжёлых E2E в tests/acceptance/ за marker `acceptance`).
# Обычный прогон для PR/регрессии автоматически исключает acceptance:
docker compose -f infra/docker-compose.dev.yml exec backend \
    pytest -q -m "not acceptance"

# Явный запуск E2E acceptance (требует
# backend/tests/fixtures/gorji_reference.xlsx):
docker compose -f infra/docker-compose.dev.yml exec backend \
    pytest -v -m acceptance
```

---

## Миграции и данные

```bash
# Применить миграции
docker compose -f infra/docker-compose.dev.yml exec backend alembic upgrade head

# Сгенерировать новую миграцию после изменения моделей
docker compose -f infra/docker-compose.dev.yml exec backend \
    alembic revision --autogenerate -m "сообщение"

# Засеять справочники (идемпотентно: повторный запуск не дублирует)
docker compose -f infra/docker-compose.dev.yml exec backend \
    python -m scripts.seed_reference_data

# Открыть psql внутри контейнера postgres
docker compose -f infra/docker-compose.dev.yml exec postgres \
    psql -U dbuser -d dbpassport
```

---

## Когда нужен rebuild / restart

### Backend перебилд — только при изменении `requirements.txt`
При обычных правках кода bind mount + uvicorn --reload подхватывают
изменения автоматически.

```bash
docker compose -f infra/docker-compose.dev.yml build --progress=plain \
    backend celery-worker
docker compose -f infra/docker-compose.dev.yml up -d --no-deps \
    --force-recreate backend celery-worker
```

### Celery-worker restart — ОБЯЗАТЕЛЬНО после изменений в:
`calculation_service`, `engine/`, `sensitivity_service` или другом коде,
который вызывается из Celery task. Celery НЕ имеет auto-reload
(в отличие от uvicorn). Признак проблемы: API endpoint работает,
recalculate возвращает 200, но в БД старые значения / новые поля = NULL.

```bash
docker compose -f infra/docker-compose.dev.yml restart celery-worker
```

---

## Frontend-проверки перед коммитом (ОБЯЗАТЕЛЬНО)

### `npx tsc --noEmit` — 0 ошибок
Самая важная проверка. Ловит отсутствующие импорты, undefined references,
несоответствия типов. **HTTP 200 на маршрут НЕ достаточен** — Next.js
dev mode радостно компилирует и отдаёт страницу даже с `X is not defined`
в коде, а runtime ошибка вылезет только когда React реально рендерит
компонент в браузере.

```bash
docker compose -f infra/docker-compose.dev.yml exec frontend npx tsc --noEmit
```

### При структурных изменениях — full restart контейнера, не HMR

HMR на Windows + Docker volume mount ненадёжен для новых route groups,
новых импортов и файлов. Признаки: страница показывает старую версию
несмотря на правки, `X is not defined` runtime error после Edit.

```bash
docker compose -f infra/docker-compose.dev.yml restart frontend
```

### При странностях — очистка `.next` build volume

Next.js build cache иногда держит старую версию модулей.

```bash
docker compose -f infra/docker-compose.dev.yml stop frontend
docker run --rm -v dbpassport-dev_frontend_next:/clean alpine \
    sh -c 'rm -rf /clean/* /clean/.*'
docker compose -f infra/docker-compose.dev.yml start frontend
```

### Визуальная проверка в браузере — после tsc

Не утверждать что задача закрыта, пока пользователь не подтвердит
визуально что новый функционал реально работает в браузере. SSR HTML
для `/(app)/*` маршрутов — это только loading spinner (auth restore
на клиенте), поэтому curl scraping не показывает реальный контент.

---

## Формат коммитов

```
тип(область): краткое описание

Подробности если нужны.
Closes #номер_задачи
```

Типы: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`

---

## Деплой на production

**Workflow: локально → GitHub → сервер.** Не редактировать код на
сервере напрямую.

```bash
# 1. Коммит локально
git add <files>
git commit -m "..."

# 2. Push на GitHub
git push origin main

# 3. По команде пользователя — деплой на VPS
ssh -i ~/.ssh/db2_deploy root@85.239.63.206 \
    "cd /opt/dbpassport && git pull origin main"

# Пересборка образов
ssh ... "cd /opt/dbpassport && docker build -f backend/Dockerfile.prod \
    -t dbpassport-backend:latest backend/"
ssh ... "cd /opt/dbpassport && docker build -f frontend/Dockerfile.prod \
    --build-arg NEXT_PUBLIC_API_URL=https://db2.medoed.work \
    --build-arg NPM_REGISTRY=https://registry.npmmirror.com \
    -t dbpassport-frontend:latest frontend/"

# Перезапуск
ssh ... "cd /opt/dbpassport/infra && docker compose -f docker-compose.prod.yml \
    up -d --force-recreate backend celery-worker frontend && sleep 5 && \
    docker compose -f docker-compose.prod.yml restart nginx"

# Миграции (если были)
ssh ... "cd /opt/dbpassport/infra && docker compose -f docker-compose.prod.yml \
    exec backend alembic upgrade head"
```

### Prod-инфра

- **Prod URL:** `https://db2.medoed.work` (nginx SSL termination →
  backend:8000 + frontend:3000)
- **IP:** `85.239.63.206` (Ubuntu 24.04, 2 CPU, 2GB RAM + 2GB swap)
- Старый IP `45.144.221.215` отброшен из-за RKN-блокировок и BGP-проблем
  у предыдущего провайдера
- Host nginx :80/443 → docker nginx :8080
- SSL: Let's Encrypt через certbot --nginx (см. `docs/SSL_SETUP.md`)
- SSH key: `~/.ssh/db2_deploy`. `.env` в `infra/.env` на сервере
- Образы: локальные `dbpassport-backend:latest` / `dbpassport-frontend:latest`
  (GHCR недоступен с RU VPS — переменные `BACKEND_IMAGE`/`FRONTEND_IMAGE`
  в `infra/.env` указывают на локальные теги)
- **Docker Hub rate limit:** новый сервер использует mirror через
  `/etc/docker/daemon.json` → `mirror.gcr.io` (Google's free Docker Hub
  mirror без rate limits)

### Frontend rebuild edge case
`NEXT_PUBLIC_API_URL` baked в build-time, поэтому при изменении API URL
(например при переходе http→https) **нужен docker build** frontend образа,
не просто restart.

### RU VPS networking
GitHub fetch с RU-серверов может быть нестабилен (периодически
`Connection reset by peer`). При деплое использовать retry-цикл:
```bash
for i in 1 2 3 4 5; do git fetch origin main && break; sleep 3; done
```
Это известное ограничение RU peering, не баг.

### Версионирование

Semver через git tags. Текущие: `v0.1.0` (MVP), `v0.2.0` (chat
persistence + delete project), `v0.3.0` (Phase 8 presentation parity),
`v2.4.0` (post-audit remediation). Пользователь иногда говорит
"версия 1.0/1.2" — это marketing milestone, в git это всегда semver
`vX.Y.Z`. На каждый prod-релиз создавать tag через
`git tag -a vX.Y.Z -m "..."` + push.
