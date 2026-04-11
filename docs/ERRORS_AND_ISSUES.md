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

## [2026-04-10] mock_polza_mockup fixture не мокала generate_image (mockup тесты 503)

**Проблема:** 3 mockup-теста (without_reference, with_reference, set_primary)
падали с 503 — `Polza media submit 401: Некорректный API ключ`.

**Контекст:** `generate_image()` в `ai_service.py` использует `httpx.AsyncClient`
напрямую (Polza Media API), а не OpenAI-совместимый клиент. Fixture мокала только
`_get_client()` (OpenAI client), но `generate_image` вызывался без мока.

**Решение:** Добавлен `monkeypatch.setattr(ai_service, "generate_image", gen_img_mock)`
в `mock_polza_mockup` fixture — теперь перехватывается httpx-путь.

**Урок:** При мокировании AI-сервиса проверять какой HTTP-клиент используется
конкретной функцией. `_get_client()` (OpenAI SDK) и `generate_image()` (raw httpx)
— два разных пути, оба нужно мокать.

---

## [2026-04-09] Polza AI base URL и model naming — две ошибки в ADR-16, выявленные live smoke-тестом Phase 7.1

**Проблема:** После того как пользователь положил реальный
`POLZA_AI_API_KEY` в `.env`, запустил `pytest -m live
tests/integration/test_polza_smoke.py` — тест упал **два раза подряд**
из-за разных ошибок в ADR-16.

**Ошибка №1 — неверный base URL.** Первый запуск: `openai` SDK
выполнил `POST https://polza.ai/v1/chat/completions` и получил в ответ
**HTML-страницу лендинга polza.ai** (Next.js 404 page на 2.5КБ),
который SDK попытался парсить как JSON. `APIError` с огромным HTML
в тексте исключения.

Первая версия ADR-16 (до Phase 7.1) указывала `https://polza.ai/v1`
без `/api` префикса, якобы «верифицированный» через чтение
`polza.ai/docs/llms.txt`. На самом деле правильный URL —
`https://polza.ai/api/v1`, что подтверждается curl-примером в
`polza.ai/docs/api-reference/chat/completions.md`:
```bash
curl -X POST "https://polza.ai/api/v1/chat/completions" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

**Ошибка №2 — неверный формат имени модели.** После фикса URL второй
запуск вернул HTTP 400 JSON:
```json
{"error":{"code":"BAD_REQUEST","message":"Модель \"anthropic/claude-sonnet-4-6\" не найдена"}}
```

ADR-16 указывал `anthropic/claude-sonnet-4-6` (с дефисами между
major и minor версиями). Проверка через `/api/v1/models` endpoint
показала, что Polza именует Claude модели **с точкой**:
`anthropic/claude-sonnet-4.6`, `anthropic/claude-opus-4.6`. Всего в
Polza 379 моделей, 12 из них Claude (3-haiku, 3.5-haiku, 3.7-sonnet,
3.7-sonnet:thinking, haiku-4.5, opus-4 / 4.1 / 4.5 / 4.6, sonnet-4 /
4.5 / 4.6).

**Контекст:** Phase 7.1 была завершена с 8 unit-тестами на моках —
моки конечно всегда зелёные, они не ходят в реальный Polza. Именно
отдельный live smoke-тест с маркером `@pytest.mark.live` (который
в обычный pytest прогон не попадает) выявил обе ошибки при первом
реальном вызове. Без smoke-теста Phase 7.2 началась бы с такой же
поломки, но в более сложном контексте (endpoint, UI, промпт).

**Решение:**

1. **Base URL.** Исправлен в трёх местах:
   - `.env.example` → `POLZA_AI_BASE_URL=https://polza.ai/api/v1`
   - Пользовательский локальный `.env` (только URL, ключ не трогал)
   - `docs/ADR.md` ADR-16: обновлены все упоминания URL + добавлена
     секция "История корректировок URL" с хронологией двух неверных
     версий, чтобы будущие читатели не повторили

