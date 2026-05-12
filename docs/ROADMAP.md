# DB2 Roadmap

Открытые задачи и backlog. История фаз (что закрыто, как, какими
коммитами) — в [`archive/IMPLEMENTATION_PLAN_v1.md`](archive/IMPLEMENTATION_PLAN_v1.md).

**Текущая prod-версия:** `v2.4.0` (2026-04-15).
**Последний раунд комментариев заказчика:** [CLIENT_FEEDBACK_v2.md](CLIENT_FEEDBACK_v2.md)
(MEMO от 2026-04-23) — он перекрывает большую часть открытого backlog'а.

---

## Что закрыто (краткая хронология)

| Фаза | Закрыта | Артефакт |
|---|---|---|
| 0. Фундамент (структура, Docker, БД-схема, seed) | 2026-04-08 | 7 коммитов |
| 1. Backend CRUD API (auth, projects, SKU, BOM, channels, period values, scenarios) | 2026-04-08 | 6 коммитов, 66 тестов, 37 endpoints |
| 2. Расчётное ядро (s01..s12, Celery, predict) | 2026-04-08 | 6 коммитов, 185 тестов |
| 3. Frontend ввод (auth UI, projects, SKU/BOM, каналы) | 2026-04-08 | 4 коммита |
| 4. Frontend результаты (периоды grid, KPI, сценарии, чувствительность) | 2026-04-09 | 5 коммитов, 217 тестов |
| 4.5. Контент паспорта (data + media storage + UI) | 2026-04-09 | 4 коммита |
| 5. Экспорт XLSX / PPT / PDF | 2026-04-09 | 3 коммита, 278 тестов |
| 6.1. E2E acceptance (GORJI drift < 5%) | 2026-04-09 | 1 коммит |
| 6.2. CI/CD + production Dockerfiles + GHCR | 2026-04-10 | release v0.1.0 |
| 7. AI-интеграция (Polza, explain KPI, sensitivity, executive summary, cost monitoring, content generation, package mockups) | 2026-04-10..11 | 7.7 marketing research — открыт, см. ниже |
| 8. Presentation parity (pricing, value chain, per-unit metrics, P&L tabs, Gate Timeline, Nielsen, supplier quotes) | 2026-04-11 | release v0.3.0, 444 тестов, 16 PPT слайдов |
| 9 (audit remediation v2.4.0). Engine quick wins (4.1 loss carryforward, 4.3 validation, 4.4 fractional payback, 4.5 scenario deltas), staleness invalidation, security (S-01..S-04), демо-полиш UI | 2026-04-15 | release v2.4.0, 469 тестов, 3 миграции |

См. `CHANGELOG.md` для последних 2 релизов, `docs/releases/` для старых.

---

## Открыто сейчас

### Главный документ — CLIENT_FEEDBACK_v2 (MEMO от 2026-04-23)

[`CLIENT_FEEDBACK_v2.md`](CLIENT_FEEDBACK_v2.md) — 14 пунктов
с приоритетами заказчика. **Перед началом работы — пройти
аудит "что уже сделано в коде vs пункты MEMO"** (результат — в
`docs/MEMO_v2.1_STATUS.md`, создаётся в Шаге 2 чистки).

**4 блокера в Блоке 1.3** (требуют ответа заказчика до изменения движка):
- Что означает `production_mode` (копакинг / своё) — как используется в расчётах сейчас
- Что означает поле "Источник" в разделе Согласующие
- MOQ — справочно или влияет на расчёт
- OBPPC — перенести из Дистрибуции в Содержание (риск миграции данных)

### Phase 8 carry-over (низкий приоритет)

- **XLSX квартальный лист** — frontend agregate Q1-Q4 уже есть, в Excel
  exporter добавить отдельный sheet. Не блокер.
- **PPT/PDF цветные ячейки в числовых таблицах** — сейчас цвета только
  в Go/No-Go badge. Через `python-pptx cell.fill.solid()` — не критично.
- **Связка КП ↔ BOM items** — сейчас `supplier_quotes` отдельный JSONB.
  Привязка к конкретной BOM-позиции — будущая фаза.

### Phase 7.7 — AI marketing research

Web search через Polza AI. Точный API формат неясен (Anthropic native
tool / Polza `extra_body` / query flag). Уточнить через
`polza.ai/openapi.json` или support перед реализацией.

### Технические долги

- **Flaky `test_explain_sensitivity_cache_hit`** (см. ERRORS_AND_ISSUES
  2026-04-14) — async pool exhaustion в конце suite. Не блокер релизов.
