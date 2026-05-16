# C #26 BOM сводка справа Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Перенести category-агрегацию BOM из inline CardHeader блока в отдельный sidebar справа от таблицы.

**Architecture:** Новый компонент `BomSummarySidebar`. `BomPanel` — grid layout `md:grid-cols-3` (таблица col-span-2, sidebar col-span-1). Backend не трогаем.

**Tech Stack:** Next.js 14 / TS / Tailwind / shadcn / Playwright.

**Spec:** `docs/superpowers/specs/2026-05-16-c26-bom-summary-design.md` (commit `4089667`).
**Branch:** `feat/c26-bom-summary` (с main HEAD `4089667`).
**Tag после merge:** `v2.6.4`.

---

## File Structure

**Создаваемые:**
- `frontend/components/projects/bom-summary-sidebar.tsx` — компонент агрегации
- `frontend/e2e/c26-bom-summary.spec.ts` — Playwright (test empty + test.skip seed)

**Модифицируемые:**
- `frontend/components/projects/bom-panel.tsx` — grid layout + удалить старый categorySums useMemo и CardHeader inline блок + удалить CATEGORY_LABELS_BOM (move в sidebar) + вставить `<BomSummarySidebar items={bom} />`
- `CHANGELOG.md` — секция Unreleased → C #26
- `docs/CLIENT_FEEDBACK_v2_STATUS.md` — пункт 22 ❌ → ✅

Boundaries: T1 = создание компонента + интеграция (неотделимо без сломанного state). T2 = docs.

---

## Task 1: BomSummarySidebar + интеграция в BomPanel + e2e

**Files:**
- Create: `frontend/components/projects/bom-summary-sidebar.tsx`
- Modify: `frontend/components/projects/bom-panel.tsx` (lines 182-194, 405-413, 588-619 — точные строки уточнить)
- Create: `frontend/e2e/c26-bom-summary.spec.ts`

- [ ] **Step 1.1: Создать ветку**

```bash
git checkout main
git checkout -b feat/c26-bom-summary
```

- [ ] **Step 1.2: Создать `frontend/components/projects/bom-summary-sidebar.tsx`**

