# К диагностике в фазе тестирования

Список технических вопросов, которые **сами разберём при прогоне
демо** — заказчику задавать не нужно. Создан 2026-05-12 при подготовке
вопросника после аудита MEMO v2.1.

Когда выйдем на фазу тестирования (после ответов клиента на блокеры) —
проходимся по этому списку и закрываем.

---

## D-1. Экспорт XLSX / PPTX / PDF (MEMO 6.4)

**Заявка заказчика:** "Экспорт не работает" — приоритетный баг.

**Что в коде:**
- `backend/app/export/excel_exporter.py`, `ppt_exporter.py`,
  `pdf_exporter.py` — все три на месте
- Endpoints: `GET /api/projects/{id}/export/{xlsx|pptx|pdf}` — есть
- Последний фикс v0.1.0 (2026-04-10): Cyrillic filenames через
  RFC 5987, volume mount исправлен на /app/media

**Гипотеза:** в коде всё на месте, "не работает" может относиться к:
- (а) конкретному проекту с битыми данными (NULL в required-полях?)
- (б) браузерному поведению (Chrome блок download без user gesture?)
- (в) большому payload (timeout? memory?)
- (г) реальной регрессии (надо воспроизвести)

**Что проверить при тестировании:**
1. Открыть `https://db2.medoed.work`, попробовать все три экспорта
   на нескольких проектах
2. Если падает — network tab (F12 → Network), смотреть status code
   и response body endpoint'а
3. Если "скачивается пустой" — backend logs
   (`docker compose logs backend`)
4. Если "ничего не происходит" — frontend console errors

---

## D-2. Финплан intermittent save error (MEMO 1.1)

**Заявка заказчика:** "При попытке сохранить после внесения данных
в CAPEX/OPEX иногда выдаётся ошибка."

**Что в коде:**
- `backend/app/services/financial_plan_service.py:replace_plan` —
  `DELETE` + `INSERT` + `flush`
- `frontend/components/projects/financial-plan-editor.tsx:174` —
  sanitize layer пытается чинить пустые строки в Number()

**Гипотеза:** payload не сохраняется правильно при определённом
паттерне:
- (а) Пустые строки в полях CAPEX/OPEX (`""` vs `null` vs `0`)
- (б) Десинхрон между `opex_total` (scalar) и `opex_items` (массив)
- (в) Race condition при двойном клике "Сохранить"

**Что проверить:**
1. Добавить серверное логирование payload в `replace_plan` (одна
   строка `logger.info("plan payload: %s", payload)`) — раскоментить
   на dev, поймать
2. Воспроизвести через UI: пустые строки, частичные данные, быстрый
   двойной клик
3. Тест с граничными значениями (CAPEX=0 — см. D-3)

---

## D-3. CAPEX = 0 краш (MEMO 1.1)

**Заявка заказчика:** "При обнулении поля CAPEX приложение падает."

**Что в коде:**
- Frontend `financial-plan-editor.tsx:201` — `Number(i.capex || 0)`,
  на фронте 0 принимается
- Backend `replace_plan` — поле Numeric, принимает 0 без проверок
- Engine: где CAPEX делится? `s09_cash_flow.py` использует
  `agg.investing_cash_flow[t] -= project_capex[t]` — деления нет
- KPI: payback и IRR могут падать, если все FCF положительные?

**Гипотеза:** падение скорее всего:
- (а) Не в backend, а в frontend графике (Recharts с пустыми сериями)
- (б) В payback расчёте при отсутствии negative FCF
- (в) В ROI Excel-формуле `(−SUM/(SUMIF<0 − 1))` — `SUMIF<0` = 0
  → знаменатель = `-1`, не делится на ноль, но даёт странный знак

**Что проверить:**
1. Локально создать проект с CAPEX=0 во всех годах, прогнать
   `pytest -m acceptance` — упадёт?
2. Frontend: открыть проект, ввести 0 в CAPEX — что в console?
3. Если падает в Recharts — добавить `if (data.length === 0) return null`

---

## D-4. RoadMap Gantt не перестраивается (MEMO 1.1)

**Заявка заказчика:** "Шкала Гантт-графика не перестраивается при
смене статуса задачи."

**Что в коде:**
- `frontend/components/projects/gantt-chart.tsx` рендерит цвет
  через `STATUS_COLORS[entry.status]`
- Roadmap данные хранятся в `Project.roadmap_tasks` JSONB

**Гипотеза:** React не видит mutation внутри JSONB массива. Типичная
проблема — `tasks[i].status = "done"` вместо `setTasks([...tasks, ...])`.

**Что проверить:**
1. Найти где меняется статус в `gantt-chart.tsx` или родителе
2. Убедиться что новый массив создаётся (immutable update)
3. Если backend mutation — проверить `flag_modified(project, "roadmap_tasks")`

---

## D-5. Изображения SKU не загружаются (MEMO 3.1)

**Заявка:** "Изображение SKU не загружается."

**Что в коде:**
- `backend/app/api/media.py` — POST /api/projects/{id}/media
- v0.1.0 фиксил permissions (root→appuser) и Cyrillic filenames
- MinIO в docker — для S3-compatible хранения

**Гипотеза:** скорее всего env-проблема (MEDIA_DIR, MinIO creds)
или регрессия после server migration на 85.239.63.206.

**Что проверить:**
1. Network tab: какой response при upload (400/500/CORS)
2. Backend logs во время upload
3. `infra/.env` на prod — MEDIA_DIR указан?

---

## D-6. Логo upload верстка (MEMO 3.1)

**Заявка:** "Ошибка верстки при загрузке лого."

**Что:** UI/CSS проблема. Проверить через DevTools после load.

---

## D-7. Ошибка в Сценариях периодическая (MEMO 5.3, BUG-05 v1)

**Заявка:** "Ошибка периодически появляется при работе со сценариями."

**Гипотеза:** race condition при polling task status, или Celery task
fails intermittently. Возможно связано с известным flaky тестом
`test_explain_sensitivity_cache_hit` (async pool exhaustion).

**Что проверить:**
1. Backend logs при последовательных recalc
2. Celery worker logs — task SUCCESS/FAILURE pattern
3. Frontend `pollTaskStatus` — корректно обрабатывает FAILURE?

---

## D-8. SKU удаление каскад при удалении проекта (MEMO 3.1)

**Заявка:** "При удалении проекта SKU в каталоге не удаляются."

**Уточнение:** это might be **намеренное поведение** — SKU справочник
не привязан к проекту, переиспользуется. Связь через `ProjectSKU`
(join table).

**Что проверить:**
- (а) Подтвердить, что удаление проекта корректно делает soft-delete
  ProjectSKU, но не SKU из справочника
- (б) Если заказчик хочет — добавить чекбокс "удалить SKU из каталога
  тоже"

Может быть UX-вопрос, не баг.

---

## Прочие технические дёрги при тестировании

- Flaky `test_explain_sensitivity_cache_hit` (async pool) — известно,
  не блокер
- Port 5432 conflict с `photobooth-pg` на dev-машине — нужно либо
  стопать чужой контейнер, либо убирать port mapping в
  `docker-compose.dev.yml`
- D-12 docstring рассинхрон в `s11_kpi.py` — после ответа клиента
  по горизонту Y1-Y5 синхронизировать docstring с кодом
