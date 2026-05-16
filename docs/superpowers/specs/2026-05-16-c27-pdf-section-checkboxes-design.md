# C #27 — PDF чекбоксы выбора секций (design)

> **Brainstorm session:** 2026-05-16 (compressed per memory `feedback-brainstorm-no-micro-questions`)
> **Источник:** MEMO 1.4 / Block 5.3 / BL-#27.
> **Scope category:** Small feature, UX-only. Backend получает opt-in query param, template conditionally рендерит. Frontend получает диалог-выбор.

---

## §1. Цель

Дать юзеру опционально исключать секции из PDF-экспорта. Текущее поведение (16 секций всегда) сохраняется как default — если param опущен.

User story: «Я хочу экспорт только для PnL+KPI без титульного листа и согласующих — для презентации внутри команды».

---

## §2. Out of scope

| Что | Почему |
|---|---|
| Pre-set наборы секций («только финансовый», «только продуктовый») | YAGNI — пусть юзер сам выбирает. |
| Реструктуризация template'а на блоки Jinja `{% block %}` | Текущий монолит работает; conditional `{% if %}` достаточно. |
| Per-user сохранение выбранных секций на backend | LocalStorage в браузере хватит для MVP. |
| Изменение PPTX/XLSX экспортёров | Отдельный feature если попросят. |
| Custom порядок секций | Out of scope — фиксированный порядок template'а. |
| Custom titles/изменение содержимого секций | Out of scope. |

---

## §3. Текущее состояние

### Backend
- `backend/app/api/projects.py:515-564` — endpoint `GET /api/projects/{id}/export/pdf` без query params, всегда генерирует весь PDF.
- `backend/app/export/pdf_exporter.py:421+` — `generate_project_pdf(session, project_id) -> bytes` без параметризации секций.
- `backend/app/export/templates/project_passport.html` — 16 секций (`<div class="section">`), без conditional rendering.

### Frontend
- Кнопка «Экспорт PDF» где-то в проекте: триггерит download `/api/projects/{id}/export/pdf`. Поиск выявит точное место.

---

## §4. Дизайн

### §4.1 Section catalog

Один источник истины — `backend/app/export/pdf_sections.py`:

```python
from typing import Literal

SectionId = Literal[
    "title",            # титул (без h2, всегда первая)
    "general",          # 1. Общая информация
    "concept",          # 2. Концепция продукта
    "tech",             # 3. Технология и обоснование
    "validation",       # 4. Результаты валидации
    "product_mix",      # 5. Продуктовый микс (с package images)
    "macro",            # 6. Финансовая модель — макро-факторы
    "kpi",              # 7. Ключевые KPI
    "pnl",              # 8. PnL по годам
    "sensitivity",      # Анализ чувствительности
    "pricing",          # Цены: полка / ex-factory / COGS
    "unit_econ",        # Стакан: per-unit экономика
    "cost_stack",       # 9. Стакан себестоимости и фин-план
    "risks",            # 10. Риски и готовность функций
    "roadmap",          # 11. Дорожная карта и согласующие
    "market",           # Рынок и поставки
    "executive_summary",# 12. Executive Summary
]

ALL_SECTIONS: tuple[SectionId, ...] = (
    "title", "general", "concept", "tech", "validation",
    "product_mix", "macro", "kpi", "pnl", "sensitivity",
    "pricing", "unit_econ", "cost_stack", "risks", "roadmap",
    "market", "executive_summary",
)

SECTION_LABELS: dict[SectionId, str] = {
    "title": "Титульный лист",
    "general": "1. Общая информация",
    "concept": "2. Концепция продукта",
    "tech": "3. Технология и обоснование",
    "validation": "4. Результаты валидации",
    "product_mix": "5. Продуктовый микс",
    "macro": "6. Макро-факторы",
    "kpi": "7. Ключевые KPI",
    "pnl": "8. PnL по годам",
    "sensitivity": "Анализ чувствительности",
    "pricing": "Цены: полка/ex-factory/COGS",
    "unit_econ": "Стакан: per-unit экономика",
    "cost_stack": "9. Стакан себестоимости + фин-план",
    "risks": "10. Риски и готовность функций",
    "roadmap": "11. Дорожная карта",
    "market": "Рынок и поставки",
    "executive_summary": "12. Executive Summary",
}
```

