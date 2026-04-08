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

## [2026-04-08] pytest-asyncio: session-scoped engine + function-scoped tests = "Future attached to a different loop"

**Проблема:** После фикса bcrypt-инцидента те же 6 auth-тестов упали уже с другой ошибкой: `RuntimeError: ... got Future <Future pending ...> attached to a different loop` в `asyncpg/protocol/protocol.pyx` при первом `session.flush()` в любом тесте, который ходит в БД. Тесты которые не дёргают сессию (`test_me_without_token`, `test_me_with_garbage_token`) проходили — характерная подсказка.

**Контекст:** В `pytest.ini` стоял `asyncio_default_fixture_loop_scope = session` (для shared engine fixture), но `asyncio_default_test_loop_scope` оставался default'ом — `function`. Pytest-asyncio 0.24+ создаёт отдельный event loop на каждый тест, а session-scoped `test_engine` с уже живыми соединениями привязан к loop'у, в котором его создавали. Когда function-scoped тест тянется к engine, asyncpg обнаруживает чужой loop → RuntimeError.

**Решение:** В `backend/pytest.ini` добавить `asyncio_default_test_loop_scope = session`. Безопасно потому что pytest гонит тесты последовательно — конкуренции event loop'ов всё равно нет. Все 8 тестов сразу прошли (1.86s).

**Урок:**
- Когда смешиваешь session-scoped async-fixtures (engine, connection pools) с pytest-asyncio тестами, обе scope (`fixture` и `test`) должны быть `session`. Это в pytest-asyncio 0.24+ задаётся явно двумя ключами в pytest.ini.
- Симптом "Future attached to a different loop" в asyncpg/SQLAlchemy ≈ всегда либо смешанные loop scopes, либо engine, переданный между процессами/тредами.
- Всегда проверять конфиг pytest-asyncio при первом запуске async-тестов с session-scoped fixtures, не ждать падения.

---

## [2026-04-08] passlib 1.7.4 несовместим с bcrypt >= 4.1

**Проблема:** При запуске первых auth-тестов (задача 1.1) 6 из 8 кейсов упали в `passlib.context.CryptContext.hash()` с ошибкой `ValueError: password cannot be longer than 72 bytes, truncate manually if necessary`. При этом наши пароли — 11 байт.

**Контекст:** В Dockerfile свежеустановлены `passlib[bcrypt]>=1.7.4` + `python-jose` + `pytest`. `passlib[bcrypt]` притянул `bcrypt 4.4.0` (последняя на момент установки). При первом обращении к `pwd_context.hash()` passlib пытается определить версию bcrypt через `bcrypt.__about__.__version__`, но в bcrypt 4.1+ этот атрибут удалён → AttributeError → fallback логика passlib пробует hash на тестовом 240-байтном пароле для детекции "wrap bug", и bcrypt 4.1+ теперь жёстко режет вход >72 байт с ValueError. Падение происходит на самом первом hash() в любом тесте, который создаёт юзера. 2 теста, которые не дёргают bcrypt (`test_me_without_token` и `test_me_with_garbage_token`), прошли — это было первой подсказкой.

**Решение:** Pin `bcrypt>=4.0.0,<4.1.0` явной строкой в `backend/requirements.txt` (4.0.1 — known-good с passlib 1.7.4). Pin фиксирует transitive dep, который раньше тянулся как `passlib[bcrypt]` без указания версии.

**Урок:**
- При добавлении `passlib[bcrypt]` в новый проект сразу пинить bcrypt < 4.1, не ждать падения тестов.
- Когда после установки новой зависимости тесты падают c загадочной ошибкой про "длинный пароль" — это passlib/bcrypt incompat, не наш баг.
- Альтернатива на будущее: рассмотреть переход на argon2 или прямое использование `bcrypt` без passlib, когда passlib получит фикс или будет переписан. Сейчас passlib не активно мейнтейнится.

---

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