2. **Model naming.** Исправлены константы в
   `backend/app/services/ai_service.py`:
   ```python
   DEFAULT_CHAT_MODEL = "anthropic/claude-sonnet-4.6"  # было: 4-6
   COMPLEX_CHAT_MODEL = "anthropic/claude-opus-4.6"    # было: 4-6
   ```
   Соответствующие assert'ы в `test_ai_service.py` — тоже.
   ADR-16 обновлён с явной пометкой «Формат имени модели: с точками».

3. **Повторный smoke-тест.** После обоих фиксов:
   ```
   tests/integration/test_polza_smoke.py::test_polza_smoke_chat_completion PASSED in 5.36s
   ```
   Round-trip Polza → Claude 4.6 Sonnet → JSON {"reply":"pong",
   "lucky_number":<int>} → Pydantic validation → OK. Стоимость ~0.01₽.

4. **Regression.** `pytest -m "not acceptance and not live"` → 286/286
   зелёных (8 unit-тестов test_ai_service используют `claude-sonnet-4.6`
   в моках).

**Урок:**

- **До первого реального вызова любой внешний API — не верифицирован.**
  Документация может противоречить сама себе или быть неполной. ADR-16
  написан на базе документации polza.ai, но две из трёх ключевых
  деталей (URL + формат имени модели) оказались некорректны.
- **Мок-тесты не ловят ошибки в структуре запроса к реальному API.**
  Они только проверяют логику вокруг SDK. Для внешних интеграций
  обязателен хотя бы один live smoke-тест — он должен быть написан
  в той же задаче что и клиент, иначе расхождение выплывет
  позже в более дорогом контексте.
- **Модели в Polza — через точку.** Форматы имён моделей у LLM
  провайдеров неконсистентны: Anthropic native API использует
  `claude-sonnet-4-5-20250929`, OpenRouter — `anthropic/claude-sonnet-4.5`,
  Polza — `anthropic/claude-sonnet-4.5` / `4.6`. Всегда проверять
  через `/models` endpoint перед деплоем.
- **Docker env_file для secrets.** Найден рядом: `infra/docker-compose.dev.yml`
  не имел `env_file:` директивы, поэтому новые переменные из `.env`
  не доходили до контейнера. Добавлено `env_file: ../.env` в секции
  `backend` и `celery-worker`. На будущее: любая новая переменная
  окружения должна одновременно попадать в `.env.example` и в
  compose `environment:` или `env_file:`.

---

## [2026-04-09] Docker Desktop Windows: file-level bind mount создаёт 0-byte marker на хосте (Phase 6.1)

**Проблема:** При настройке GORJI Excel fixture для E2E acceptance
теста попытался добавить в `infra/docker-compose.dev.yml` file-level
read-only mount:
```yaml
- ../PASSPORT_MODEL_GORJI_2025-09-05.xlsx:/app/tests/fixtures/gorji_reference.xlsx:ro
```

Mount технически работал — внутри контейнера файл видим как 7.6 MB.
Но Docker Desktop на Windows **создал 0-byte файл на хосте** в точке
`backend/tests/fixtures/gorji_reference.xlsx`. `git status` подхватил
его как untracked файл, при `git add` он попал в staged changes.

**Контекст:** На нативном Linux Docker file-level bind mount работает
иначе — точка монтирования живёт только в mount namespace контейнера,
на хосте ничего не создаётся. Docker Desktop на Windows использует
WSL2 backend, и файловые события проксируются через Virtiofs, что
приводит к созданию markers на Windows FS.

**Решение:** Отказался от file-level mount. Вместо этого:
1. Оригинал `PASSPORT_MODEL_GORJI_2025-09-05.xlsx` по-прежнему в
   корне репо (в git, ~7.6 MB)
2. Один раз копируется в `backend/tests/fixtures/gorji_reference.xlsx`
   через `cp` (dev setup шаг)
