# C #27 — PDF чекбоксы выбора секций (implementation plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Compact 3-task план (small feature).

**Goal:** Дать PDF endpoint опциональный query param `sections=...`, обернуть каждую template секцию в `{% if ... %}`, добавить frontend dialog с чекбоксами для выбора.

**Spec:** `docs/superpowers/specs/2026-05-16-c27-pdf-section-checkboxes-design.md`.
**Branch:** `feat/c27-pdf-section-checkboxes` (создана от main).
**Baseline:** main `2224a4f` (после C #16 merge), pytest 545 passed, alembic head `eb59341b9034`, tsc clean.

---

## Контекст для исполнителя

### Файлы PDF flow
- `backend/app/api/projects.py:515-564` — endpoint
- `backend/app/export/pdf_exporter.py:421+` — `generate_project_pdf(session, project_id)` 
- `backend/app/export/templates/project_passport.html` — 16 `<div class="section">` + 1 title block
- `backend/tests/api/test_export_pdf.py` — тесты экспорта (если есть) / создать

### Frontend
- Текущая кнопка PDF-экспорта — найти через `grep -r "export/pdf\|Экспорт PDF" frontend/`
- Будет переписана в open-dialog action

### Команды
```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration | tail -3
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q tests/api/test_export_pdf.py -v
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```

---

## Task 1: Backend — section catalog + endpoint + template + tests

**Files:**
- Create: `backend/app/export/pdf_sections.py`
- Modify: `backend/app/export/pdf_exporter.py` (signature + jinja context)
- Modify: `backend/app/export/templates/project_passport.html` (17 conditional blocks)
- Modify: `backend/app/api/projects.py` (endpoint accepts `sections` query param + validation)
- Create or modify: `backend/tests/api/test_export_pdf.py` (4 tests)

### Шаги

- [ ] **Step 1: Создать `backend/app/export/pdf_sections.py`**

```python
"""C #27: catalog of PDF sections для selective export."""
from typing import Literal

SectionId = Literal[
    "title",
    "general",
    "concept",
    "tech",
    "validation",
    "product_mix",
    "macro",
    "kpi",
    "pnl",
    "sensitivity",
    "pricing",
    "unit_econ",
    "cost_stack",
    "risks",
    "roadmap",
    "market",
    "executive_summary",
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


def parse_sections(raw: str | None) -> set[SectionId]:
    """Parse query param value → set of SectionId.

    None → all sections (current behavior).
    "" → ValueError (empty list — endpoint maps to 422).
    "kpi,pnl" → {"kpi","pnl"}.
    Invalid IDs → ValueError со списком invalid.
    """
    if raw is None:
        return set(ALL_SECTIONS)
    parts = [s.strip() for s in raw.split(",") if s.strip()]
    if not parts:
        raise ValueError("sections must contain at least one ID")
    invalid = [p for p in parts if p not in ALL_SECTIONS]
    if invalid:
        raise ValueError(f"Invalid section IDs: {sorted(invalid)}")
    return set(parts)  # type: ignore[arg-type]
```

- [ ] **Step 2: Расширить `generate_project_pdf` сигнатуру**

В `backend/app/export/pdf_exporter.py:421+`:
```python
async def generate_project_pdf(
    session: AsyncSession,
    project_id: int,
    sections: set[SectionId] | None = None,
) -> bytes:
    """...
    
    Args:
        sections: subset of SectionId to include. None = all 17.
    """
    from app.export.pdf_sections import ALL_SECTIONS, SectionId
    if sections is None:
        sections = set(ALL_SECTIONS)
    # ...загрузка данных как сейчас...
    
    # В render context добавить:
    context["active_sections"] = sections
    
    # ...render как сейчас...
```

Импорт `SectionId` тоже в начале файла.

- [ ] **Step 3: Обернуть 17 секций в template'е**

В `backend/app/export/templates/project_passport.html` каждый `<div class="section">` (16 штук) + title block (1) обернуть:

```jinja
{# Title — обернуть существующий блок выше первого <div class="section"> #}
{% if 'title' in active_sections %}
... existing title HTML ...
<div class="page-break"></div>
{% endif %}

{# Каждая секция: #}
{% if 'general' in active_sections %}
<div class="section">
  <h2>1. Общая информация</h2>
  ...
</div>
<div class="page-break"></div>
{% endif %}
```

Соответствие section ID → существующая секция в шаблоне:
- `title` → блок перед строкой 267 (`<div class="page-break">` на 262 — часть title?)
- `general` → строка 267 (`1. Общая информация`)
- `concept` → 328 (`2. Концепция`)
- `tech` → 367 (`3. Технология`)
- `validation` → 392 (`4. Результаты валидации`)
- `product_mix` → 424 (`5. Продуктовый микс`)
- `macro` → 469 (`6. Макро-факторы`)
- `kpi` → 490 (`7. Ключевые KPI`)
- `pnl` → 550 (`8. PnL по годам`)
- `sensitivity` → 582 (`Анализ чувствительности`)
- `pricing` → 621 (`Цены`)
- `unit_econ` → 687 (`Стакан per-unit`)
- `cost_stack` → 738 (`9. Стакан себестоимости`)
- `risks` → 801 (`10. Риски`)
- `roadmap` → 846 (`11. Дорожная карта`)
- `market` → 899 (`Рынок и поставки`)
- `executive_summary` → 968 (`12. Executive Summary`)

⚠ ВАЖНО: перед написанием — прочитать актуальный template, проверить что строки соответствуют. Структура может слегка отличаться. Использовать grep по `<h2>` для подтверждения.

- [ ] **Step 4: Расширить endpoint `export_project_pdf_endpoint`**

В `backend/app/api/projects.py:526+`:
```python
@router.get(
    "/{project_id}/export/pdf",
    responses={...},
)
@limiter.limit("20/minute")
async def export_project_pdf_endpoint(
    request: Request,
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    sections: str | None = Query(
        default=None,
        description="Comma-separated section IDs (e.g. 'kpi,pnl'). Omit для всех секций.",
    ),
) -> StreamingResponse:
    from io import BytesIO
    from app.export.excel_exporter import ProjectNotFoundForExport
    from app.export.pdf_exporter import generate_project_pdf
    from app.export.pdf_sections import ALL_SECTIONS, parse_sections

    try:
        active = parse_sections(sections)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    try:
        pdf_bytes = await generate_project_pdf(session, project_id, sections=active)
    except ProjectNotFoundForExport:
        raise _not_found

    project = await project_service.get_project(session, project_id, user=current_user)
    is_partial = active != set(ALL_SECTIONS)
    suffix = "_partial" if is_partial else ""
    content_disposition = _build_export_content_disposition(
        project, project_id, f"{suffix}.pdf"
    )
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disposition,
            "Content-Length": str(len(pdf_bytes)),
        },
    )
```

Если `_build_export_content_disposition` принимает только `.pdf` — адаптировать сигнатуру или построить filename вручную.

- [ ] **Step 5: Добавить 4 теста**

В `backend/tests/api/test_export_pdf.py` (создать если нет):
```python
async def test_pdf_export_all_sections_default(
    auth_client: AsyncClient,
    seed_project,  # фикстура — найти существующую или адаптировать
):
    """C #27: GET без sections param — все 17 секций в PDF."""
    resp = await auth_client.get(f"/api/projects/{seed_project.id}/export/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    # PDF blob → размер не нулевой
    assert len(resp.content) > 1000


async def test_pdf_export_subset_sections(
    auth_client: AsyncClient,
    seed_project,
):
    """C #27: sections=kpi,pnl → меньший PDF, _partial в filename."""
    resp = await auth_client.get(
        f"/api/projects/{seed_project.id}/export/pdf?sections=kpi,pnl"
    )
    assert resp.status_code == 200
    cd = resp.headers["content-disposition"]
    assert "_partial.pdf" in cd
    assert len(resp.content) > 0


async def test_pdf_export_empty_sections_422(
    auth_client: AsyncClient,
    seed_project,
):
    """C #27: ?sections= (пустой) → 422."""
    resp = await auth_client.get(
        f"/api/projects/{seed_project.id}/export/pdf?sections="
    )
    assert resp.status_code == 422


async def test_pdf_export_invalid_section_422(
    auth_client: AsyncClient,
    seed_project,
):
    """C #27: ?sections=invalid_id → 422 со списком."""
    resp = await auth_client.get(
        f"/api/projects/{seed_project.id}/export/pdf?sections=xyz,kpi"
    )
    assert resp.status_code == 422
    assert "xyz" in resp.text
```

Если seed_project фикстуры нет — найти существующую (`grep -n "seed_project\|test_project\|_create_project" backend/tests/`). Альтернатива: создать project через `_create_psk`-стиль helper или использовать `test_seed_data` fixture.

- [ ] **Step 6: Run pytest**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q tests/api/test_export_pdf.py -v
```
Expected: 4 new tests passed. Existing PDF tests still passing.

- [ ] **Step 7: Full pytest verification**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration | tail -3
```
Expected: 549 passed (545 + 4 new).

- [ ] **Step 8: Commit T1**

```bash
git add backend/app/export/pdf_sections.py \
        backend/app/export/pdf_exporter.py \
        backend/app/export/templates/project_passport.html \
        backend/app/api/projects.py \
        backend/tests/api/test_export_pdf.py
git commit -m "feat(c27-t1): PDF endpoint sections= query param + template conditionals

- pdf_sections.py: 17 SectionId (Literal) + ALL_SECTIONS + SECTION_LABELS + parse_sections
- generate_project_pdf принимает sections: set[SectionId] | None
- Template: 17 секций обёрнуты в {% if 'X' in active_sections %}
- Endpoint Query param sections=kpi,pnl — comma-separated
- Filename suffix _partial если выбраны не все секции
- 4 теста: default (все 17), subset, empty 422, invalid 422"
```

---

## Task 2: Frontend — section catalog mirror + PdfExportDialog + wire

**Files:**
- Create: `frontend/lib/pdf-sections.ts`
- Create: `frontend/components/projects/pdf-export-dialog.tsx`
- Modify: wherever the current «Экспорт PDF» button lives (find by grep)

### Шаги

- [ ] **Step 1: Найти текущую PDF-кнопку**

```bash
grep -rn "export/pdf\|Экспорт PDF\|ExportPDF\|exportPdf" frontend/ --include="*.tsx" --include="*.ts"
```

Запомнить файл и строку. Скорее всего в `frontend/components/projects/` или `frontend/app/projects/[id]/`.

- [ ] **Step 2: Создать `frontend/lib/pdf-sections.ts`**

```typescript
/**
 * C #27: PDF section catalog mirror. Источник истины enum —
 * backend `app/export/pdf_sections.py`.
 */

export type PdfSectionId =
  | "title"
  | "general"
  | "concept"
  | "tech"
  | "validation"
  | "product_mix"
  | "macro"
  | "kpi"
  | "pnl"
  | "sensitivity"
  | "pricing"
  | "unit_econ"
  | "cost_stack"
  | "risks"
  | "roadmap"
  | "market"
  | "executive_summary";

export const PDF_SECTION_ORDER: PdfSectionId[] = [
  "title",
  "general",
  "concept",
  "tech",
  "validation",
  "product_mix",
  "macro",
  "kpi",
  "pnl",
  "sensitivity",
  "pricing",
  "unit_econ",
  "cost_stack",
  "risks",
  "roadmap",
  "market",
  "executive_summary",
];

export const PDF_SECTION_LABELS: Record<PdfSectionId, string> = {
  title: "Титульный лист",
  general: "1. Общая информация",
  concept: "2. Концепция продукта",
  tech: "3. Технология и обоснование",
  validation: "4. Результаты валидации",
  product_mix: "5. Продуктовый микс",
  macro: "6. Макро-факторы",
  kpi: "7. Ключевые KPI",
  pnl: "8. PnL по годам",
  sensitivity: "Анализ чувствительности",
  pricing: "Цены: полка/ex-factory/COGS",
  unit_econ: "Стакан: per-unit экономика",
  cost_stack: "9. Стакан себестоимости + фин-план",
  risks: "10. Риски и готовность функций",
  roadmap: "11. Дорожная карта",
  market: "Рынок и поставки",
  executive_summary: "12. Executive Summary",
};

const LS_KEY = "pdf-export-sections-v1";

export function loadSavedSections(): PdfSectionId[] {
  if (typeof window === "undefined") return [...PDF_SECTION_ORDER];
  try {
    const raw = window.localStorage.getItem(LS_KEY);
    if (!raw) return [...PDF_SECTION_ORDER];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [...PDF_SECTION_ORDER];
    const valid = parsed.filter((x): x is PdfSectionId =>
      PDF_SECTION_ORDER.includes(x as PdfSectionId),
    );
    return valid.length > 0 ? valid : [...PDF_SECTION_ORDER];
  } catch {
    return [...PDF_SECTION_ORDER];
  }
}

export function saveSections(sections: PdfSectionId[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LS_KEY, JSON.stringify(sections));
  } catch {
    // localStorage недоступен — игнор
  }
}
```

- [ ] **Step 3: Создать `frontend/components/projects/pdf-export-dialog.tsx`**

```typescript
"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { apiFetch } from "@/lib/api";  // helper для blob с auth
import {
  loadSavedSections,
  saveSections,
  PDF_SECTION_LABELS,
  PDF_SECTION_ORDER,
  type PdfSectionId,
} from "@/lib/pdf-sections";

interface PdfExportDialogProps {
  projectId: number;
  projectName?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function PdfExportDialog({
  projectId,
  projectName,
  open,
  onOpenChange,
}: PdfExportDialogProps) {
  const [selected, setSelected] = useState<Set<PdfSectionId>>(
    new Set(PDF_SECTION_ORDER),
  );
  const [downloading, setDownloading] = useState(false);

  // Загрузить сохранённый выбор при open
  useEffect(() => {
    if (open) {
      setSelected(new Set(loadSavedSections()));
    }
  }, [open]);

  function toggleSection(id: PdfSectionId) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAll() {
    setSelected(new Set(PDF_SECTION_ORDER));
  }

  function deselectAll() {
    setSelected(new Set());
  }

  const isAllSelected = selected.size === PDF_SECTION_ORDER.length;

  async function handleDownload() {
    if (selected.size === 0) return;
    setDownloading(true);
    try {
      // Сохранить выбор
      const arr = PDF_SECTION_ORDER.filter((id) => selected.has(id));
      saveSections(arr);

      // Запрос с auth — нужен fetch с headers
      const sectionsParam = isAllSelected ? "" : `?sections=${arr.join(",")}`;
      const url = `/api/projects/${projectId}/export/pdf${sectionsParam}`;
      
      const response = await apiFetch(url, { method: "GET" });
      if (!response.ok) {
        throw new Error(`PDF export failed: ${response.status}`);
      }
      const blob = await response.blob();
      
      // Trigger download через blob URL
      const blobUrl = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      // Извлечь filename из Content-Disposition если возможно
      const cd = response.headers.get("content-disposition") ?? "";
      const match = /filename\*=UTF-8''([^;]+)/.exec(cd) || /filename="([^"]+)"/.exec(cd);
      const filename = match
        ? decodeURIComponent(match[1])
        : `project-${projectId}${isAllSelected ? "" : "_partial"}.pdf`;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(blobUrl);

      toast.success("PDF скачан");
      onOpenChange(false);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Ошибка";
      toast.error(`Не удалось скачать PDF: ${msg}`);
    } finally {
      setDownloading(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Экспорт PDF</DialogTitle>
          <DialogDescription>
            Выберите секции для включения в PDF{projectName ? ` «${projectName}»` : ""}.
            Выбор запоминается для следующего экспорта.
          </DialogDescription>
        </DialogHeader>

        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={selectAll}
            disabled={downloading || isAllSelected}
          >
            Выбрать всё
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={deselectAll}
            disabled={downloading || selected.size === 0}
          >
            Снять всё
          </Button>
        </div>

        <div className="max-h-[50vh] overflow-y-auto space-y-1 pt-2">
          {PDF_SECTION_ORDER.map((id) => (
            <div key={id} className="flex items-center gap-2 py-1">
              <Checkbox
                id={`pdf-section-${id}`}
                checked={selected.has(id)}
                onCheckedChange={() => toggleSection(id)}
                disabled={downloading}
              />
              <label
                htmlFor={`pdf-section-${id}`}
                className="flex-1 text-sm cursor-pointer"
              >
                {PDF_SECTION_LABELS[id]}
              </label>
            </div>
          ))}
        </div>

        <DialogFooter>
          <span className="text-sm text-muted-foreground mr-auto">
            Выбрано: {selected.size} / {PDF_SECTION_ORDER.length}
          </span>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={downloading}
          >
            Отмена
          </Button>
          <Button
            type="button"
            onClick={handleDownload}
            disabled={downloading || selected.size === 0}
          >
            {downloading ? "Скачивание..." : "Скачать PDF"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

⚠ `apiFetch` может не быть в проекте — проверить `frontend/lib/api.ts`. Если есть `apiGet` для JSON, добавить `apiFetch` (generic fetch с auth) или встроить fetch напрямую с auth header.

- [ ] **Step 4: Wire button to open dialog**

В файле, где сейчас кнопка PDF-экспорта (Step 1 нашёл):
- Заменить direct download на `setPdfDialogOpen(true)`
- Добавить state `pdfDialogOpen`
- Рендерить `<PdfExportDialog ... />`

- [ ] **Step 5: Frontend restart + tsc**

```bash
docker compose -f infra/docker-compose.dev.yml stop frontend
docker compose -f infra/docker-compose.dev.yml run --rm frontend sh -c "rm -rf .next/* .next/.[!.]* 2>/dev/null"
docker compose -f infra/docker-compose.dev.yml up -d frontend
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```

- [ ] **Step 6: Commit T2**

```bash
git add frontend/lib/pdf-sections.ts \
        frontend/components/projects/pdf-export-dialog.tsx \
        <button-file>
git commit -m "feat(c27-t2): PdfExportDialog — чекбоксы для выбора секций

- lib/pdf-sections.ts: 17 SectionId + LABELS + load/save в localStorage
- PdfExportDialog: чекбокс per section + select/deselect all + blob download
- Кнопка PDF-экспорта теперь открывает dialog вместо direct download
- localStorage key pdf-export-sections-v1 сохраняет выбор"
```

---

## Task 3: Smoke + CHANGELOG + GO5 + merge

- [ ] **Step 1: Full pytest + tsc + acceptance**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration | tail -3
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q tests/acceptance -m acceptance | tail -3
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```

- [ ] **Step 2: Обновить CHANGELOG.md**

В `## [Unreleased]` секцию `### Added (Phase C — C #27)`:
```markdown
- **C #27**: PDF экспорт получает диалог выбора секций — 17 чекбоксов (титул, общая инфо, концепция, ..., executive summary). Endpoint `?sections=kpi,pnl` для programmatic access. LocalStorage сохраняет выбор юзера.
```

- [ ] **Step 3: Обновить GO5.md status**

Заголовок «### Фаза C — 8/19 ✅» → «### Фаза C — 9/19 ✅».
Добавить строку в таблицу:
```markdown
| 27 | PDF чекбоксы выбора секций | ✅ 2026-05-16 |
```

В backlog убрать #27 из «Средние».

- [ ] **Step 4: Commit T3 docs**

```bash
git add CHANGELOG.md GO5.md
git commit -m "docs(c27): CHANGELOG + GO5 — C #27 PDF section checkboxes closed"
```

- [ ] **Step 5: Merge --no-ff в main**

```bash
git checkout main
git merge --no-ff feat/c27-pdf-section-checkboxes -m "Merge C #27 — PDF чекбоксы выбора секций

3-task subagent-driven small-эпик:
- T1 backend: section catalog + endpoint param + template conditionals + 4 теста
- T2 frontend: lib/pdf-sections.ts + PdfExportDialog + wire button
- T3 docs + smoke

Endpoint backward-compat: omit sections → все 17 секций.
LocalStorage запоминает выбор. Filename _partial если не все секции.

Closes Phase C #27."
git tag v2.6.1 -m "v2.6.1 — C #27 PDF section checkboxes"
git branch -d feat/c27-pdf-section-checkboxes
```

DO NOT push — controller (Claude) делает merge но не push (user decision).
