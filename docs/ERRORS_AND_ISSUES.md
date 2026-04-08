# Журнал ошибок и проблем

Сюда записываются все нетривиальные проблемы, возникшие во время разработки,
и их решения. Это коллективная память проекта — чтобы не наступать на одни
и те же грабли дважды.

Правило из CLAUDE.md: при возникновении проблемы — сначала записать сюда,
потом искать корневую причину, не лечить симптом.

---

## Формат записи

Каждая запись — отдельный раздел второго уровня с датой и кратким названием,
содержащий четыре поля:

- **Проблема:** что пошло не так
- **Контекст:** при каких условиях возникло
- **Решение:** как исправили
- **Урок:** что учесть в будущем

Записи добавляются сверху (новые — выше старых).

---

## Записи

## [2026-04-08] Containerd image manifest conflict при повторной сборке

**Проблема:** `docker compose build frontend` упал с `failed to solve: image "docker.io/library/dbpassport-dev-frontend:latest": already exists` на шаге exporting image. После чего `docker rmi dbpassport-dev-frontend:latest` тоже упал — мешал висящий контейнер.

**Контекст:** Первая сборка 0.2 была запущена в background (`docker compose up --build -d`) и принудительно остановлена через TaskStop до завершения (чтобы обойти буферизацию вывода в `| tail`). После этого повторный build в foreground обнаружил в containerd-снапшоттере незавершённый манифест с тем же тегом и отказался перезаписывать.

**Решение:** 
1. `docker rm -f <container_id>` — удалить зависший промежуточный контейнер
2. `docker rmi dbpassport-dev-frontend:latest` — удалить неполный tag
3. Повторный build прошёл чисто

**Урок:** Не убивать docker build/compose через TaskStop без предварительного `docker compose down` — buildx с containerd-снапшоттером оставляет висящие manifest-ы. Перед retry сборки — всегда проверять `docker ps -a` + `docker images`.

---

## [2026-04-08] npm install занимает ~15 минут в Docker build, прогресс не виден

**Проблема:** Сборка frontend-контейнера в docker compose висела без видимой активности. При запуске в foreground выяснилось, что шаг `RUN npm install` для Next.js 14 внутри node:20-alpine занял **890 секунд** (~15 мин).

**Контекст:** Первая сборка dev-окружения (задача 0.2), package.json на 329 пакетов (next, react, typescript, eslint). npm не выводит прогресс установки в stdout — файл вывода выглядит «застывшим», хотя работа идёт.

**Решение:** 
1. В `frontend/Dockerfile` добавлен `RUN --mount=type=cache,target=/root/.npm npm install` — BuildKit cache mount сохраняет загруженные tarballs между сборками, повторные builds в 3-5 раз быстрее. Аналогично для `pip` в `backend/Dockerfile` (`target=/root/.cache/pip`).
2. Для отладки длинных сборок — использовать `docker compose build --progress=plain` **без** пайпинга вывода через `tail`/`head` (пайп буферизует до EOF и скрывает live-прогресс).

**Урок:** 
- BuildKit cache mount — обязательный паттерн для package-manager шагов. Включать в Dockerfile с самого начала, не post-factum.
- Длинные docker builds всегда запускать с `--progress=plain` + без pipe на выводе.
- Если npm install медленный — подозревать не Docker, а сеть/proxy/npm registry. Проверять через `npm view <pkg>` напрямую с хоста.

---
