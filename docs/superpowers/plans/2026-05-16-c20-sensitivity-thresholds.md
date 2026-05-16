# C #20 Sensitivity Thresholds Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

**Goal:** Настраиваемые % пороги для раскраски таблицы NPV-чувствительности и tornado-bars.

**Architecture:** localStorage (как C #27), 2 раздельных input «Зелёный ≥ %» / «Красный ≤ −%», default 5/5. Backend не трогаем.

**Tech Stack:** Next.js 14 / TS / Tailwind / shadcn / recharts (tornado).

**Spec:** `docs/superpowers/specs/2026-05-16-c20-sensitivity-thresholds-design.md` (commit `e5e86d2`).
**Branch:** `feat/c20-sensitivity-thresholds` (с main HEAD `e5e86d2`).
**Tag после merge:** `v2.6.6`.

---

## File Structure

**Создаваемые:**
- `frontend/lib/sensitivity-thresholds.ts` — localStorage lib (~50 строк, pattern с `pdf-sections.ts`)
- `frontend/components/projects/sensitivity-thresholds-controls.tsx` — UI controls (~60 строк)
- `frontend/e2e/c20-sensitivity-thresholds.spec.ts` — Playwright skip

**Модифицируемые:**
- `frontend/components/projects/sensitivity-tab.tsx` — useState, npvClass с thresholds, проброс в TornadoChart, render controls
- `frontend/components/projects/tornado-chart.tsx` — thresholds prop, getBarColor helper

---

## Task 1: thresholds lib + controls + integration + e2e

- [ ] **Step 1.1: ветка**

```bash
git checkout main && git checkout -b feat/c20-sensitivity-thresholds
```

- [ ] **Step 1.2: создать `frontend/lib/sensitivity-thresholds.ts`**

Pattern скопирован с `pdf-sections.ts`:

```ts
/**
 * C #20: пороги раскраски для таблицы чувствительности и tornado-bars.
 * Хранятся в localStorage (как C #27 PDF sections), не персистятся в DB.
 */

export interface SensitivityThresholds {
  /** Если delta NPV / base ≥ greenPct/100 → ячейка зелёная. */
  greenPct: number;
  /** Если delta NPV / base ≤ -redPct/100 → ячейка красная. */
  redPct: number;
}

export const DEFAULT_SENSITIVITY_THRESHOLDS: SensitivityThresholds = {
  greenPct: 5,
  redPct: 5,
};

const LS_KEY = "sensitivity-thresholds-v1";

function isValidPct(x: unknown): x is number {
  return typeof x === "number" && Number.isFinite(x) && x >= 0 && x <= 100;
}

export function loadSensitivityThresholds(): SensitivityThresholds {
  if (typeof window === "undefined") return { ...DEFAULT_SENSITIVITY_THRESHOLDS };
  try {
    const raw = window.localStorage.getItem(LS_KEY);
    if (!raw) return { ...DEFAULT_SENSITIVITY_THRESHOLDS };
    const parsed: unknown = JSON.parse(raw);
    if (
      parsed === null ||
      typeof parsed !== "object" ||
      !("greenPct" in parsed) ||
      !("redPct" in parsed)
    ) {
      return { ...DEFAULT_SENSITIVITY_THRESHOLDS };
    }
    const obj = parsed as Record<string, unknown>;
    if (!isValidPct(obj.greenPct) || !isValidPct(obj.redPct)) {
      return { ...DEFAULT_SENSITIVITY_THRESHOLDS };
    }
    return { greenPct: obj.greenPct, redPct: obj.redPct };
  } catch {
    return { ...DEFAULT_SENSITIVITY_THRESHOLDS };
  }
}

export function saveSensitivityThresholds(t: SensitivityThresholds): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LS_KEY, JSON.stringify(t));
  } catch {
    // localStorage unavailable — ignore
  }
}

/**
 * Возвращает Tailwind text-color класс для NPV-ячейки относительно base.
 * Пустая строка = нейтральный.
 */
export function classifyNpv(
  value: number | null,
  base: number | null,
  thresholds: SensitivityThresholds,
): "" | "text-green-600" | "text-red-600" {
  if (value === null || base === null || base === 0) return "";
  const ratio = (value - base) / Math.abs(base);
  if (ratio >= thresholds.greenPct / 100) return "text-green-600";
  if (ratio <= -thresholds.redPct / 100) return "text-red-600";
  return "";
}

/**
 * Возвращает hex-цвет для tornado-bar относительно base.
 * Серый = нейтральный, между порогами.
 */
export function classifyNpvHex(
  value: number | null,
  base: number | null,
  thresholds: SensitivityThresholds,
): string {
  if (value === null || base === null || base === 0) return "#9ca3af";
  const ratio = (value - base) / Math.abs(base);
  if (ratio >= thresholds.greenPct / 100) return "#22c55e";
  if (ratio <= -thresholds.redPct / 100) return "#ef4444";
  return "#9ca3af";
}
```

Примечание: `Math.abs(base)` — корректная работа при отрицательном base NPV (хотя редко).

- [ ] **Step 1.3: создать `frontend/components/projects/sensitivity-thresholds-controls.tsx`**

```tsx
"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  DEFAULT_SENSITIVITY_THRESHOLDS,
  type SensitivityThresholds,
} from "@/lib/sensitivity-thresholds";

interface Props {
  value: SensitivityThresholds;
  onChange: (next: SensitivityThresholds) => void;
}

function clampPct(raw: string): number {
  const n = Number(raw);
  if (!Number.isFinite(n)) return 0;
  if (n < 0) return 0;
  if (n > 100) return 100;
  return n;
}

/**
 * Контролы для настройки порогов раскраски чувствительности (C #20).
 * Изменения сохраняются в localStorage через onChange parent'а.
 */
export function SensitivityThresholdsControls({ value, onChange }: Props) {
  return (
    <div className="flex items-end gap-3 text-xs">
      <div className="space-y-1">
        <Label
          htmlFor="sens-green-pct"
          className="text-xs text-muted-foreground"
        >
          Зелёный ≥ %
        </Label>
        <Input
          id="sens-green-pct"
          type="number"
          min={0}
          max={100}
          step={1}
          value={value.greenPct}
          onChange={(e) =>
            onChange({ ...value, greenPct: clampPct(e.target.value) })
          }
          className="h-8 w-20"
        />
      </div>
      <div className="space-y-1">
        <Label
          htmlFor="sens-red-pct"
          className="text-xs text-muted-foreground"
        >
          Красный ≤ −%
        </Label>
        <Input
          id="sens-red-pct"
          type="number"
          min={0}
          max={100}
          step={1}
          value={value.redPct}
          onChange={(e) =>
            onChange({ ...value, redPct: clampPct(e.target.value) })
          }
          className="h-8 w-20"
        />
      </div>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-8 text-xs"
        onClick={() => onChange({ ...DEFAULT_SENSITIVITY_THRESHOLDS })}
        title="Сбросить пороги к значениям по умолчанию (5% / 5%)"
      >
        Сбросить
      </Button>
    </div>
  );
}
```

- [ ] **Step 1.4: модифицировать `frontend/components/projects/sensitivity-tab.tsx`**

Read файл целиком (~340 строк). Найди:
- Импорты в начале файла
- Функция `npvClass` (lines 66-72)
- Где scope selector в JSX (header вкладки)
- Где TornadoChart рендерится
- Где npvClass вызывается (вокруг line 330-340)

**Изменения:**

A) Импорты:
```ts
import {
  loadSensitivityThresholds,
  saveSensitivityThresholds,
  classifyNpv,
  type SensitivityThresholds,
} from "@/lib/sensitivity-thresholds";
import { SensitivityThresholdsControls } from "./sensitivity-thresholds-controls";
```