3. `backend/tests/fixtures/.gitignore` исключает копию чтобы не было
   дубля в git
4. Обычный bind mount `../backend:/app` прокидывает файл внутрь
   контейнера автоматически
5. Тест находит его по пути `/app/tests/fixtures/gorji_reference.xlsx`

**Урок:** Избегать file-level bind mount в compose на Windows.
Directory-level mount — ок. Если нужен read-only файл из корня репо
в контейнере — лучше **скопировать в bind-mounted директорию** через
dev setup скрипт, чем прокидывать через file-level mount. Для CI
(задача 6.2) этот вопрос не актуален — там Linux runners.

---

## [2026-04-09] Jinja2 template: `row.values` резолвится как метод dict, не как ключ (Phase 5.3)

**Проблема:** При рендере PDF-шаблона `project_passport.html` для слайда
«PnL по годам» Jinja2 падал с
`TypeError: 'builtin_function_or_method' object is not iterable`
на строке `{% for v in row.values %}`. Сам context передавался
корректно: `{"label": "Net Revenue", "values": ["1 000", "2 000", ...]}`.

**Контекст:** PnL строка конструируется в `_build_pnl_context` как
dict с ключами `label` и `values` (список отформатированных строк).
В template итерация `{% for v in row.values %}`.

**Решение:** Переименовал ключ `values` в `cells` — и в context builder,
и в template. Исправление в одном коммите вместе с smoke-тестом
генерации PDF.

**Урок:** Jinja2 attribute access (`obj.attr`) сначала пробует
`getattr(obj, attr)`, потом fallback на `obj[attr]`. Для Python dict
`getattr(d, 'values')` возвращает связанный метод `dict.values`, а
не ключ `"values"` — и Jinja2 считает это успешным lookup'ом. Другие
зарезервированные имена dict которые нельзя использовать как ключи в
context: `keys`, `items`, `get`, `update`, `pop`, `copy`, `setdefault`,
`clear`, `fromkeys`, `popitem`. Правило: не использовать имена методов
Python dict как ключи в context-dict'ах для Jinja2 templates. Если
поле семантически просится называться `values` — назвать `cells`,
`entries`, `data` или явно обернуть в namespace-объект.

---

## [2026-04-09] celery-worker не подхватывал fix `_load_seasonality_coefficients` (stale module cache)

**Проблема:** После задачи 4.3 (визуальная проверка таба «Сценарии»)
пользователь увидел в pipeline ошибку
`ValueError: invalid literal for int() with base 10: 'months'` при
recalculate проектов с привязанной WTR seasonality.

**Контекст:** Background — в Discovery V2 я уже поправил
`_load_seasonality_coefficients` в `calculation_service.py` чтобы
поддерживать nested format `{"months": [12 vals]}` (формат seed
для WTR/CSD/EN/TEA/JUI). Backend pytest 207/207 проходил, GORJI
acceptance с WTR seasonality прошёл с drift -0.70% (потом 0.10%).

При визуальной проверке 4.3 пользователь нажал «Применить и
пересчитать» на проект GORJI (привязанный WTR). Backend получил
PATCH+POST recalculate, ответил 202 Accepted, но Celery worker
крашнулся с `int("months")` error.

**Корневая причина:** **Stale module cache в celery-worker контейнере.**

`backend` контейнер запускается с `uvicorn --reload` и подхватывает
изменения в коде через bind mount. **`celery-worker` контейнер
такой watch-restart НЕ имеет** — Celery prefork запускает воркер один
раз, импортирует все модули в memory, и держит их до явного restart.

При editing `calculation_service.py` (например fix
`_load_seasonality_coefficients`), backend service сразу подхватывает,
но celery-worker продолжает использовать **старую** версию модуля,
загруженную при старте контейнера.

Pytest проходил потому что pytest запускается в **backend** контейнере,
не в celery-worker.

**Решение:**
1. `docker compose -f infra/docker-compose.dev.yml restart celery-worker`
   подхватил новый код. Recalculate работает.