```tsx
"use client";

import { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { formatMoney } from "@/lib/format";
import type { BOMItemRead } from "@/types/api";

/** Категории BOM-ингредиентов (FK Ingredient.category). */
const CATEGORY_LABELS: Record<string, string> = {
  raw_material: "Сырьё",
  packaging: "Упаковка",
  other: "Прочее",
};

/** Порядок отображения категорий в сводке (фиксированный). */
const CATEGORY_ORDER = ["raw_material", "packaging", "other"] as const;

interface CategorySummary {
  sum: number;
  count: number;
}

interface BomSummarySidebarProps {
  items: BOMItemRead[];
}

/**
 * Сводка BOM справа от таблицы: разбивка по категориям ингредиентов
 * (Сырьё / Упаковка / Прочее) с суммой ₽, кол-вом позиций, % от итога.
 * Сумма категории = Σ qty × price × (1 + loss) per items.
 */
export function BomSummarySidebar({ items }: BomSummarySidebarProps) {
  const { byCat, total, totalCount } = useMemo(() => {
    const byCat: Record<string, CategorySummary> = {
      raw_material: { sum: 0, count: 0 },
      packaging: { sum: 0, count: 0 },
      other: { sum: 0, count: 0 },
    };
    let total = 0;
    for (const it of items) {
      const cat = it.ingredient_category ?? "other";
      const slot = byCat[cat] ?? byCat.other;
      const cost =
        Number(it.quantity_per_unit) *
        Number(it.price_per_unit) *
        (1 + Number(it.loss_pct));
      if (!Number.isNaN(cost)) {
        slot.sum += cost;
        total += cost;
      }
      slot.count += 1;
    }
    return { byCat, total, totalCount: items.length };
  }, [items]);

  if (items.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Сводка BOM</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Добавьте позиции BOM для расчёта.
          </p>
        </CardContent>
      </Card>
    );
  }

  function pct(sum: number): string {
    if (total === 0) return "—";
    return `${((sum / total) * 100).toFixed(1)}%`;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Сводка BOM</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-2">
          {CATEGORY_ORDER.map((cat) => {
            const entry = byCat[cat];
            const empty = entry.count === 0;
            return (
              <div key={cat} className="flex items-baseline justify-between gap-2 text-sm">
                <div>
                  <div className="font-medium">{CATEGORY_LABELS[cat]}</div>
                  <div className="text-xs text-muted-foreground">
                    {empty ? "0 позиций" : `${entry.count} поз., ${pct(entry.sum)}`}
                  </div>
                </div>
                <div className="text-right font-medium tabular-nums">
                  {empty ? (
                    <span className="text-muted-foreground">—</span>
                  ) : (
                    formatMoney(String(entry.sum))
                  )}
                </div>
              </div>
            );
          })}
        </div>
        <Separator />
        <div className="flex items-baseline justify-between gap-2 text-sm font-semibold">
          <div>
            <div>Итого</div>
            <div className="text-xs font-normal text-muted-foreground">
              {totalCount} {totalCount === 1 ? "позиция" : "позиций"}
            </div>
          </div>
          <div className="tabular-nums">{formatMoney(String(total))}</div>
        </div>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 1.3: Проверить наличие `@/components/ui/separator`**

Если файла нет — добавить shadcn separator (`npx shadcn add separator`), либо заменить `<Separator />` на `<div className="border-t" />`. Не добавлять dependency без согласования — fallback на div ОК.

- [ ] **Step 1.4: Модифицировать `frontend/components/projects/bom-panel.tsx`**

A) Удалить `categorySums` useMemo (текущие строки 182-194):
```ts
// УДАЛИТЬ ВЕСЬ блок:
const categorySums = useMemo(() => { ... }, [bom]);
```

B) Удалить `CATEGORY_LABELS_BOM` константу (текущие 409-413):
```ts
// УДАЛИТЬ:
const CATEGORY_LABELS_BOM: Record<string, string> = { ... };
```

(Сначала проверь grep что больше нигде в файле не используется. Если используется — оставь и НЕ удаляй, sidebar просто получит свою копию.)

C) Удалить inline-блок категорий в CardHeader (строки 605-616):
```tsx
// УДАЛИТЬ:
{Object.keys(categorySums).length > 0 && (
  <div className="text-xs text-muted-foreground space-y-0.5">
    ...
  </div>
)}
```

D) В CardHeader оставить только `<p>COGS на единицу (preview)</p>` + `<p>{formatMoney(...)}</p>` — без category breakdown.

E) Импортировать `BomSummarySidebar` в начало файла:
```ts
import { BomSummarySidebar } from "./bom-summary-sidebar";
```

F) Обернуть основной BOM-Card в grid и добавить sidebar. Структура:

Было (приблизительно):
```tsx
<Card>
  <CardHeader>...</CardHeader>
  <CardContent>...table + form...</CardContent>
</Card>
```

Станет:
```tsx
<div className="grid grid-cols-1 md:grid-cols-3 gap-4">
  <Card className="md:col-span-2">
    <CardHeader>...</CardHeader>
    <CardContent>...table + form...</CardContent>
  </Card>
  <div className="md:col-span-1">
    <BomSummarySidebar items={bom ?? []} />
  </div>
</div>
```

(Точная wrap-зона — главный BOM Card на уровне второй Card в JSX. ProjectSKU rates Card сверху не трогаем.)

- [ ] **Step 1.5: Создать `frontend/e2e/c26-bom-summary.spec.ts`**

```ts
/**
 * C #26 — BOM сводка справа.
 */
import { expect, test } from "@playwright/test";

const EMAIL = "admin@example.com";
const PASSWORD = "admin123";

async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Пароль").fill(PASSWORD);
  await page.getByRole("button", { name: "Войти" }).click();
  await page.waitForURL("**/projects", { timeout: 10_000 });
}

async function createProjectAndOpenBom(
  page: import("@playwright/test").Page,
  prefix: string,
) {
  await login(page);
  await page.getByRole("button", { name: "Создать проект" }).click();
  await page.getByLabel("Название").fill(`${prefix} ${Date.now()}`);
  await page.getByRole("button", { name: "Создать" }).click();
  await expect(
    page.getByRole("tab", { name: "Параметры" }),
  ).toBeVisible({ timeout: 10_000 });
  // ... open "SKU и BOM" tab, create SKU if needed
}

test("C #26 — пустой BOM показывает empty state в сводке", async ({ page }) => {
  await createProjectAndOpenBom(page, "C26 empty");
  // expect summary card visible
  await expect(page.getByText("Сводка BOM")).toBeVisible();
  await expect(page.getByText("Добавьте позиции BOM для расчёта")).toBeVisible();
  // TODO: уточнить путь до открытия SKU+BOM tab если требует seed-SKU
});