B) В компоненте добавить state:
```ts
const [thresholds, setThresholds] = useState<SensitivityThresholds>(
  loadSensitivityThresholds,
);

function handleThresholdsChange(next: SensitivityThresholds) {
  setThresholds(next);
  saveSensitivityThresholds(next);
}
```

C) Заменить `npvClass`:
```ts
// Удалить функцию npvClass (lines 66-72), вместо неё использовать classifyNpv.
```

D) Использовать в JSX:
```tsx
// Было:
<TableCell className={npvClass(cell.npv_y1y10, baseValue)}>
// Стало:
<TableCell className={classifyNpv(cell.npv_y1y10, baseValue, thresholds)}>
```

E) Добавить controls в header (рядом с scope selector):
```tsx
<SensitivityThresholdsControls value={thresholds} onChange={handleThresholdsChange} />
```

F) Передать в TornadoChart:
```tsx
<TornadoChart ... thresholds={thresholds} />
```

- [ ] **Step 1.5: модифицировать `frontend/components/projects/tornado-chart.tsx`**

Read файл (~200 строк). Найди interface props, `<Bar dataKey="negative">` и `<Bar dataKey="positive">` (lines 138-146), where they get the hardcoded fill.

**Изменения:**

A) Импорт:
```ts
import {
  classifyNpvHex,
  type SensitivityThresholds,
} from "@/lib/sensitivity-thresholds";
```

B) Добавить prop в interface:
```ts
thresholds: SensitivityThresholds;
```

C) Destructure в компоненте.

D) Заменить hardcoded fill на dynamic. В recharts `<Bar>` можно использовать `<Cell>` дочерние элементы:

Найди что-то вроде:
```tsx
<Bar dataKey="negative" fill="#ef4444" />
<Bar dataKey="positive" fill="#22c55e" />
```

Заменить на:
```tsx
<Bar dataKey="negative">
  {data.map((entry, idx) => (
    <Cell
      key={`neg-${idx}`}
      fill={classifyNpvHex(baseValue + entry.negative, baseValue, thresholds)}
    />
  ))}
</Bar>
<Bar dataKey="positive">
  {data.map((entry, idx) => (
    <Cell
      key={`pos-${idx}`}
      fill={classifyNpvHex(baseValue + entry.positive, baseValue, thresholds)}
    />
  ))}
</Bar>
```