2. **Regression test добавлен** в `tests/api/test_calculation.py::
   TestBuildLineInputs::test_seasonality_profile_months_format` —
   создаёт проект, привязывает WTR seed профиль, вызывает
   `build_line_inputs`, проверяет что seasonality правильно применён
   к monthly periods. Если parser снова сломается, тест упадёт.

**Урок:**
- При любом изменении в `app/services/`, `app/engine/`, `app/tasks/` —
  **обязательно** restart celery-worker, иначе recalculate использует
  старый код. Это уже задокументировано в CLAUDE.md в разделе команды
  разработки, но я его пропустил при D-22 commit (тогда тоже надо было
  restart, но recalculate происходил через pytest eager mode и багов
  не вылезло).
- При написании тестов для service-кода, который использует JSONB
  данные из seed — **всегда** проверять с реальным seed профилем, не
  только синтетическим. test_calculation `_seed_minimal_project`
  не привязывал seasonality (default None), поэтому покрытие парсера
  было дырой.
- При архитектурных изменениях, затрагивающих pipeline, — **прогонять
  через реальный recalculate проект**, не только pytest.

**Профилактика:** Добавить hooks в `update-config` skill чтобы при
изменении в `backend/app/services|engine|tasks/` автоматически
перезапускать celery-worker. Или просто помнить.

---

## [2026-04-08] launch_year/month сначала на ProjectSKU — архитектурно неверно (Excel: per канал)

**Проблема:** Discovery V1 (SKU_1/HM) показал что pipeline корректен per-line.
Решение D-13 launch lag было первоначально реализовано как
`ProjectSKU.launch_year + launch_month` (коммит eb8426d). Но Quick check #2
показал что Excel хранит launch per **(SKU × Channel)**, не per SKU.

**Контекст:** Quick check #2 раскрыл структуру DASH: каждый SKU блок
содержит **6 каналов** через col_base offset (HM=2, SM=50, MM=98, TT=146,
E-COM_OZ=194, E-COM_OZ_Fresh=242). Внутри одного SKU блока
launch_year/launch_month в DASH **разные для разных каналов**:

```
SKU "Gorji Цитрус Газ Пэт 0,5":
  HM              year=2025 month=2  (Y2 Feb)
  SM              year=2025 month=2
  MM              year=2025 month=2
  TT              year=2024 month=11 (Y1 Nov, на 3 мес раньше HM)
  E-COM_OZ        year=2024 month=11
  E-COM_OZ_Fresh  year=2024 month=11
```

Бизнес-логика: классические каналы (TT, e-com) → первичная дистрибуция
для тестирования. Modern trade (HM/SM/MM) подключаются позже.

**Решение:** Вариант C (одобрен пользователем) — rollback launch с
`ProjectSKU` на `ProjectSKUChannel`. Чистая архитектура, соответствует
Excel. Будет реализовано в новой сессии.

**Урок:** при добавлении нового поля сразу думать "это свойство ЭТОГО
объекта или СВЯЗИ?" Launch — это свойство **выхода в канал**, не SKU.
Quick check #1 (8 SKU блоков в DASH) дал false impression что launch
per SKU. Только Quick check #2 (per-channel sub-blocks) выявил
правильную структуру.

**На будущее:** при моделировании поля проверять Excel **в нескольких
точках** (не только первый блок) до commit. Я бы поймал это раньше
если бы перед добавлением поля сравнил launch для двух разных каналов
одного SKU.

---

## [2026-04-08] ROI overflow Numeric(10,6) + test workaround вместо фикса (обнаружено в Phase 4.2)

**Проблема:** Реальный Celery recalculate task падал с
`asyncpg.NumericValueOutOfRangeError: numeric field overflow. DETAIL: A field
with precision 10, scale 6 must round to an absolute value less than 10^4.`
при попытке сохранить `ScenarioResult.roi` ≈ 581 878.

