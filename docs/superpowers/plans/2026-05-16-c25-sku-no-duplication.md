# C #25 SKU no-duplication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** На вкладке «Каналы» SKU можно только привязывать (existing), создание скрыто.

**Architecture:** `existingOnly?: boolean` prop через `AddSkuDialog` ← `SkuPanel`. Backend не трогаем.

**Tech Stack:** Next.js 14 / TS / Tailwind / shadcn / Playwright.

**Spec:** `docs/superpowers/specs/2026-05-16-c25-sku-no-duplication-design.md` (commit `2fd8975`).
**Branch:** `feat/c25-sku-no-duplication` (с main HEAD `2fd8975`).
**Tag после merge:** `v2.6.5`.

---

## File Structure

**Создаваемые:**
- `frontend/e2e/c25-sku-no-duplication.spec.ts` (Playwright skip)

**Модифицируемые:**
- `frontend/components/projects/add-sku-dialog.tsx` — `existingOnly` prop + render gate
- `frontend/components/projects/sku-panel.tsx` — `existingOnly` prop + проброс + label
- `frontend/components/projects/channels-tab.tsx` — `<SkuPanel existingOnly />`
- (опционально) `frontend/components/projects/skus-tab.tsx` — sanity check, no changes если default правильный
- `CHANGELOG.md` + `docs/CLIENT_FEEDBACK_v2_STATUS.md`

---

## Task 1: existingOnly prop + integration + e2e

- [ ] **Step 1.1: ветка**

```bash
git checkout main && git checkout -b feat/c25-sku-no-duplication
```

- [ ] **Step 1.2: модифицировать `frontend/components/projects/add-sku-dialog.tsx`**

A) В интерфейс пропсов:

```ts
interface AddSkuDialogProps {
  // ... existing
  /**
   * Если true — режим «создать новый SKU» скрыт. Диалог работает
   * только в mode="existing" (выбор из каталога). Используется на
   * вкладке «Каналы» (MEMO 4.4: SKU создаётся только в SKU и BOM).
   */
  existingOnly?: boolean;
}
```

B) В компонент:

```ts
export function AddSkuDialog({
  projectId,
  open,
  onOpenChange,
  onAdded,
  existingOnly = false,
}: AddSkuDialogProps) {
  const [mode, setMode] = useState<Mode>("existing");
  // ...
```

C) При `existingOnly === true`:
- Не рендерить переключатель mode (radio/segmented control). Найди в JSX где есть `<RadioGroup>` или эквивалент для переключения mode — оберни в `{!existingOnly && <...>}`.
- Не рендерить блок формы создания нового (вся секция `{mode === "new" && ...}`). При `existingOnly` mode всё равно остаётся `"existing"` от default, так что условие `mode === "new"` всегда false — блок просто не покажется. Но для clarity можно дополнительно обернуть условие.

D) Заголовок диалога:

Найди `<DialogTitle>` или эквивалент. Текущее «Добавить SKU в проект» или похожее.

```tsx
<DialogTitle>
  {existingOnly ? "Привязать SKU к проекту" : "Добавить SKU в проект"}
</DialogTitle>
```

Если описание (`DialogDescription`) тоже намекает на создание — адаптировать:

```tsx
<DialogDescription>
  {existingOnly
    ? "Выберите SKU из каталога и привяжите к проекту."
    : "Выберите существующий SKU из каталога или создайте новый."}
</DialogDescription>
```

(Точный текст может отличаться — найди существующий и адаптируй.)

- [ ] **Step 1.3: модифицировать `frontend/components/projects/sku-panel.tsx`**

A) Добавить prop в interface:

```ts
interface SkuPanelProps {
  // ... existing
  existingOnly?: boolean;
}
```

B) В компонент:

```ts
export function SkuPanel({
  projectId,
  selectedPskId,
  onSelectPsk,
  existingOnly = false,
}: SkuPanelProps) {
```

C) Передать в AddSkuDialog (строки ~176-181):

```tsx
<AddSkuDialog
  projectId={projectId}
  open={dialogOpen}
  onOpenChange={setDialogOpen}
  onAdded={reload}
  existingOnly={existingOnly}
/>
```

D) Label кнопки добавления — найди кнопку с текстом «+ Добавить» (поиск в файле). Адаптируй:

```tsx
<Button onClick={() => setDialogOpen(true)} size="sm">
  {existingOnly ? "+ Привязать SKU" : "+ Добавить"}
</Button>
```

(Точный markup может отличаться — match существующий.)

- [ ] **Step 1.4: модифицировать `frontend/components/projects/channels-tab.tsx`**

Найти `<SkuPanel ...>` (строки ~29-33 по diagnose). Добавить `existingOnly`:

```tsx
<SkuPanel
  projectId={projectId}
  selectedPskId={selectedPskId}
  onSelectPsk={setSelectedPskId}
  existingOnly
/>
```

(Bool prop `existingOnly` без значения = `true` в JSX.)

- [ ] **Step 1.5: sanity check `frontend/components/projects/skus-tab.tsx`**

Read файл, убедись что `<SkuPanel>` НЕ передаёт `existingOnly` (default false) → пользователь на вкладке SKU и BOM сохраняет возможность создания. Если по ошибке передаётся — НЕ менять; если нет — оставить как есть.

- [ ] **Step 1.6: создать `frontend/e2e/c25-sku-no-duplication.spec.ts`**