**Важно:** уточнить как у вас `entry.negative` / `entry.positive` соотносятся с базовым NPV. Если они — абсолютные значения NPV для (param, -20%) / (param, +20%), то `value` это `entry.negative`. Если они — дельты, нужно прибавлять base. Read code carefully перед написанием — варианты могут отличаться.

Импорт `Cell` из recharts (если ещё не импортирован):
```ts
import { ..., Cell } from "recharts";
```

- [ ] **Step 1.6: создать `frontend/e2e/c20-sensitivity-thresholds.spec.ts`**

```ts
/**
 * C #20 — Раскраска чувствительности с настраиваемыми порогами.
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

test.skip(
  "C #20 — изменение порога меняет раскраску ячеек",
  async ({ page }) => {
    // TODO: требует проект с рассчитанной чувствительностью.
    // Ожидаемое:
    //   1. Открыть вкладку Чувствительность
    //   2. Видны два input: "Зелёный ≥ %" / "Красный ≤ −%" со значением 5
    //   3. Поднять green до 50 → ячейки с delta < +50% становятся нейтральными
    //   4. Reset → значения возвращаются к 5/5
    //   5. Reload page → значения сохранились (localStorage)
    await login(page);
  },
);

test.skip(
  "C #20 — пороги сохраняются между сессиями",
  async ({ page, context }) => {
    // TODO: установить пороги, перезагрузить, проверить.
    await login(page);
  },
);
```

- [ ] **Step 1.7: tsc**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -v sonner | head -10
```

Expected: пусто.

- [ ] **Step 1.8: commit**

```bash
cd ..
git add frontend/lib/sensitivity-thresholds.ts \
        frontend/components/projects/sensitivity-thresholds-controls.tsx \
        frontend/components/projects/sensitivity-tab.tsx \
        frontend/components/projects/tornado-chart.tsx \
        frontend/e2e/c20-sensitivity-thresholds.spec.ts
git commit -m "feat(c20-t1): настраиваемые пороги раскраски чувствительности

- sensitivity-thresholds.ts (new): localStorage + classifyNpv/classifyNpvHex
- SensitivityThresholdsControls (new): 2 input (Зелёный ≥ %, Красный ≤ −%)
  + Reset кнопка, default 5/5
- sensitivity-tab: useState + проброс в classifyNpv и TornadoChart
- tornado-chart: динамические цвета bars (зелёный / красный / серый)
- Backend не трогаем — пороги чисто UI
- Edge case base=0/null → нейтральный
- Playwright e2e: 2 test.skip с TODO

Refs: docs/superpowers/specs/2026-05-16-c20-sensitivity-thresholds-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: CHANGELOG + STATUS

- [ ] **Step 2.1: CHANGELOG.md** — блок перед C #25:

```markdown
### Added (Phase C — C #20)

- **C #20**: Настраиваемые пороги раскраски таблицы чувствительности NPV и tornado-диаграммы. В header вкладки «Чувствительность» появились два input — «Зелёный ≥ %» и «Красный ≤ −%» (default 5%/5%), регулирующие порог отклонения от базового NPV для подсветки ячеек. Между порогами — нейтральный (серый/без подсветки). Tornado-bars также меняют цвет по той же логике. Пороги сохраняются в `localStorage` (`sensitivity-thresholds-v1`), кнопка «Сбросить» возвращает 5/5. Backend не трогался. (MEMO 6.2)
```

- [ ] **Step 2.2: STATUS** пункт 17 (~строка 274):

Было:
```
17. **Раскраска чувствительности с настраиваемыми порогами** (6.2, 🟡).
```
Стало:
```
17. **Раскраска чувствительности с настраиваемыми порогами** (6.2, ✅ — закрыто C #20 2026-05-16).
```

Также в таблице 6.2 (строка с «Раскраска таблицы зелёный/красный») 🟡 → ✅ с пометкой C #20.

- [ ] **Step 2.3: tsc + commit**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -v sonner | head -5
cd ..
git add CHANGELOG.md docs/CLIENT_FEEDBACK_v2_STATUS.md
git commit -m "docs(c20): CHANGELOG + STATUS — sensitivity thresholds closed

Refs: docs/superpowers/specs/2026-05-16-c20-sensitivity-thresholds-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Финализация (controller)

```bash
git checkout main
git merge --no-ff feat/c20-sensitivity-thresholds -m "Merge C #20 — sensitivity thresholds настраиваемые

Frontend-only fix: localStorage-based thresholds, 2 input в header
вкладки Чувствительность. Раскраска таблицы NPV и tornado-bars
учитывает % отклонения от base.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git tag -a v2.6.6 -m "C #20 — sensitivity coloring thresholds

Phase C completion run: 7/11 закрыто."
git branch -d feat/c20-sensitivity-thresholds
```

Memory: 14/19 ✅, остаток 4.

## Self-review

- §2.1 пороги → T1 Step 1.2 ✓
- §2.2 UI controls → T1 Step 1.3 ✓
- §2.3 применение раскраски → T1 Step 1.4, 1.5 ✓
- §3 архитектура → all steps ✓
- §4 backend не трогаем ✓
- §6 файлы (5) ✓
- §7 testing → manual + Playwright skip ✓

Type consistency: `SensitivityThresholds` interface single import.