**Контекст:** Excel-формула ROI (D-06): `(-SUM(FCF)/(SUMIF(FCF,"<0")-1))/COUNT`.
Когда **все FCF положительные** (что случается если в проекте нет CAPEX Y0),
`SUMIF<0 = 0`, денoминатор = `-1`, и формула вырождается в `SUM(FCF) / N` —
абсолютное среднее в рублях, а не ratio. Для тестовых данных с ND=0.5,
offtake=10, shelf=100 это даёт миллионы, что не помещается в Numeric(10,6)
(макс 9999.999999).

**Решение:**
1. **Расширение precision колонки** `scenario_results.roi` до `Numeric(20, 6)`.
   Миграция `65003c0135cc_expand_scenario_result_roi_to_numeric_`. Это
   минимальное изменение которое убирает overflow без искажения математики.
2. **API для project CAPEX/OPEX**: `GET/PUT /api/projects/{id}/financial-plan`
   с маппингом year → period_id первого периода model_year. До этого
   CAPEX/OPEX на уровне проекта были захардкожены в `()` tuples в
   calculate_and_save_scenario.
3. **UI для ввода плана**: `FinancialPlanEditor` в табе «Параметры». Без
   capex/opex pipeline не может давать разумные KPI (все FCF положительные
   → ROI вырождается, см. root cause).

**Урок — главный:**
> **Workaround в тесте ≠ фикс проблемы.**

В задаче 2.4 я увидел эту же ошибку при написании тестов и "решил" её
снижением параметров `_seed_minimal_project` (nd=0.001, offtake=1.0,
shelf=10.0) чтобы числа помещались в Numeric(10,6). Тесты прошли 168/168,
я закоммитил задачу как закрытую. **В реальном UI при дефолтных параметрах
формы канала проблема сразу всплыла.**

Правильно было:
1. Расследовать root cause (D-06 quirk → overflow в edge case)
2. Создать issue с пометкой "блокирует реальную работу" ИЛИ сразу расширить
   precision колонки + добавить API для CAPEX/OPEX
3. Пометить в задаче 2.4 "acceptance требует реальных данных, а не test-only
   стаба"

Вместо этого я обошёл симптом и отложил решение на Phase 4, где оно и
взорвалось. +1 час на фикс в критической точке вместо 30 минут заранее.

**Правило на будущее:** если тест упал из-за того что БД не принимает
значения pipeline → это **bug дизайна**, не test issue. Решать на месте,
не workaround'ом. Маленький workaround в тесте — red flag.

---

## [2026-04-08] Celery worker не видит task после добавления `import app.tasks` в worker.py

**Проблема:** При нажатии кнопки «Пересчитать» в UI frontend получал
`FAILURE` с сообщением `'calculations.calculate_project'`. В логах
celery-worker: `Received unregistered task of type 'calculations.
calculate_project'. The message has been ignored and discarded.`

**Контекст:** Worker был запущен через `docker compose up -d` в начале
разработки (задача 0.2), когда `app/worker.py` был **заглушкой** —
создавал `celery_app` и регистрировал только `system.ping`. В задаче 2.4
я добавил `import app.tasks` в конце worker.py для регистрации
`calculations.calculate_project`. **Но worker-процесс не рестартился
с тех пор**, и Python модуль `app.worker` в его памяти был старый, без
импорта `app.tasks`.

Bind mount `../backend:/app` обновлял файл на диске, но процесс worker'а
не перечитывает Python модули автоматически.

**Решение:** `docker compose restart celery-worker`. После рестарта
worker импортировал новый `app/worker.py`, увидел task в `[tasks]`
секции startup log:
```
[tasks]
  . calculations.calculate_project
  . system.ping
```

**Урок:** после **любых изменений** в Python коде backend которые
затрагивают модули, импортируемые Celery worker'ом (в том числе
transitive dependencies), **обязательно рестартовать celery-worker**,
не только backend. bind mount обновляет файлы на диске, но Python не
перезагружает уже импортированные модули.