- **D-12 рассинхрон** — в `s11_kpi.py:50` `SCOPE_BOUNDS["y1y5"] = (5, 5)`
  с комментарием "fix 6→5", но docstring выше говорит "реализуем как
  в Excel 6 столбцов". Уточнить актуальное намерение перед изменениями
  в этой логике.

### Smoke-тесты Phase 8 endpoint'ов (карри-овер)

Lazy import bug в pnl_endpoint показал что новые endpoint'ы попадают
в prod без покрытия. Нужны 200 OK smoke-тесты для:
- `GET /api/projects/{id}/pricing-summary`
- `GET /api/projects/{id}/value-chain`
- `GET /api/projects/{id}/pnl`
- `PATCH /api/projects/{id}` с `nielsen_benchmarks` / `supplier_quotes`

---

## Backlog (низкий приоритет, не блокирует)

### Из MVP scope (B-XX)

| # | Приоритет | Описание |
|---|---|---|
| B-01 | 🟠 P1 | Мультипользователь / роли (Keycloak — Этап 2) |
| B-03 | 🟡 P2 | Агрегация портфеля департамента (= BL-10) |
| B-08 | 🟡 P2 | Согласование / approval flow (связан с B-01) |
| B-09 | 🟢 P3 | Интеграция с 1С / BI-кубами |
| B-14 | 🟠 P1 | MFA / SSO / LDAP (с Keycloak) |
| B-17 | 🟢 P3 | Batch save для period values |
| B-18 | 🟡 P2 | Corporate PPT template от дизайнера |

### Из Phase 9 backlog (BL-XX, источник CLIENT_FEEDBACK_v1)

Многие пересекаются с MEMO v2.1 — проверять при аудите.

| # | Приоритет | Описание |
|---|---|---|
| BL-01..02 | 🟡 P2 | Импорт через Excel + предиктивные шаблоны Nielsen |
| BL-03 | 🟡 P2 | Группы каналов + кастомный канал (= MEMO 4.1) |
| BL-04 | 🟡 P2 | Фильтры P&L / pivot (= MEMO 6.1) |
| BL-05 | 🟢 P3 | Waterfall chart в Стакане (= MEMO 6.3) |
| BL-07 | 🟡 P2 | CA&M/Marketing per-channel (= MEMO 3.2 второй пункт) |
| BL-08 | 🟡 P2 | Ступенчатая себестоимость (= MEMO 5.2) |
| BL-09 | 🟡 P2 | План продаж / план АКБ детальный |
| BL-10 | 🟠 P1 | Агрегация проектов (= B-03, = MEMO 6.5) |
| BL-11 | 🟡 P2 | Копии и группировка проектов |
| BL-12 | 🟢 P3 | OBPPC → Содержание (= MEMO 1.3) |
| BL-13 | 🟢 P3 | Сценарии → Анализ/Результаты (= MEMO 5.3) |
| BL-14 | 🟡 P2 | Fine tuning всех показателей (= MEMO 5.1) |
| BL-15 | 🟢 P3 | Фильтрация SKU по доп. атрибутам |
| BL-16 | 🟢 P3 | Предиктивный шаблон CAPEX по типу производства |

### Логика (LOGIC-XX) — из CLIENT_FEEDBACK_v1

| # | Описание | Статус |
|---|---|---|
| LOGIC-01 | Copacking в расчётах (`production_mode: own/copacking`) | Частично в коде (есть миграция, см. MEMO 1.3 + 7.1.1 — аудит) |
| LOGIC-02 | Go/No-Go порог настраиваемый | ✅ Сделано (миграция `32c6c1bd0abf`) |
| LOGIC-03 | CAPEX детализация по статьям + M1-M36 | Открыто (= MEMO 2.1) |
| LOGIC-04 | Sensitivity по горизонтам Y1-Y3/Y5/Y10 | Открыто (= MEMO 6.2) |
| LOGIC-06 | P&L структура как DATA в Excel | Открыто (= MEMO 6.1) |
| LOGIC-07 | Per-ingredient НДС (10/22/0%) | Открыто (= MEMO 3.3) |
| LOGIC-08 | D-12 Y1-Y5 уточнение у заказчика | Открыто (см. "Технические долги") |

---

## Раздел 0 MVP scope, ADR-критерии и зависимости фаз

В архивированном [`archive/IMPLEMENTATION_PLAN_v1.md`](archive/IMPLEMENTATION_PLAN_v1.md).
Не нужно для текущей разработки — оставлено для истории.
