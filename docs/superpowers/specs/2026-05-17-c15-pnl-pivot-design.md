# C #15 — P&L фильтры + pivot Excel (design)

> **Brainstorm session:** 2026-05-17 (compressed)
> **Источник:** MEMO 1.4 / BL-#15.
> **Scope:** Pragmatic — Excel pivot sheet (per-line breakdown) + frontend filters в P&L view. Большой эпик урезан до минимально полезного.

---

## §1. Цель

1. **Excel pivot sheet** — новый лист «P&L Pivot» в существующем Excel экспорте: per-line breakdown (SKU × Channel × Period × P&L метрики). Юзер открывает в Excel → строит свои pivot tables / фильтры нативными tools.
2. **Frontend filters в P&L view** — toggles для группировки/фильтрации (по SKU / Channel / Group). Минимальный UI без новых endpoints.

### §1.1 User story

«Я хочу выгрузить P&L в Excel и сам построить pivot по своим срезам (SKU × period, channel_group × year, etc). Сейчас экспорт даёт мне агрегированный P&L — это не годится для глубокого анализа».

---

## §2. Out of scope

| Что | Почему |
|---|---|
| Кастомные pivot tables в Excel (xlsxwriter pivot API) | Слишком хрупко. Просто raw data — юзер построит сам. |
| Backend pivot endpoint с фильтрами | Excel экспорт даёт все строки → юзер фильтрует в Excel. Frontend filters работают на уже-agreed P&L (не per-line). |
| Помесячная агрегация по SKU + period | Per-line данные доступны в pipeline output → выгружаются как есть. |
| Кастомные сводки в frontend (новая страница «Pivot Analysis») | YAGNI. |
| Сохранение фильтров между сессиями | Можно localStorage если просто; иначе skip. |

---

## §3. Текущее состояние

### Backend
- `GET /api/projects/{id}/pnl` → `PnlResponse` (агрегат per-period, 43 строки, без SKU/Channel разреза).
- `excel_exporter.py` имеет `_build_pnl_sheet` — current P&L sheet (агрегат).
- Pipeline через `run_project_pipeline` агрегирует по всем PSC. Per-line данные есть в `aggregator.py` промежуточно (но не сохраняются в Pydantic response).

### Frontend
- `frontend/components/projects/pnl-tab.tsx` — рендерит P&L таблицу с toggle Month/Quarter/Year.
- Нет filters / разрезов.

---

## §4. Дизайн

### §4.1 Excel Pivot sheet — per-line breakdown

Новый sheet «P&L Pivot» в `excel_exporter.py`. Структура: одна строка на каждую комбинацию (SKU × Channel × Period). 43 периода × N SKU × M каналов = до ~тысяч строк.

Колонки:
| Колонка | Источник |
|---|---|
| SKU brand | `sku.brand` |
| SKU name | `sku.name` |
| SKU format | `sku.format` |
| SKU volume | `sku.volume_l` + unit_of_measure |
| Channel code | `channel.code` |
| Channel name | `channel.name` |
| Channel group | `channel.channel_group` (C #16) |
| Channel source_type | `channel.source_type` (C #16) |
| Period label | M1..Y10 |
| Period type | monthly/annual |
| Model year | 1..10 |
| Month num | 1..12 / None |
| Quarter | 1..4 / None |
| Volume units | per (PSC × period) |
| Volume liters | |
| Net revenue | |
| COGS material | |
| COGS production | |
| COGS total | |
| Gross profit | |
| Logistics | |
| Contribution | |
| CA&M | |
| Marketing | |
| EBITDA | |

Источник данных — `run_project_pipeline` уже считает per-line. Нужно вытащить per-line aggregate (LineOutput.periods) перед aggregation в total.

В `excel_exporter` функция `_build_pnl_pivot_sheet`:
```python
def _build_pnl_pivot_sheet(
    wb, sheet, project, scenario_outputs, ...
):
    """Per-line breakdown: SKU × Channel × Period × P&L metrics."""
    # Headers (23 columns)
    # For each LineOutput in scenario.line_outputs:
    #   sku = line_output.sku
    #   channel = line_output.channel
    #   for period in line_output.periods:
    #     row = [sku.brand, sku.name, ..., period.net_revenue, ...]
    #     ws.append(row)
```

### §4.2 Frontend filters

В `pnl-tab.tsx` — pragmatic minimum:
- Информационный hint: «Для разреза по SKU/каналу — экспортируйте Excel, лист P&L Pivot»
- Можно ничего больше не добавлять; экспорт делает всю работу

Альтернативно (если есть запас контекста): добавить локальные filters для скрытия некоторых row'ов в текущей таблице (по period type или году). Skip для MVP.

### §4.3 Tests

Backend:
- `test_pnl_pivot_sheet_has_per_line_rows` — экспорт содержит лист «P&L Pivot» с per-line данными
- `test_pnl_pivot_sheet_column_count` — 23 колонки в headers

### §4.4 Docs

CHANGELOG + GO5 sync (18/19 ✅, 0 open!).

---

## §5. Plan skeleton (2 задачи)

| # | Задача | Файлы |
|---|---|---|
| T1 | Backend: новый `_build_pnl_pivot_sheet` в excel_exporter + 2 теста | excel_exporter.py, test_export_xlsx.py |
| T2 | docs + merge (frontend hint optional если время) | CHANGELOG, GO5 |

Branch: `feat/c15-pnl-pivot-excel`. Tag: `v2.7.0` (Phase C complete).