Добавил в чек-лист CLAUDE.md (или планирую добавить).

---

## [2026-04-08] asyncpg + Celery prefork + asyncio.run = "Future attached to a different loop"

**Проблема:** После фикса unregistered task, recalculate падал с
`RuntimeError: Task ... got Future ... attached to a different loop`
в `asyncpg/protocol/protocol.pyx` при `pool._do_ping_w_event`.

**Контекст:** `app/db/__init__.py` создаёт **global** `engine = create_async_engine(...)` на import-time. Этот engine создаёт asyncpg connection pool, коннекшены которого привязываются к event loop того процесса
который их открыл. В FastAPI (uvicorn) всё работает потому что один event
loop на весь процесс. В Celery worker — **каждый task делает `asyncio.run()`**,
который создаёт **новый event loop**. Первый task успешно берёт коннекшен
из пула. После завершения task loop закрывается. Второй task получает
новый loop, но пул держит коннекшены от старого закрытого loop →
`"Future attached to a different loop"`.

В тестах (задача 2.4) проблема не всплывала потому что использовался
`task_always_eager=True` — задачи выполнялись в том же процессе FastAPI
с одним event loop.

**Решение:** В `app/tasks/calculate_project.py` создавать **локальный
engine с NullPool** внутри `_calculate_project_async`:

```python
engine = create_async_engine(
    settings.database_url,
    poolclass=NullPool,
)
session_maker = async_sessionmaker(engine, ...)
try:
    async with session_maker() as session:
        ...
finally:
    await engine.dispose()
```

`NullPool` не переиспользует коннекшены — каждый запрос открывает
свежий. Коннекшены живут только в рамках текущего `asyncio.run` и
корректно закрываются. Global `async_session_maker` остаётся
только для FastAPI dependency injection.

**Урок:** global asyncpg engine **нельзя** использовать в Celery prefork
worker без поправок. Либо NullPool в каждом task, либо переход на sync
driver. Eager mode тестов **маскирует** эту проблему — обязательно
тестировать real worker при любых async+Celery изменениях.

Также: два бага подряд (unregistered task + loop mismatch) прошли
тесты Phase 2.4 потому что integration test использовал eager mode.
`IMPLEMENTATION_PLAN.md` плана 2.4 говорил "реальный Celery worker test
как future extension" — эта отметка должна быть **блокером** до
перехода в Phase 3+, а не "nice to have".

---

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

## [2026-04-10] 500 на upload ai_reference — PermissionError media dir

**Проблема:** POST `/api/media/upload` с `kind=ai_reference` возвращает 500.
Traceback: `PermissionError: [Errno 13] Permission denied: 'media/1/ai_reference/...'`.

**Контекст:** Prod-сервер, backend работает как `appuser` (uid=999).
Поддиректории `media/1/ai_reference/` и `media/1/ai_generated/` были
созданы при предыдущем деплое, когда backend ещё работал как root
(dev Dockerfile без USER). После перехода на `Dockerfile.prod` с
`USER appuser` — новый процесс не может писать в root-owned директории
внутри named volume `media-storage`.

**Решение:** `docker exec -u root ... chown -R appuser:appuser /app/media/`.
Одноразовый фикс — новые директории создаются уже от appuser и проблема
не повторится.

**Урок:**
- При переходе dev → prod Dockerfile (root → non-root user) проверять
  ownership файлов в persistent volumes.
- Named volumes сохраняют ownership от первого container-а, последующие
  контейнеры с другим UID не могут писать без явного chown.

---

## [2026-04-10] body.period_scope → AttributeError (explain-kpi endpoint)

**Проблема:** Endpoint `POST /api/projects/{id}/ai/explain-kpi` падает с
`AttributeError: AIKpiExplanationRequest has no attribute period_scope`.
4 теста test_explain_kpi_* тоже падают.