17 секций (титул как отдельная controllable секция). 17 — потому что title — отдельная opt-out возможность («не нужен титульный лист»).

### §4.2 Endpoint

Расширить `GET /api/projects/{id}/export/pdf?sections=kpi,pnl`:
- Если param опущен → `active_sections = set(ALL_SECTIONS)` (current behavior).
- Если param пустая строка `?sections=` → 422 «Укажите хотя бы одну секцию».
- Если param с valid IDs → `active_sections = set(parsed)`.
- Невалидные IDs (например `?sections=xyz`) → 422 со списком invalid.

Filename меняется: если выбраны не все секции — суффикс `_partial` (`project-N_2026-05-16_partial.pdf`).

### §4.3 Template conditional rendering

Каждая `<div class="section">` оборачивается:
```jinja
{% if 'general' in active_sections %}
<div class="section">
  <h2>1. Общая информация</h2>
  ...
</div>
<div class="page-break"></div>
{% endif %}
```

`{# Title #}` без h2 — обернётся аналогично с `'title' in active_sections`.

`active_sections: set[SectionId]` — передаётся в Jinja context, считается через `pdf_exporter.generate_project_pdf(session, project_id, sections=set_of_ids)`.

### §4.4 Frontend

**Section catalog mirror** (`frontend/lib/pdf-sections.ts`):
```typescript
export type PdfSectionId = "title" | "general" | ...;  // те же 17
export const PDF_SECTION_ORDER: PdfSectionId[] = [...];
export const PDF_SECTION_LABELS: Record<PdfSectionId, string> = {...};
```

**`PdfExportDialog`** компонент:
- Открывается по клику на кнопку «Экспорт PDF» (текущая кнопка триггерит download — теперь она открывает диалог)
- 17 чекбоксов в одной колонке, все checked по умолчанию
- Кнопки «Выбрать всё» / «Снять всё»
- Сохраняет последнюю конфигурацию в `localStorage` key `pdf-export-sections-v1` (массив выбранных IDs)
- При первом открытии — все checked
- Кнопка «Скачать PDF» → формирует URL с `?sections=...&token=...` (или скачивает blob через fetch с auth header) → trigger download
- Disabled когда 0 чекбоксов

**Где живёт диалог**: единый компонент `frontend/components/projects/pdf-export-dialog.tsx`, открывается из текущего места кнопки экспорта (найти grep'ом).

### §4.5 Tests

Backend:
- `test_pdf_export_all_sections` (no sections param → all 17 sections present in HTML before render OR file size = baseline)
- `test_pdf_export_subset_sections` (sections=kpi,pnl → only those 2 + title (если в списке) present)
- `test_pdf_export_empty_sections_422`
- `test_pdf_export_invalid_section_422`

Frontend:
- tsc --noEmit clean
- Manual smoke

### §4.6 CHANGELOG / docs

Стандартный formato в Unreleased + GO5 (отметка #27 ✅).

---

## §5. Plan skeleton (3 задачи)

| # | Задача | Файлы | Модель |
|---|---|---|---|
| T1 | Backend: section catalog + endpoint param + template conditionals + 4 теста | `pdf_sections.py` (new), `pdf_exporter.py`, `templates/project_passport.html`, `projects.py` endpoint, `tests/api/test_export_pdf.py` | sonnet |
| T2 | Frontend: section catalog mirror + PdfExportDialog + wire button | `lib/pdf-sections.ts` (new), `components/projects/pdf-export-dialog.tsx` (new), edit existing export button location | sonnet |
| T3 | Smoke + CHANGELOG + GO5 status + merge --no-ff | docs + verification | sonnet |

Branch: `feat/c27-pdf-section-checkboxes`.

---

## §6. Открытые вопросы

Нет. Все решения зафиксированы.