test.skip("C #26 — BOM из 3 категорий показывает разбивку + Итого", async ({ page }) => {
  // TODO: требует seed-данных (3 ингредиента с разными category)
});
```

(Test 1 может требовать создание SKU в проекте — если flow сложный, реализуй или помечай `test.skip` с TODO. Минимум — файл создан и компилируется.)

- [ ] **Step 1.6: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: 0 новых ошибок.

- [ ] **Step 1.7: Полный restart frontend (per memory)**

После нового import в bom-panel.tsx — Windows+Docker HMR ненадёжен:
```bash
docker compose restart frontend
```

- [ ] **Step 1.8: Manual verify в браузере**

Открыть проект, SKU и BOM tab. Empty state: сводка показывает «Добавьте позиции». Добавить позицию из категории «Сырьё» (если ingredient_id привязан) → видно строку Сырьё с суммой + Итого с той же суммой. Layout — sidebar справа на desktop.

- [ ] **Step 1.9: Commit**

```bash
git add frontend/components/projects/bom-summary-sidebar.tsx \
        frontend/components/projects/bom-panel.tsx \
        frontend/e2e/c26-bom-summary.spec.ts
git commit -m "feat(c26-t1): BomSummarySidebar + grid layout в BomPanel

- Новый компонент BomSummarySidebar (Сырьё/Упаковка/Прочее + Итого)
- BomPanel: grid grid-cols-1 md:grid-cols-3 — таблица col-span-2, sidebar col-span-1
- Удалён старый categorySums useMemo и inline-блок в CardHeader
- Playwright e2e: empty state test (test 2 skip — seed-зависимо)

Refs: docs/superpowers/specs/2026-05-16-c26-bom-summary-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: CHANGELOG + STATUS

- [ ] **Step 2.1: CHANGELOG.md — добавить блок перед C #29**

```markdown
### Added (Phase C — C #26)

- **C #26**: BOM-панель получила отдельный sidebar `Сводка BOM` справа от таблицы (grid `md:grid-cols-3`). Sidebar показывает суммы по категориям ингредиентов (Сырьё / Упаковка / Прочее) с количеством позиций и % от итога + общую строку «Итого». Empty state при пустом BOM. Inline-блок категорийных сумм в CardHeader удалён — один источник истины. (MEMO 3.4)
```

- [ ] **Step 2.2: docs/CLIENT_FEEDBACK_v2_STATUS.md — пункт 22**

Заменить:
```
22. **BOM сводка справа** (3.4, ❌).
```
на:
```
22. **BOM сводка справа** (3.4, ✅ — закрыто C #26 2026-05-16).
```

Если в таблице секции 3.4 есть аналогичная запись с ❌ — также обновить на ✅.

- [ ] **Step 2.3: Финальный tsc**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 2.4: Commit**

```bash
git add CHANGELOG.md docs/CLIENT_FEEDBACK_v2_STATUS.md
git commit -m "docs(c26): CHANGELOG + STATUS — BOM sidebar closed

Refs: docs/superpowers/specs/2026-05-16-c26-bom-summary-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Финализация (controller)

- [ ] **F.1: Merge**

```bash
git checkout main
git merge --no-ff feat/c26-bom-summary -m "Merge C #26 — BOM сводка справа

BomPanel получил отдельный sidebar Сводка BOM (Сырьё/Упаковка/Прочее
+ Итого). Layout md:grid-cols-3. Inline-блок в CardHeader удалён.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **F.2: Tag**

```bash
git tag -a v2.6.4 -m "C #26 — BOM сводка справа

Phase C completion run: 5/11 закрыто."
```

- [ ] **F.3: Cleanup + memory**

```bash
git branch -d feat/c26-bom-summary
```

Обновить `project_phase_c_completion_run.md`: 12/19 ✅, остаток 6.

## Self-review

**Spec coverage:**
- §2.1 layout grid → T1 Step 1.4-F ✓
- §2.2 BomSummarySidebar → T1 Step 1.2 ✓
- §2.3 терминология → T1 Step 1.2 (CATEGORY_LABELS) ✓
- §2.4 удаление CardHeader inline + categorySums → T1 Step 1.4-A/B/C ✓
- §5.2 Playwright → T1 Step 1.5 ✓

**Placeholder scan:** Step 1.5 содержит TODO в test (seed-зависимо). Это намеренно — заглушка скомпилируется, опциональная доводка локаторов implementer'ом.

**Type consistency:**
- `BOMItemRead` импортируется из `@/types/api` (consistent с другими).
- `formatMoney(String(...))` — pattern уже используется в bom-panel.tsx:603.
- `CATEGORY_ORDER` `as const` для type safety.