**Контекст:** В `ai.py` строки 214 и 291 обращались к `body.period_scope`,
но Pydantic schema `AIKpiExplanationRequest` определяет поле как `scope`
(тип `PeriodScope`). Вероятно, при рефакторинге переименовали поле в
schema но забыли обновить 2 вызова `_persist_kpi_commentary`.

**Решение:** `body.period_scope` → `body.scope` (2 вхождения в ai.py).

**Урок:**
- `tsc --noEmit` ловит такое на фронте, для бэкенда аналог — `mypy --strict`.
  Рассмотреть включение mypy в CI.
- После переименования поля в Pydantic schema — grep по старому имени.

---

## [2026-04-10] Frontend + celery-worker unhealthy в prod

**Проблема:** `docker compose ps` показывает frontend и celery-worker
как `(unhealthy)` несмотря на то что оба работают корректно.

**Контекст:**
1. **celery-worker:** использует тот же образ что backend
   (`Dockerfile.prod`), в котором `HEALTHCHECK` проверяет `curl
   localhost:8000`. Celery не запускает HTTP-сервер → healthcheck
   всегда fail.
2. **frontend:** `HEALTHCHECK ... wget localhost:3000` — Alpine
   резолвит `localhost` в `::1` (IPv6), а Next.js standalone слушает
   только `0.0.0.0` (IPv4). `wget http://127.0.0.1:3000/` работает.

**Решение:**
- `docker-compose.prod.yml`: override healthcheck для celery-worker
  (`celery inspect ping`) и frontend (`wget http://127.0.0.1:3000/`).
- `frontend/Dockerfile.prod`: заменён `localhost` → `127.0.0.1` для
  будущих сборок образа.

**Урок:**
- Healthcheck в Dockerfile наследуется всеми контейнерами из этого
  образа. Если образ используется для разных сервисов (api + worker) —
  обязательно override healthcheck в compose.
- Alpine + Docker = IPv6 по умолчанию для `localhost`. Всегда
  использовать `127.0.0.1` в healthcheck.

---

## [2026-04-11] Lazy import внутри endpoint минует pytest

**Проблема:** PnL endpoint падал с `ModuleNotFoundError: No module named
'app.models.enums'` в runtime, но 444 pytest passed. UI показывал
"Ошибка" на табе P&L.

**Контекст:** Phase 8.5. Импорт `from app.models.enums import ScenarioType`
был сделан **внутри функции** `pnl_endpoint` (lazy для избежания
циклических зависимостей). Pytest для этого endpoint'а ещё не написан.
ScenarioType на самом деле экспортируется из `app.models` напрямую,
а модуля `app.models.enums` не существует.

**Решение:**
- Вынести импорт ScenarioType в общий блок lazy imports внутри функции
  (`from app.models import Scenario, ScenarioType`).
- На уровне коммита добавить базовый тест для нового endpoint'а
  (даже smoke-test 200 OK).

**Урок:**
- **Lazy imports внутри endpoint функций не валидируются ни линтером,
  ни pytest до первого вызова.** При создании нового endpoint **обязательно**
  написать хотя бы один integration test на 200 OK с пустым проектом —
  это поймает ModuleNotFoundError, NameError, неправильные импорты.
- Использовать `from app.models import X` (не `from app.models.X import Y`)
  для согласованности — все entities + enums экспортируются через
  `__init__.py` модуля.

---

## [2026-04-11] Celery worker не подхватывает изменения кода без restart

**Проблема:** После добавления per-unit метрик в `calculation_service`
(Phase 8.3) пересчёт через UI продолжал давать `nr_per_unit=None` —
несмотря на uvicorn --reload + bind mount.

**Контекст:** Backend uvicorn auto-reloads при изменении кода через
bind mount. Celery worker — отдельный контейнер, тоже использует bind
mount, но **не перезагружается** автоматически. Recalculate
выполняется через Celery task, поэтому использовался старый код.

