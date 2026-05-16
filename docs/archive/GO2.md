# GO2 — Старт новой сессии DB2

> Создано 2026-05-15 после сессии, в которой закрыты Фаза A (6/6) и
> 4.5/5 Фазы B по MEMO v2.1.

---

## 0. Минимальный план старта (5 шагов)

1. Прочитать `CLAUDE.md` (роль, стек, правила работы).
2. Прочитать `docs/CLIENT_FEEDBACK_v2_DECISIONS.md` — **источник истины**
   по решениям клиента и плану Фаз A/B/C.
3. Прочитать секцию `[Unreleased]` в `CHANGELOG.md` — что закрыто
   в последней сессии (2026-05-15).
4. Запустить `git log --oneline -12` — увидеть 10 коммитов сессии.
5. Поднять dev-стенд:
   ```
   docker compose -f infra/docker-compose.dev.yml up -d
   docker compose -f infra/docker-compose.dev.yml exec backend alembic upgrade head
   docker compose -f infra/docker-compose.dev.yml exec backend pytest -q --ignore=tests/integration
   ```
   Ожидаемо: **472 passed** (468 non-acceptance + 4 acceptance GORJI).

После этого — готов работать.

---

## 1. Где остановились (2026-05-15)

### Фаза A — закрыта целиком (6/6 ✅)

Регрессии и блокеры данных:
- A.1 Diagnostic logging в `replace_plan` (`ea262e1`)
- A.2 Экспорт PDF/XLSX/PPTX — клиент подтвердил работу
- A.3 Gantt status dropdown (`3aa5b8d`) — фикс корневой причины
- A.4 SKU images / лого — клиент подтвердил работу
- A.5 D-12 docstring + ROADMAP sync, 5 лет финально (`498486c`)
- A.6 Сценарии intermittent — diagnostic logging (`ea262e1`)

### Фаза B — закрыто 4.5/5

- B.7 Q6 CA&M / Marketing → per-channel (`53e4629`)
- B.8 Q1 production_mode_by_year (`f1ec2eb`)
- B.9 **часть 1**: статьи CAPEX (`9df4617`) — таблица `capex_items`,
  UI "+ Статья CAPEX" в раскрывающемся блоке
- B.10 Q7 НДС dropdown + дефолт 22% (`60d5edb`)
- B.11 Q5 BOM 3 уровня + per-year override (`0875eb8`)

### Что в работе / следующий приоритет

**B.9b — Помесячная гранулярность Y1-Y3 + UI матрицы 43 колонки.**
*Поднято наверх Фазы C* в `CLIENT_FEEDBACK_v2_DECISIONS.md`.

---

## 2. B.9b — техническое задание

### Цель

Финансовый план переключается с **10 годовых ячеек** (Y1..Y10) на:
- **36 помесячных** для Y1-Y3 (M1..M36)
- **7 годовых** для Y4-Y10
- Итого **43 точки** на проект, по одной записи `ProjectFinancialPlan`
  на каждый период.

### Что уже готово (от B.9 части 1)

- Таблица `capex_items` (миграция `e5f6a7b8c9d0`)
- `OpexItem` уже работает per-период через `financial_plan_id` FK
- Engine `aggregator.py` принимает `project_opex` и `project_capex`
  как `tuple[float, ...]` длины `n` — backend инфра готова
- UNIQUE на `project_financial_plans (project_id, period_id)`
  гарантирует одну запись на (проект × период)

### Что нужно сделать

**Backend:**
1. `_get_first_period_by_year` в `financial_plan_service.py` — заменить
   на `_get_all_periods_for_project` (возвращает все 43 period с
   `period_number` и `model_year`)
2. `FinancialPlanItem` → принимать `period_id` (или `period_number`)
   вместо `year`. Обратная совместимость: оставить `year` как
   опциональный fallback (если только year — сохраняется в первый
   период года, текущее поведение)
3. `replace_plan` — сохранять во ВСЕ переданные периоды
4. `list_plan_by_period` — новый метод возвращает 43 элемента
   (capex/opex per period + opex_items + capex_items per period)
5. API endpoint `GET /api/projects/{id}/financial-plan-monthly` или
   query-параметр `?granularity=monthly`
6. Обновить engine `pipeline.run_project_pipeline` если нужно
   (вероятно уже работает корректно — agg per line)

**Frontend:**
7. Переписать `financial-plan-editor.tsx`:
   - Опция: горизонтальная scrollable таблица 43 колонки,
     строки = CAPEX итог / CAPEX статьи / OPEX итог / OPEX статьи
   - ИЛИ tabbed view: "Помесячно Y1-Y3" + "Годами Y4-Y10"
   - Toggle "Y-only" возвращает текущий 10-строчный режим (опционально)
8. UI должен поддерживать **bulk fill** — "залить значение на диапазон
   месяцев" (упомянуто в MEMO 5.1 для Fine Tuning, тут тоже актуально)

### Риски / на что смотреть

