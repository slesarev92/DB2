# C #29 Валидация вводных Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить inline warnings (amber) для 4 критических полей при значении 0; save не блокируется.

**Architecture:** Расширить `useFieldValidation` так, чтобы он возвращал `warnings` параллельно с `errors`. Добавить `FieldRule.warn` (predicate + сообщение). Создать новый компонент `FieldWarning`. Интегрировать в 3 формы. Backend не трогаем.

**Tech Stack:** Next.js 14 / TypeScript / Tailwind / shadcn/ui / lucide-react / Playwright e2e.

**Spec:** `docs/superpowers/specs/2026-05-16-c29-input-validation-design.md` (commits `e619964`, `ccd2a93`).

**Branch:** `feat/c29-input-validation` (создать с `main` HEAD = `ccd2a93`).
**Tag после merge:** `v2.6.3`.

---

## File Structure

**Создаваемые:**
- `frontend/components/ui/field-warning.tsx` — UI-компонент amber warning + AlertTriangle icon
- `frontend/e2e/c29-input-validation.spec.ts` — Playwright e2e тесты (5 сценариев)

**Модифицируемые:**
- `frontend/lib/use-field-validation.ts` — `FieldRule.warn`, `validateField` возвращает `{error?, warning?}`, hook отдаёт `warnings`
- `frontend/components/projects/channel-form.tsx` — `warn` в rules для `shelf_price_reg` и `offtake_target`, render `FieldWarning`
- `frontend/components/projects/bom-panel.tsx` — `warn` в `BOM_RULES` для `price_per_unit`, render
- `frontend/components/projects/add-sku-dialog.tsx` — `warn` для `volume_l`, render
- `CHANGELOG.md` — секция `[Unreleased]` → C #29
- `docs/CLIENT_FEEDBACK_v2_STATUS.md` — пункт 27 «Валидация вводных» статус ❌ → ✅

Boundary разделения: T1 = core (hook + ui-component) self-contained; T2 = per-form integration (зависит от T1); T3 = docs (after code works).

---

## Task 1: Hook расширение + FieldWarning компонент

**Files:**
- Modify: `frontend/lib/use-field-validation.ts:1-128`
- Create: `frontend/components/ui/field-warning.tsx`

- [ ] **Step 1.1: Создать ветку**

```bash
git checkout main
git status   # должно быть clean
git checkout -b feat/c29-input-validation
```

Expected: `Switched to a new branch 'feat/c29-input-validation'`.

- [ ] **Step 1.2: Расширить `FieldRule` и сигнатуру `validateField` в `frontend/lib/use-field-validation.ts`**

Полная новая версия файла:

```ts
"use client";

import { useCallback, useState } from "react";

/** Validation rule for a single field. */
export interface FieldRule {
  /** Field is required (non-empty string). */
  required?: boolean;
  /** Minimum numeric value (inclusive). */
  min?: number;
  /** Maximum numeric value (inclusive). */
  max?: number;
  /** Field must parse as a number. */
  numeric?: boolean;
  /** Custom error message override. */
  message?: string;
  /**
   * Optional non-blocking warning.
   * Triggers ONLY if no error present and `when(num)` is true.
   * Empty/non-numeric values never produce warnings.
   */
  warn?: {
    when: (n: number) => boolean;
    message: string;
  };
}

/** Map of field names to their validation rules. */
export type ValidationRules<T extends string = string> = Partial<
  Record<T, FieldRule>
>;

/** Map of field names to their current error message (empty = no error). */
export type FieldErrors<T extends string = string> = Partial<Record<T, string>>;

/** Map of field names to their current warning message. */
export type FieldWarnings<T extends string = string> = Partial<
  Record<T, string>
>;

/** Result of validating a single field. */
interface ValidationResult {
  error?: string;
  warning?: string;
}

/** Validate a single field value against a rule. */
function validateField(value: string, rule: FieldRule): ValidationResult {
  const trimmed = value.trim();

  if (rule.required && trimmed === "") {
    return { error: rule.message ?? "Обязательное поле" };
  }

  // Skip numeric checks if field is empty and not required
  if (trimmed === "") return {};

  if (
    rule.numeric ||
    rule.min !== undefined ||
    rule.max !== undefined ||
    rule.warn !== undefined
  ) {
    const num = Number(trimmed.replace(",", "."));
    if (Number.isNaN(num)) {
      return { error: rule.message ?? "Введите число" };
    }
    if (rule.min !== undefined && num < rule.min) {
      return { error: rule.message ?? `Минимум ${rule.min}` };
    }
    if (rule.max !== undefined && num > rule.max) {
      return { error: rule.message ?? `Максимум ${rule.max}` };
    }
    if (rule.warn && rule.warn.when(num)) {
      return { warning: rule.warn.message };
    }
  }

  return {};
}

/**
 * Lightweight field validation hook with non-blocking warnings.
 *
 * Usage:
 * ```ts
 * const { errors, warnings, validateAll, validateOne, clearError } =
 *   useFieldValidation(RULES);
 * // On blur: validateOne("field_name", value);
 * // On submit: if (!validateAll(formState)) return;  // blocks on errors only
 * // In JSX:
 * //   <FieldError error={errors.field_name} />
 * //   <FieldWarning warning={warnings.field_name} />
 * ```
 */
export function useFieldValidation<T extends string>(
  rules: ValidationRules<T>,
) {
  const [errors, setErrors] = useState<FieldErrors<T>>({});
  const [warnings, setWarnings] = useState<FieldWarnings<T>>({});

  /** Validate one field. Returns error message or null. */
  const validateOne = useCallback(
    (field: T, value: string): string | null => {
      const rule = rules[field];
      if (!rule) return null;
      const result = validateField(value, rule);
      setErrors((prev) => {
        if (prev[field] === (result.error ?? undefined)) return prev;
        const next = { ...prev };
        if (result.error) {
          next[field] = result.error;
        } else {
          delete next[field];
        }
        return next;
      });
      setWarnings((prev) => {
        if (prev[field] === (result.warning ?? undefined)) return prev;
        const next = { ...prev };
        if (result.warning) {
          next[field] = result.warning;
        } else {
          delete next[field];
        }
        return next;
      });
      return result.error ?? null;
    },
    [rules],
  );

  /** Validate all fields at once. Returns true if no errors (warnings allowed). */
  const validateAll = useCallback(
    (values: Record<T, string>): boolean => {
      const nextErrors: FieldErrors<T> = {};
      const nextWarnings: FieldWarnings<T> = {};
      let valid = true;
      for (const [field, rule] of Object.entries(rules) as [T, FieldRule][]) {
        const val = values[field] ?? "";
        const result = validateField(val, rule);
        if (result.error) {
          nextErrors[field] = result.error;
          valid = false;
        }
        if (result.warning) {
          nextWarnings[field] = result.warning;
        }
      }
      setErrors(nextErrors);
      setWarnings(nextWarnings);
      return valid;
    },
    [rules],
  );

  /** Clear error for a specific field (e.g., on focus). Warning preserved. */
  const clearError = useCallback((field: T) => {
    setErrors((prev) => {
      if (!(field in prev)) return prev;
      const next = { ...prev };
      delete next[field];
      return next;
    });
  }, []);

  /** Clear all errors and warnings. */
  const clearAll = useCallback(() => {
    setErrors({});
    setWarnings({});
  }, []);

  /** Whether there are any validation errors (warnings do NOT count). */
  const hasErrors = Object.keys(errors).length > 0;

  return {
    errors,
    warnings,
    hasErrors,
    validateOne,
    validateAll,
    clearError,
    clearAll,
  };
}
```

Изменения относительно текущего файла (для понимания при code review):
1. `FieldRule.warn?: { when, message }` — новое.
2. `FieldWarnings<T>` — новый тип.
3. `validateField` возвращает `ValidationResult` (`{error?, warning?}`).
4. Hook хранит `warnings` state параллельно с `errors`.
5. `validateOne`/`validateAll` обновляют оба state.
6. `clearError` чистит ТОЛЬКО error (warning остаётся, чтобы пользователь продолжал видеть нюдж).
7. `clearAll` чистит оба.
8. `hasErrors` — только по errors (warnings не блокируют submit).