```ts
/**
 * C #25 — Дублирование ввода SKU между табами устранено.
 * Требования: Docker stack, dev user admin@example.com/admin123.
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
  "C #25 — на вкладке Каналы диалог только в existing-режиме",
  async ({ page }) => {
    // TODO: требует seed-данных (проект с минимум 1 SKU в каталоге).
    // Ожидаемое:
    //   1. Открыть проект → tab «Каналы»
    //   2. Видна кнопка «+ Привязать SKU» (не «+ Добавить»)
    //   3. Клик → диалог «Привязать SKU к проекту»
    //   4. Mode toggle (existing/new) отсутствует
    //   5. Виден Select из каталога
    await login(page);
  },
);

test.skip(
  "C #25 — на вкладке SKU и BOM оба режима доступны",
  async ({ page }) => {
    // TODO:
    //   1. Открыть проект → tab «SKU и BOM»
    //   2. Видна кнопка «+ Добавить»
    //   3. Клик → диалог «Добавить SKU в проект»
    //   4. Mode toggle виден, оба варианта (existing / new) доступны
    await login(page);
  },
);
```

- [ ] **Step 1.7: tsc check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -v "Cannot find module 'sonner'" | head -5
```

Expected: пусто.

- [ ] **Step 1.8: Manual verify**

После реализации controller:
- Каналы → «+ Привязать SKU» → диалог «Привязать SKU к проекту», без toggle, только Select.
- SKU и BOM → «+ Добавить» → диалог «Добавить SKU в проект», toggle виден.

Если HMR не подхватил изменения — `docker compose restart frontend` (per memory feedback-frontend-structural-restart).

- [ ] **Step 1.9: commit**

```bash
cd ..
git add frontend/components/projects/add-sku-dialog.tsx \
        frontend/components/projects/sku-panel.tsx \
        frontend/components/projects/channels-tab.tsx \
        frontend/e2e/c25-sku-no-duplication.spec.ts
git commit -m "feat(c25-t1): existingOnly prop в AddSkuDialog/SkuPanel

- AddSkuDialog: existingOnly?: boolean — скрывает mode toggle,
  заголовок 'Привязать SKU к проекту'
- SkuPanel: пробрасывает existingOnly, label кнопки '+ Привязать SKU'
- channels-tab.tsx: <SkuPanel ... existingOnly />
- skus-tab.tsx: без изменений (default false, оба режима доступны)
- Playwright e2e: 2 test.skip с TODO seed-data

Refs: docs/superpowers/specs/2026-05-16-c25-sku-no-duplication-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: CHANGELOG + STATUS

- [ ] **Step 2.1: CHANGELOG.md**

В секцию `[Unreleased]` перед C #26 добавить:

```markdown
### Added (Phase C — C #25)

- **C #25**: На вкладке «Каналы» диалог добавления SKU теперь работает только в режиме привязки существующего SKU из каталога (`existingOnly` prop). Mode toggle и форма создания нового SKU скрыты — создание возможно только из вкладки «SKU и BOM», что соответствует MEMO 4.4 (один источник истины для SKU). Заголовок диалога адаптирован: «Привязать SKU к проекту» (Каналы) vs «Добавить SKU в проект» (SKU и BOM). Backend защищён `ProjectSKU.sku_id` с `RESTRICT FK` — orphan невозможен. (MEMO 4.4)
```

- [ ] **Step 2.2: STATUS**

В `docs/CLIENT_FEEDBACK_v2_STATUS.md` priority list пункт 20 (~строка 277):
```
20. **Дублирование ввода SKU между табами** (4.4, ❌).
```
Заменить на:
```
20. **Дублирование ввода SKU между табами** (4.4, ✅ — закрыто C #25 2026-05-16).
```

Также в таблице 4.4 (если есть аналогичная запись с ❌) — обновить на ✅ с пометкой про C #25.

- [ ] **Step 2.3: tsc + commit**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -v sonner | head -5
cd ..
git add CHANGELOG.md docs/CLIENT_FEEDBACK_v2_STATUS.md
git commit -m "docs(c25): CHANGELOG + STATUS — SKU duplication closed

- CHANGELOG.md [Unreleased]: C #25 секция
- CLIENT_FEEDBACK_v2_STATUS.md: пункт 20 ❌ → ✅

Refs: docs/superpowers/specs/2026-05-16-c25-sku-no-duplication-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Финализация (controller)

```bash
git checkout main
git merge --no-ff feat/c25-sku-no-duplication -m "Merge C #25 — SKU duplication устранено

Frontend-only fix: existingOnly prop в AddSkuDialog/SkuPanel.
На вкладке Каналы создание SKU скрыто, остаётся только привязка
существующего из каталога. Backend RESTRICT FK уже защищал от
orphan'ов.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git tag -a v2.6.5 -m "C #25 — SKU duplication устранено

Phase C completion run: 6/11 закрыто."
git branch -d feat/c25-sku-no-duplication
```

Memory: 13/19 ✅, остаток 5 (#20, #21, #17, #18, #15).

## Self-review

- §2.1 existingOnly prop → T1 Step 1.2 ✓
- §2.2 SkuPanel проброс → T1 Step 1.3 ✓
- §2.3 channels-tab + skus-tab → T1 Step 1.4, 1.5 ✓
- §4 backend не трогаем — план не содержит backend изменений ✓
- §6.2 Playwright e2e → T1 Step 1.6 ✓
- §7 acceptance — все ✓ через T1+T2

Type consistency: `existingOnly?: boolean` везде one type.