- Существующие проекты имеют записи только по 10 годам — миграция
  данных НЕ нужна (старые записи остаются как одна запись на год)
- `_validate_line_input` в `calculation_service` — не трогает финплан,
  работает с per-PSC inputs. Безопасно.
- Acceptance тесты GORJI: они импортируют `import_gorji_full.py`,
  который **не** заполняет финплан. То есть acceptance безразличен
  к этой правке (никакого CAPEX/OPEX из GORJI в финплане).

### Оценка

~10-15 часов работы. Большая часть — frontend UI (~6-10 часов).
Backend ~3-5 часов.

---

## 3. Альтернативы (если B.9b не приоритет)

Все из Фазы C. Перечислены по убыванию impact:

- **Fine Tuning расширение** (#14) — copacking_rate, logistics_per_l,
  CA&M, marketing per-period. ~4-6 ч. Заказчик прямо ожидает это
  по MEMO 5.1.
- **P&L фильтры + pivot Excel** (#15) — разрезы по SKU/каналу/бренду.
  ~6-8 ч. Разблокирует MEMO 6.1.
- **Q4 OBPPC перенос в Содержание** (#13) — ~1 ч, чисто навигация
  в `project-nav-context.tsx`.
- **Каналы группы + source_type** (#16) — миграция Channel модели
  + UI. ~4-6 ч.
- **Waterfall в Unit-экономике** (#18) — ~3-4 ч.

Полный список — `docs/CLIENT_FEEDBACK_v2_DECISIONS.md` секция "Фаза C".

---

## 4. Технические напоминания

### Docker

- Стенд: `infra/docker-compose.dev.yml`
- Порт 5432 — **photobooth-pg больше нет** (удалён в этой сессии).
  Если docker отказывается стартовать с конфликтом 5432 — ищите
  что-то новое, в этом репо чисто.
- Иногда postgres контейнер не подключается к сети сразу после `up -d`:
  ```
  docker compose down
  docker network prune -f
  docker compose up -d
  ```

### Тесты

```bash
# Backend, без интеграции с реальным Polza API
docker compose -f infra/docker-compose.dev.yml exec backend \
    pytest -q --ignore=tests/integration

# Только acceptance GORJI (4 теста, ~20 сек)
docker compose -f infra/docker-compose.dev.yml exec backend \
    pytest -q -m acceptance

# Frontend type check (обязательно перед коммитом)
docker compose -f infra/docker-compose.dev.yml exec frontend \
    npx tsc --noEmit
```

### Миграции

```bash
docker compose -f infra/docker-compose.dev.yml exec backend alembic upgrade head
docker compose -f infra/docker-compose.dev.yml exec backend alembic current
```

Последняя миграция: `e5f6a7b8c9d0` (B.9 capex_items).

### Полезные точки в коде

| Файл | Что внутри |
|---|---|
| `backend/app/engine/steps/s03_cogs.py` | COGS с per-period production_mode + 3 уровня BOM |
| `backend/app/engine/context.py` | PipelineInput dataclass — все поля engine |
| `backend/app/services/calculation_service.py:_build_line_input` | Строит PipelineInput из БД |
| `backend/app/services/financial_plan_service.py` | replace_plan + list_plan_by_year (целевая точка B.9b) |
| `frontend/components/projects/financial-plan-editor.tsx` | UI финплана (целевая точка B.9b) |
| `frontend/components/projects/year-override-editor.tsx` | Generic-редактор JSONB годового override |

---

## 5. Правила, которые легко забыть

Из `CLAUDE.md` и `memory/`:

- **Frontend checklist перед коммитом:** `npx tsc --noEmit` обязателен.
  HTTP 200 ≠ работает; tsc ловит undefined refs.
- **При структурных изменениях UI** (новый import / JSX блок) —
  делать full restart frontend контейнера с очисткой `.next`
  (Windows+Docker HMR баг).
- **JSONB mutation:** `flag_modified(obj, "field")` обязателен после
  изменения вложенного dict/list внутри JSONB колонки.
- **Excel = источник истины** (ADR-CE-01). Все D-XX финальные, не
  пересматриваем без явного запроса.
- **Деплой:** только локально → GitHub → сервер. Не редактировать
  на сервере. Деплой только по команде пользователя.

---

## 6. Финальная проверка готовности

Должно выполниться без ошибок:

```bash
git status                           # clean
git log --oneline -1                 # df012a6 docs: обновить план Фаз A/B/C
docker compose -f infra/docker-compose.dev.yml ps
# Все 6 контейнеров healthy / running

docker compose -f infra/docker-compose.dev.yml exec backend alembic current
# Должно быть: e5f6a7b8c9d0 (head)

docker compose -f infra/docker-compose.dev.yml exec backend \
    pytest -q --ignore=tests/integration | tail -3
# 472 passed

docker compose -f infra/docker-compose.dev.yml exec frontend \
    npx tsc --noEmit
# (без output = ок)
```

Если всё зелёное — можно стартовать.