- [ ] **Step 1.3: Создать `frontend/components/ui/field-warning.tsx`**

```tsx
import { AlertTriangle } from "lucide-react";

/**
 * Inline non-blocking warning message (amber, AlertTriangle icon).
 * Symmetric to FieldError. Renders nothing if `warning` is falsy.
 */
export function FieldWarning({ warning }: { warning?: string | null }) {
  if (!warning) return null;
  return (
    <p
      className="mt-0.5 flex items-center gap-1 text-xs text-amber-600"
      role="status"
    >
      <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden="true" />
      <span>{warning}</span>
    </p>
  );
}
```

- [ ] **Step 1.4: Проверить компиляцию TypeScript**

Run:
```bash
cd frontend && npx tsc --noEmit
```

Expected: `0 errors`. (Consumers ещё не используют новый API, но сам hook должен типизироваться без ошибок. Существующие формы используют только `errors`, `validateAll`, `validateOne`, `clearError` — backward-compatible.)

- [ ] **Step 1.5: Commit**

```bash
git add frontend/lib/use-field-validation.ts frontend/components/ui/field-warning.tsx
git commit -m "feat(c29-t1): расширение useFieldValidation + FieldWarning

- FieldRule.warn?: { when, message } для non-blocking warnings
- validateField возвращает { error?, warning? }
- Hook отдаёт warnings параллельно errors
- validateAll возвращает true при warning-only state
- Новый компонент FieldWarning (amber + AlertTriangle)
- Backward-compatible: существующие формы продолжают работать

Refs: docs/superpowers/specs/2026-05-16-c29-input-validation-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

Expected: `[feat/c29-input-validation <sha>] feat(c29-t1): ...`.

---

## Task 2: Per-form integration + Playwright e2e

**Files:**
- Modify: `frontend/components/projects/channel-form.tsx` (rules + JSX render)
- Modify: `frontend/components/projects/bom-panel.tsx` (rules + JSX render)
- Modify: `frontend/components/projects/add-sku-dialog.tsx` (rules + JSX render)
- Create: `frontend/e2e/c29-input-validation.spec.ts`

- [ ] **Step 2.1: Изучить текущие rules + JSX в `channel-form.tsx`**

Read `frontend/components/projects/channel-form.tsx` строки 96–110 (CHANNEL_FORM_RULES) и весь JSX от `return (` до `</form>` чтобы найти где рендерятся `<FieldError>` для `shelf_price_reg` и `offtake_target`. Зафиксировать line numbers.

- [ ] **Step 2.2: Добавить `warn` в `CHANNEL_FORM_RULES` для двух полей**

В `frontend/components/projects/channel-form.tsx` найти `CHANNEL_FORM_RULES` (строка 96). Заменить две строки:

Было:
```ts
offtake_target: { required: true, numeric: true, min: 0 },
shelf_price_reg: { required: true, numeric: true, min: 0 },
```

Станет:
```ts
offtake_target: {
  required: true,
  numeric: true,
  min: 0,
  warn: {
    when: (n) => n === 0,
    message: "Целевой offtake 0 — продаж не будет",
  },
},
shelf_price_reg: {
  required: true,
  numeric: true,
  min: 0,
  warn: {
    when: (n) => n === 0,
    message: "Цена полки 0 ₽ — выручка обнулится",
  },
},
```

- [ ] **Step 2.3: Деструктурировать `warnings` из hook + render `FieldWarning` в channel-form**

Найти строку `const { errors, validateOne, validateAll, clearError } = useFieldValidation<FormField>(effectiveRules);` (примерно :149). Заменить на:

```ts
const { errors, warnings, validateOne, validateAll, clearError } =
  useFieldValidation<FormField>(effectiveRules);
```

Импорт `FieldWarning` в начале файла (рядом с импортом `FieldError`):

```ts
import { FieldWarning } from "@/components/ui/field-warning";
```

(Уточнить alias `@/` — посмотреть как импортирован `FieldError` в этом же файле; использовать тот же стиль.)

В JSX найти места где рендерится `<FieldError error={errors.shelf_price_reg} />` и `<FieldError error={errors.offtake_target} />`. После каждого добавить:

```tsx
<FieldError error={errors.shelf_price_reg} />
<FieldWarning warning={warnings.shelf_price_reg} />
```

```tsx
<FieldError error={errors.offtake_target} />
<FieldWarning warning={warnings.offtake_target} />
```

- [ ] **Step 2.4: Изучить `bom-panel.tsx` BOM_RULES (~строка 104) и его JSX**

Read `frontend/components/projects/bom-panel.tsx`. Найти `BOM_RULES`. Найти JSX где рендерится поле `price_per_unit` (input) и его `<FieldError>`.

- [ ] **Step 2.5: Добавить warn для `price_per_unit` в `bom-panel.tsx`**

В `BOM_RULES` заменить:

Было:
```ts
price_per_unit: { numeric: true, min: 0 },
```

(Точная текущая строка может отличаться — заменить ту что есть, добавив `warn`.)

Станет:
```ts
price_per_unit: {
  numeric: true,
  min: 0,
  warn: {
    when: (n) => n === 0,
    message: "Цена сырья 0 — компонент не попадёт в COGS",
  },
},
```

Деструктуризация hook: добавить `warnings`. Импорт `FieldWarning`. После `<FieldError error={errors.price_per_unit} />` (или эквивалента — может быть в табличной ячейке) добавить `<FieldWarning warning={warnings.price_per_unit} />`.

**Замечание:** BOM использует inline-таблицу, FieldWarning рендерится в той же ячейке после input + FieldError. Если ячейка узкая, перенос строки — нормально (amber-текст помещается ниже input на той же ячейке).

- [ ] **Step 2.6: Изучить `add-sku-dialog.tsx` и его SKU_RULES для `volume_l`**

Read `frontend/components/projects/add-sku-dialog.tsx`. Найти `volume_l` input и rules (если есть в форме — иначе валидация только на бэкенде, тогда добавить rules).

- [ ] **Step 2.7: Добавить warn для `volume_l` в `add-sku-dialog.tsx`**

Если в `add-sku-dialog.tsx` уже используется `useFieldValidation` — добавить `warn` для `volume_l` так же как в шагах 2.2/2.3:

```ts
volume_l: {
  numeric: true,
  min: 0,
  warn: {
    when: (n) => n === 0,
    message: "Объём 0 — расчёты per-unit некорректны",
  },
},
```

Если в `add-sku-dialog.tsx` ещё нет `useFieldValidation` (только Input с `min="0"`): подключить hook минимально — единственное правило для `volume_l`:

```ts
const SKU_RULES: ValidationRules<"volume_l"> = {
  volume_l: {
    numeric: true,
    min: 0,
    warn: {
      when: (n) => n === 0,
      message: "Объём 0 — расчёты per-unit некорректны",
    },
  },
};

const { errors, warnings, validateOne } = useFieldValidation<"volume_l">(SKU_RULES);
```

И вызвать `validateOne("volume_l", value)` на `onBlur` input'а. Рядом с input — `<FieldError error={errors.volume_l} /><FieldWarning warning={warnings.volume_l} />`.

- [ ] **Step 2.8: Проверить TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

Expected: `0 errors`.

- [ ] **Step 2.9: Полный restart Next.js dev-сервера (per memory)**

После добавления нового import (`FieldWarning`) в existing файлы — Windows+Docker HMR ненадёжен. Если dev-сервер запущен:

```bash
docker compose restart frontend
# или, если запущен через npm:
# Ctrl+C, затем rm -rf .next, затем npm run dev
```

(Этот шаг обязателен только если controller планирует manual verify в браузере перед T3 — для Playwright можно не делать, e2e сами стартуют свежий процесс.)

- [ ] **Step 2.10: Создать `frontend/e2e/c29-input-validation.spec.ts`**

```ts
/**
 * C #29 — Валидация вводных (minimum protection).
 * Проверяет inline amber-warnings при значении 0 в 4 критических полях.
 * Submit формы при warning-only state не блокируется; -1 блокируется error.
 *
 * Требования: Docker compose stack запущен, dev user admin@example.com/admin123.
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

async function createProjectAndOpen(
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
}

// ============================================================
// 1. ChannelForm: shelf_price_reg = 0 → warning, save проходит
// ============================================================

test("C #29 — shelf_price_reg=0 показывает amber warning, не блокирует save", async ({
  page,
}) => {
  await createProjectAndOpen(page, "C29 shelf");
  // TODO для implementer: открыть вкладку Каналы, кликнуть "Добавить канал",
  // выбрать SKU + Channel из dropdown, заполнить required-поля валидными значениями,
  // shelf_price_reg = 0, blur → ожидать warning text.
  // Структуру dialog'а уточнить по channel-form.tsx и существующему e2e flow.
  // Заглушка теста — заполнить после изучения структуры формы:
  await page.getByRole("tab", { name: "Каналы" }).click();
  // ... locator цепочка для добавления канала ...
  // await page.getByLabel("Цена полки, ₽").fill("0");
  // await page.getByLabel("Цена полки, ₽").blur();
  // await expect(page.getByText("Цена полки 0 ₽ — выручка обнулится")).toBeVisible();
  // await page.getByRole("button", { name: "Сохранить" }).click();
  // await expect(page.getByRole("dialog")).not.toBeVisible({ timeout: 5_000 });
});

// ============================================================
// 2. ChannelForm: offtake_target = 0 → warning, save проходит
// ============================================================

test("C #29 — offtake_target=0 показывает amber warning, не блокирует save", async ({
  page,
}) => {
  await createProjectAndOpen(page, "C29 offtake");
  // Аналогично test 1, но другое поле и текст warning'а:
  // "Целевой offtake 0 — продаж не будет"
});

// ============================================================
// 3. BOMPanel: price_per_unit = 0 → warning, save проходит
// ============================================================

test("C #29 — BOM price_per_unit=0 показывает warning, не блокирует save", async ({
  page,
}) => {
  await createProjectAndOpen(page, "C29 bom");
  // SKU и BOM tab → создать SKU → добавить BOM-компонент → price_per_unit=0
  // ожидать "Цена сырья 0 — компонент не попадёт в COGS"
});

// ============================================================
// 4. AddSkuDialog: volume_l = 0 → warning, save проходит
// ============================================================

test("C #29 — volume_l=0 показывает warning, не блокирует создание SKU", async ({
  page,
}) => {
  await createProjectAndOpen(page, "C29 volume");
  // SKU и BOM tab → "Добавить SKU" → volume_l=0
  // ожидать "Объём 0 — расчёты per-unit некорректны"
});

// ============================================================
// 5. Negative: -1 в shelf_price_reg → red error, save заблокирован
// ============================================================

test("C #29 — shelf_price_reg=-1 показывает error, блокирует save", async ({
  page,
}) => {
  await createProjectAndOpen(page, "C29 negative");
  // Каналы → -1 в shelf_price_reg → blur → ожидать error "Минимум 0"
  // Submit → диалог НЕ закрылся (форма заблокирована)
});
```

**Замечание для implementer**: точные locator-цепочки нужно завершить, изучив `channel-form.tsx`, `bom-panel.tsx`, `add-sku-dialog.tsx` и существующий `smoke.spec.ts`. Каркас выше — заглушка с TODO; implementer должен заменить TODO на работающие steps. Если в формах есть Select для SKU/Channel — нужно их заполнить дефолтными значениями.

- [ ] **Step 2.11: Запустить Playwright e2e**

```bash
docker compose up -d   # если ещё не запущен
cd frontend && npx playwright test e2e/c29-input-validation.spec.ts
```

Expected: 5 tests passed. Если падают — implementer чинит locator-ы.

- [ ] **Step 2.12: Manual verify в браузере (controller checkpoint)**

Открыть `http://localhost:3000`, залогиниться, пройти 4 positive-кейса вручную. Подтвердить визуально:
- Amber-цвет различим (text-amber-600 на белом фоне)
- AlertTriangle icon виден
- Текст помещается, не съезжает

Если визуальные проблемы — controller правит `field-warning.tsx` (margin, icon size) до коммита.

- [ ] **Step 2.13: Commit**

```bash
git add frontend/components/projects/channel-form.tsx \
        frontend/components/projects/bom-panel.tsx \
        frontend/components/projects/add-sku-dialog.tsx \
        frontend/e2e/c29-input-validation.spec.ts
git commit -m "feat(c29-t2): warn rules для 4 критических полей + e2e

Добавлен warn-механизм в:
- channel-form.tsx: shelf_price_reg, offtake_target (warning при 0)
- bom-panel.tsx: price_per_unit (warning при 0)
- add-sku-dialog.tsx: volume_l (warning при 0)

Playwright e2e: 4 positive + 1 negative scenarios.

tsc --noEmit: 0 errors.

Refs: docs/superpowers/specs/2026-05-16-c29-input-validation-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: CHANGELOG + STATUS update

**Files:**
- Modify: `CHANGELOG.md` (секция `[Unreleased]`)
- Modify: `docs/CLIENT_FEEDBACK_v2_STATUS.md` (пункт 27)

- [ ] **Step 3.1: Открыть `CHANGELOG.md` и найти секцию `[Unreleased]`**

Read `CHANGELOG.md` top 30 строк, найти секцию `## [Unreleased]` (или эквивалент). Если нет — создать в начале файла.

- [ ] **Step 3.2: Добавить запись в `CHANGELOG.md`**

В секцию `[Unreleased]` под `### Added` (или создать секцию `Added`) добавить:

```markdown
### Added — C #29 Валидация вводных (minimum protection)

- `useFieldValidation` hook расширен `warn?: { when, message }` правилом — non-blocking warning параллельно с errors.
- Новый компонент `FieldWarning` (amber + AlertTriangle icon) симметричный `FieldError`.
- Inline-предупреждения для 4 критических полей при значении `0`:
  - `shelf_price_reg` (ChannelForm) — «Цена полки 0 ₽ — выручка обнулится»
  - `offtake_target` (ChannelForm) — «Целевой offtake 0 — продаж не будет»
  - BOM `price_per_unit` (BOMPanel) — «Цена сырья 0 — компонент не попадёт в COGS»
  - SKU `volume_l` (AddSkuDialog) — «Объём 0 — расчёты per-unit некорректны»
- Playwright e2e `c29-input-validation.spec.ts` — 5 scenarios.

Backend не менялся (Pydantic `ge=0` остаётся защитой от отрицательных).
Out of scope: upper bound `copacking_rate`, per-period warnings, Excel-импорт warnings.
```

- [ ] **Step 3.3: Обновить `docs/CLIENT_FEEDBACK_v2_STATUS.md` пункт 27**

Найти строку (примерно :287):
```
27. **Валидация вводных** (7.2, ❌).
```

Заменить на:
```
27. **Валидация вводных** (7.2, ✅ minimum protection — закрыто C #29 2026-05-16).
```

И в верхней таблице (строки около :244):
Было:
```
| Валидация вводных (отрицательная цена, нулевой universe) | ❌ | Отсутствует. Сейчас расчёт продолжается на любых входах. |
```
Станет:
```
| Валидация вводных (отрицательная цена, нулевой universe) | ✅ | Minimum protection (C #29, 2026-05-16): Pydantic `ge=0` блокирует отрицательные, frontend amber-warning при 0 для shelf_price_reg, offtake_target, BOM price_per_unit, volume_l. |
```

- [ ] **Step 3.4: Финальный tsc + полный test sweep**

```bash
cd frontend && npx tsc --noEmit
# pytest как baseline-check (не должен сломаться, мы фронт трогаем)
cd .. && pytest -m "not acceptance" -q
```

Expected:
- tsc: 0 errors
- pytest: тот же baseline (553 passed; если число изменилось — выяснить почему до коммита)

- [ ] **Step 3.5: Commit**

```bash
git add CHANGELOG.md docs/CLIENT_FEEDBACK_v2_STATUS.md
git commit -m "docs(c29): CHANGELOG + STATUS — C #29 validation closed

- CHANGELOG.md: секция [Unreleased] → C #29 Валидация вводных
- CLIENT_FEEDBACK_v2_STATUS.md: пункт 27 ❌ → ✅ (minimum protection)

Refs: docs/superpowers/specs/2026-05-16-c29-input-validation-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Финализация (controller, не subagent)

После T3 review controller выполняет (НЕ subagent):

- [ ] **F.1: Merge feature branch в main**

```bash
git checkout main
git merge --no-ff feat/c29-input-validation -m "Merge C #29 — input validation minimum protection

Closes C #29 из Phase C completion run.
- useFieldValidation расширен warn-механизмом
- FieldWarning компонент
- 4 поля с amber-warning при значении 0
- Backend не трогался

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **F.2: Tag v2.6.3**

```bash
git tag -a v2.6.3 -m "C #29 — Валидация вводных (minimum protection)

Phase C completion run: 4/11 закрыто.
- useFieldValidation.warn — non-blocking warnings
- FieldWarning UI component (amber + AlertTriangle)
- Поля: shelf_price_reg, offtake_target, BOM price_per_unit, SKU volume_l"
```

- [ ] **F.3: Cleanup branch**

```bash
git branch -d feat/c29-input-validation
git status   # должно быть clean
```

- [ ] **F.4: Memory update**

Обновить `project_phase_c_completion_run.md`:
- Перенести `#29` из «Очередь» в «Закрытые в текущем run»
- Обновить «Фаза C статус: 11/19 ✅, 7 в backlog»
- Обновить «main HEAD» и tag list
- Обновить «Push pending» количество commits

- [ ] **F.5: Уведомить пользователя**

Сводка: T1/T2/T3 + merge + tag, baseline pytest, push pending (НЕ пушим без команды).

---

## Self-review (заполнено перед хэндоффом)

**Spec coverage:**
- §2 scope (4 поля × 3 формы) → T2 шаги 2.1–2.7 ✓
- §3.1 hook расширение → T1 шаг 1.2 ✓
- §3.2 FieldWarning component → T1 шаг 1.3 ✓
- §3.3 per-form интеграция → T2 шаги 2.2/2.3/2.5/2.7 ✓
- §4 backend не трогаем → не в плане (правильно) ✓
- §5 файлы (8) → все в File Structure ✓
- §6.1 tsc compile-time → T1 1.4, T2 2.8, T3 3.4 ✓
- §6.2 Playwright e2e → T2 шаги 2.10/2.11 ✓
- §6.3 manual verify → T2 шаг 2.12 ✓
- §8 acceptance — все пункты покрыты ✓

**Placeholder scan:**
- В каркасе Playwright `c29-input-validation.spec.ts` присутствуют TODO-комментарии и «заглушка теста — заполнить после изучения структуры формы». Это **намеренно**: точные locator-цепочки невозможно зафиксировать без чтения JSX каждой формы; implementer-subagent изучает структуру и завершает locator'ы. Альтернатива — раздувать план до 300 строк JSX дампов трёх форм. Считаю компромисс приемлемым; явно отмечено как «уточнить implementer'ом».

**Type consistency:**
- `FieldRule.warn.when: (n: number) => boolean` — везде такое.
- `validateField` → `ValidationResult` (`{error?, warning?}`) — везде.
- Hook return: `{ errors, warnings, hasErrors, validateOne, validateAll, clearError, clearAll }` — все consumer-сайты деструктурируют `warnings`.
- `FieldWarning` принимает `warning?: string | null` — то же что `FieldError.error`.
- `validateOne` signature: возвращает `string | null` (error message) — сохранено, не ломает существующих consumer'ов.

Готов к выбору режима выполнения.