**Решение:**
- `docker compose -f infra/docker-compose.dev.yml restart celery-worker`
  после изменений в `calculation_service.py`, `engine/`, или любом
  модуле, который вызывается из Celery task.

**Урок:**
- При изменении кода, который выполняется в Celery (calculation_service,
  engine steps, sensitivity_service) — **обязательно** restart
  `celery-worker`. Backend reload не покрывает Celery.
- Признак проблемы: API endpoint работает, recalculate возвращает 200,
  но в БД старые значения / новые поля = NULL.

---

## [2026-04-11] RU VPS IP в RKN registry → site недоступен глобально

**Проблема:** После деплоя на VPS `45.144.221.215` сайт работал только
у владельца. Другие пользователи (в РФ с мобильных операторов и за
рубежом из EU/US) получали connection timeout.

**Контекст:** Phase 8 деплой v0.3.0 на VPS неназванного RU провайдера.
Let's Encrypt cert получили без проблем, host nginx + certbot работали
локально OK. С check-host.net 14/20 нод по миру показывали timeout.

**Диагноз:** Двойная проблема:
1. **RKN block** — IP `45.144.221.215` оказался в реестре
   Роскомнадзора (вероятно потому что предыдущий пользователь IP
   хостил блокированный контент). Российские мобильные операторы
   и часть проводных ISP блокировали соединения через DPI.
2. **BGP peering issues** — у того же VPS-провайдера плохой peering
   с европейскими/американскими транзитными сетями. Маршруты от
   многих AS просто не существовали.

**Доказательства:**
- VPN включён → сайт открывается (трафик мимо RU DPI)
- Мобильный оператор РФ → не работает (DPI/блок)
- Хостинг ноды РФ (check-host) → работают (хостинги не фильтруются)
- Check-host из США/Германии → timeout (BGP)
- Check-host из РФ Москва (residential) → timeout (RKN/CF block)

**Попытка решения 1: Cloudflare proxy** — настроили CF nameservers
+ proxied A-record. Помогло частично — для большинства мира заработало,
но российские провайдеры всё равно блокировали CF anycast IPs (RKN
периодически блокирует CF целыми диапазонами).

**Финальное решение:** Миграция на новый VPS `85.239.63.206` с чистым
IP и хорошим peering. Результат check-host: 13/15 локаций OK
(только Иран в фейле — это их собственные блокировки).

**Урок:**
- **Перед деплоем prod на новый IP:** прогнать через check-host.net
  с разных регионов чтобы убедиться что IP не в registry / нет BGP
  проблем. Лучше потратить 5 минут на проверку чем переезжать потом.
- Для RU VPS: проверить публичные IP-блок-листы (например
  github.com/zapret-info/z-i для RKN registry).
- VPS-провайдер тоже важен — некоторые AS имеют проблемы с peering
  к зарубежным сетям после санкций.
- **Cloudflare proxy** — хорошее решение для большинства случаев,
  но в РФ периодически блокируется. Не надёжно для пользователей в РФ.

---

## [2026-04-11] Docker Hub anonymous rate limit на новых VPS

**Проблема:** После установки docker на чистом сервере, первый
`docker pull` или `docker build` с base image из docker.io падает с
`error from registry: You have reached your unauthenticated pull rate limit`.

**Контекст:** Docker Hub лимитирует анонимные pulls до ~100 запросов
в 6 часов с одного IP. На свежем VPS этот лимит может быть уже
исчерпан другими арендаторами этого IP.

**Решение:** Настроить mirror через `/etc/docker/daemon.json`:

```json
{
  "registry-mirrors": ["https://mirror.gcr.io"]
}
```

Затем `systemctl restart docker`. После этого все pulls идут через
Google Container Registry зеркало Docker Hub — без rate limits.

**Урок:**
- При bootstrap нового сервера сразу настраивать `mirror.gcr.io`,
  не дожидаясь rate limit ошибки.
- Альтернативы: docker.io login (если есть аккаунт), `quay.io`,
  `public.ecr.aws/docker`.

---
