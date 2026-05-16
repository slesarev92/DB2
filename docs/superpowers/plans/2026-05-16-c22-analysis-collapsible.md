# C #22 — Collapse/expand разделов группы «Анализ» (implementation plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить section-level collapse/expand на 5 табах группы ⑤ «Анализ» (Results, Sensitivity, Pricing, Value-chain, P&L) с localStorage persistence на (projectId, tabKey, sectionId). Bulk toggle «Свернуть/развернуть всё» в табах с >1 секциями.

**Architecture:** Чисто frontend. Новый wrapper-компонент `<CollapsibleSection>` поверх `@base-ui/react/collapsible` (controlled, height-transition). Хук `useCollapseState(projectId, tabKey, sectionIds)` инкапсулирует localStorage I/O. Section ID константы в отдельном модуле. Бэкенд / БД / API не трогаем. Миграции нет.

**Tech Stack:** Next.js 14 App Router, TypeScript, React 18, Tailwind, `@base-ui/react` (Collapsible primitive уже в `node_modules`), `lucide-react` 1.7.0 (`ChevronDown`, `ChevronsUpDown`, `ChevronsDownUp`).

**Spec reference:** `docs/superpowers/specs/2026-05-16-c22-analysis-collapsible-design.md` (закоммичена `ce09125`).

**Branch:** `feat/c22-analysis-collapsible` (уже создана от `main`, спека закоммичена).

---

## TDD note

Этот план **не использует TDD-цикл с unit-тестами**, потому что во `frontend/` нет unit-test runner-а (jest/vitest). Единственный test-файл — `frontend/e2e/smoke.spec.ts`, не покрывающий collapse-поведение.

**Замена TDD — статическая верификация + manual smoke:**
1. `npx tsc --noEmit` после каждой правки → 0 ошибок (ловит сигнатуры, undefined refs, мисматчи типов)
2. Manual smoke в браузере по чек-листу из spec §10.2 → подтверждение поведения

Это сознательный выбор; см. spec §10.

**Структурные изменения React-деревьев в существующих файлах** (Tasks 4-7) — после правки делать **purge `.next` + restart frontend** (Windows+Docker HMR-баг, memory `feedback-frontend-structural-restart`). Стандартный поток:
```bash
docker compose -f infra/docker-compose.dev.yml stop frontend
docker compose -f infra/docker-compose.dev.yml run --rm frontend sh -c "rm -rf .next/* .next/.[!.]* 2>/dev/null"
docker compose -f infra/docker-compose.dev.yml up -d frontend
```

---

## Task 1: Создать `<CollapsibleSection>` UI-обёртку

**Files:**
- Create: `frontend/components/ui/collapsible.tsx`

**Контекст:** Обёртка над `@base-ui/react/collapsible` примитивом. Controlled (state живёт в табе через хук из Task 2). Chevron-down лежит справа в header-button и поворачивается на основе data-атрибута `data-panel-open`. Анимация — height-transition с CSS var `--collapsible-panel-height` (предоставляет base-ui).

Существующий паттерн обёртки base-ui примитивов — `frontend/components/ui/dialog.tsx` (использует `data-slot`, `cn()` из `@/lib/utils`).

- [ ] **Step 1: Создать файл `frontend/components/ui/collapsible.tsx`**

```tsx
"use client";

import { Collapsible as CollapsiblePrimitive } from "@base-ui/react/collapsible";
import { ChevronDown } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface CollapsibleSectionProps {
  /** Стабильный ID для localStorage (kebab-case). Не менять без миграции схемы. */
  sectionId: string;
  /** Заголовок секции (string | JSX). Рисуется внутри clickable button. */
  title: ReactNode;
  /** Controlled state: true = раскрыта. */
  isOpen: boolean;
  /** Toggle handler — обычно из useCollapseState. */
  onToggle: () => void;
  /** Контент секции. */
  children: ReactNode;
  /** Доп. классы на корневой div. */
  className?: string;
}

/**
 * Section-level collapse/expand wrapper для табов группы «Анализ».
 *
 * Controlled-компонент: open и onToggle обязательны. Bulk toggle
 * («Свернуть всё / Развернуть всё») требует централизованного state,
 * поэтому defaultOpen намеренно НЕ поддерживается.
 *
 * Анимация — height-transition через CSS var --collapsible-panel-height
 * от base-ui Panel. keepMounted=true: контент остаётся в DOM при collapse
 * (важно для AI-секций с локальным state и кэшем).
 */
export function CollapsibleSection({
  sectionId,
  title,
  isOpen,
  onToggle,
  children,
  className,
}: CollapsibleSectionProps): JSX.Element {
  return (
    <CollapsiblePrimitive.Root
      data-slot="collapsible-section"
      data-section-id={sectionId}
      open={isOpen}
      onOpenChange={(open) => {
        if (open !== isOpen) onToggle();
      }}
      className={cn("space-y-2", className)}
    >
      <CollapsiblePrimitive.Trigger
        data-slot="collapsible-trigger"
        className="group flex w-full items-center justify-between gap-2 rounded-md text-left text-sm font-semibold text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
      >
        <span>{title}</span>
        <ChevronDown
          aria-hidden
          className="size-4 shrink-0 -rotate-90 transition-transform duration-200 group-data-[panel-open]:rotate-0"
        />
      </CollapsiblePrimitive.Trigger>
      <CollapsiblePrimitive.Panel
        data-slot="collapsible-panel"
        keepMounted
        className="h-[var(--collapsible-panel-height)] overflow-hidden transition-[height] duration-150 ease-out data-[starting-style]:h-0 data-[ending-style]:h-0"
      >
        <div className="pt-1">{children}</div>
      </CollapsiblePrimitive.Panel>
    </CollapsiblePrimitive.Root>
  );
}
```

**Что внутри:**
- `Collapsible.Root` controlled через `open`/`onOpenChange` (guard `if (open !== isOpen)` — против лишнего callback'а если base-ui дёргает init).
- `Collapsible.Trigger` имеет `data-panel-open` атрибут когда раскрыто. `group` + `group-data-[panel-open]:rotate-0` поворачивает chevron: closed = -90deg (▶), open = 0deg (▼).
- `Collapsible.Panel` с `keepMounted` — контент в DOM всегда, скрыт высотой. `--collapsible-panel-height` ставит base-ui автоматически.
- `space-y-2` на root: отступ между trigger и panel (внутри parent `space-y-6` это не ломает ритм).

- [ ] **Step 2: Запустить TypeScript-проверку**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```

Expected: **0 ошибок, без output**.

Возможные ошибки:
- `Cannot find module '@base-ui/react/collapsible'` — проверить `frontend/node_modules/@base-ui/react/collapsible/` существует (тестировалось во время дизайна — должно быть).
- `JSX.Element` undefined — проверить TS lib config (должна работать с React 18).
- Если `Collapsible.Trigger.Props` не находит `data-panel-open` в типах — это нормально, base-ui выставляет атрибут в runtime, типы не должны падать.

- [ ] **Step 3: Закоммитить**

```bash
git add frontend/components/ui/collapsible.tsx
git commit -m "$(cat <<'EOF'
feat(c22): add CollapsibleSection wrapper over base-ui Collapsible

Controlled-компонент для section-level collapse/expand на табах
группы «Анализ». keepMounted=true сохраняет контент в DOM для AI-
секций с локальным state.

Spec: docs/superpowers/specs/2026-05-16-c22-analysis-collapsible-design.md
Plan: docs/superpowers/plans/2026-05-16-c22-analysis-collapsible.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Создать хук `useCollapseState`

**Files:**
- Create: `frontend/lib/use-collapse-state.ts`

**Контекст:** Хук инкапсулирует localStorage I/O и предоставляет API для toggle, collapse-all, expand-all. Схема LS — см. spec §7.

Ключевая инвариант: храним только **закрытые** секции (для compactness). Все, чего нет в записи → open. `expandAll()` = удалить запись таба (а не записывать все true).

- [ ] **Step 1: Создать `frontend/lib/use-collapse-state.ts`**

```tsx
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

export type AnalysisTabKey =
  | "results"
  | "sensitivity"
  | "pricing"
  | "value-chain"
  | "pnl";

export interface CollapseStateApi {
  /** true если секция раскрыта. Default = true для отсутствующих в LS. */
  isOpen: (sectionId: string) => boolean;
  /** Переключает один section ID. */
  toggle: (sectionId: string) => void;
  /** Все sectionIds → закрыты. */
  collapseAll: () => void;
  /** Удаляет запись таба → всё default open. */
  expandAll: () => void;
  /** true если все sectionIds открыты (для лейбла bulk-кнопки). */
  allOpen: boolean;
}

const STORAGE_KEY = "db2:analysis-collapse:v1";

interface StorageRoot {
  schema_version: 1;
  by_project: Record<
    string, // String(projectId)
    Partial<Record<AnalysisTabKey, Record<string, false>>>
  >;
}

function readStorage(): StorageRoot | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === null) return null;
    const parsed = JSON.parse(raw) as StorageRoot;
    if (parsed.schema_version !== 1) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeStorage(root: StorageRoot): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(root));
  } catch {
    // QuotaExceededError / SecurityError → silent (см. spec §11)
  }
}

/**
 * Хук для управления collapse-state секций одного таба.
 *
 * Persistence: localStorage по ключу `db2:analysis-collapse:v1`.
 * Структура — см. spec §7.1.
 *
 * Хранятся только closed-секции (для compactness). isOpen() возвращает
 * true для всего, чего нет в LS-записи. expandAll() удаляет запись.
 */
export function useCollapseState(
  projectId: number,
  tabKey: AnalysisTabKey,
  sectionIds: readonly string[],
): CollapseStateApi {
  const projectKey = String(projectId);

  // Локально храним set closed-секций как { id: true } для O(1) checks.
  const [closed, setClosed] = useState<Record<string, true>>(() => {
    const root = readStorage();
    const stored = root?.by_project[projectKey]?.[tabKey] ?? {};
    const result: Record<string, true> = {};
    for (const id of Object.keys(stored)) {
      result[id] = true;
    }
    return result;
  });

  // Persist на каждое изменение.
  useEffect(() => {
    const root: StorageRoot = readStorage() ?? {
      schema_version: 1,
      by_project: {},
    };
    const project = root.by_project[projectKey] ?? {};

    if (Object.keys(closed).length === 0) {
      // Все открыты → удаляем запись таба
      delete project[tabKey];
    } else {
      const tabRecord: Record<string, false> = {};
      for (const id of Object.keys(closed)) {
        tabRecord[id] = false;
      }
      project[tabKey] = tabRecord;
    }

    if (Object.keys(project).length === 0) {
      delete root.by_project[projectKey];
    } else {
      root.by_project[projectKey] = project;
    }

    writeStorage(root);
  }, [closed, projectKey, tabKey]);

  const isOpen = useCallback(
    (sectionId: string): boolean => !(sectionId in closed),
    [closed],
  );

  const toggle = useCallback((sectionId: string) => {
    setClosed((prev) => {
      const next = { ...prev };
      if (sectionId in next) {
        delete next[sectionId];
      } else {
        next[sectionId] = true;
      }
      return next;
    });
  }, []);

  const collapseAll = useCallback(() => {
    setClosed(() => {
      const next: Record<string, true> = {};
      for (const id of sectionIds) {
        next[id] = true;
      }
      return next;
    });
  }, [sectionIds]);

  const expandAll = useCallback(() => {
    setClosed({});
  }, []);

  const allOpen = useMemo(() => Object.keys(closed).length === 0, [closed]);

  return { isOpen, toggle, collapseAll, expandAll, allOpen };
}
```

**Что внутри:**
- `readStorage` / `writeStorage` гард `typeof window === "undefined"` для SSR-safety (App Router server components никогда не вызовут хук, но защита).
- Невалидный JSON / неверная schema_version → silent fallback на пустой стейт.
- `closed` локально хранит `{ id: true }` (compact, O(1) `in` check). В LS пишется как `{ id: false }` (за counter-intuitive значение — false означает "не открыта"). Это согласуется со spec §7.1, где «false = свёрнуто, отсутствие = развёрнуто».
- `collapseAll` использует `sectionIds`, поэтому только секции этого таба пометит. Безопасно.
- `useMemo(allOpen)` чтобы перевычислять только при изменении closed.

- [ ] **Step 2: Запустить TypeScript-проверку**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```

Expected: **0 ошибок**.

Возможные ошибки:
- `Cannot find name 'window'` — нужен `lib: ["dom"]` в `tsconfig.json` (должен уже быть для Next.js).
- Mismatch на `Partial<Record<AnalysisTabKey, Record<string, false>>>` — проверить точное написание.

- [ ] **Step 3: Закоммитить**

```bash
git add frontend/lib/use-collapse-state.ts
git commit -m "$(cat <<'EOF'
feat(c22): add useCollapseState hook with localStorage persistence

API: isOpen(id), toggle(id), collapseAll(), expandAll(), allOpen.
Хранит только closed-секции (compactness). Schema versioned:
db2:analysis-collapse:v1. SSR-safe через typeof window guards.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Создать константы section IDs

**Files:**
- Create: `frontend/lib/analysis-sections.ts`

**Контекст:** Стабильные section ID для каждого таба. Иммутабельные `as const` массивы. ID согласованы со spec §4.

- [ ] **Step 1: Создать `frontend/lib/analysis-sections.ts`**

```ts
/**
 * Стабильные section ID для каждого таба группы «Анализ».
 *
 * Используются как ключи в localStorage (см. lib/use-collapse-state.ts).
 * НЕ переименовывать без бампа `schema_version` в STORAGE_KEY — иначе
 * пользовательские collapse-state потеряются (что не катастрофа, но
 * нежелательно).
 *
 * См. spec §4 — карта секций по табам.
 */

export const RESULTS_SECTIONS = [
  "go-no-go",
  "ai-explain",
  "ai-exec-summary",
  "npv",
  "irr",
  "roi",
  "payback",
  "margins",
  "per-unit",
  "color-legend",
] as const;

export const SENSITIVITY_SECTIONS = [
  "base-values",
  "ai-interpretation",
  "tornado",
  "matrix",
] as const;

export const PRICING_SECTIONS = [
  "shelf-price",
  "ex-factory",
  "costs-margins",
] as const;

export const VALUE_CHAIN_SECTIONS = ["unit-economy"] as const;

export const PNL_SECTIONS = ["pnl"] as const;
```

- [ ] **Step 2: Запустить `tsc --noEmit`**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```

Expected: **0 ошибок**.

- [ ] **Step 3: Закоммитить**

```bash
git add frontend/lib/analysis-sections.ts
git commit -m "$(cat <<'EOF'
feat(c22): add analysis-sections.ts section ID constants

10 sections для Results, 4 для Sensitivity, 3 для Pricing, по 1 для
Value-chain и P&L. Стабильные kebab-case ID — используются как ключи
в localStorage (db2:analysis-collapse:v1).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Обернуть Results tab + bulk toggle

**Files:**
- Modify: `frontend/components/projects/results-tab.tsx`

**Контекст:** Самый большой таб — 10 секций. Bulk toggle добавить в существующий header-row (line 314, рядом с export-кнопками). Каждая «секция» уже логически отделена в JSX (см. spec §4.1), оборачиваем `<CollapsibleSection>`.

**Внимание к секциям:**
- `ai-explain` рендерится условно (`selectedScenarioId !== null`). Оборачиваем условный render — то есть `<CollapsibleSection>` внутри условия.
- `staleness-badge` (line 445) НЕ оборачиваем — это inline-уведомление.
- Все остальные секции либо `<Card>`, либо `<div>` с `<h3>`. Поскольку у `<CollapsibleSection>` свой header, удаляем `<h3>` внутри обёрнутых div'ов (заголовок переезжает в title prop).

- [ ] **Step 1: Импорты — добавить в начало файла**

В `frontend/components/projects/results-tab.tsx` найти существующий блок импортов (строки 1-48) и добавить:

```tsx
import { ChevronsDownUp, ChevronsUpDown } from "lucide-react";
import { CollapsibleSection } from "@/components/ui/collapsible";
import { RESULTS_SECTIONS } from "@/lib/analysis-sections";
import { useCollapseState } from "@/lib/use-collapse-state";
```

Импорт `Loader2` из lucide уже есть на строке 3 — добавляем `ChevronsDownUp`, `ChevronsUpDown` в тот же import:

```tsx
import { ChevronsDownUp, ChevronsUpDown, Loader2 } from "lucide-react";
```

- [ ] **Step 2: Добавить collapse-state hook**

После существующих `useState` (примерно после строки 140, после `const [exportError, setExportError] = useState<string | null>(null);`) добавить:

```tsx
  const collapse = useCollapseState(projectId, "results", RESULTS_SECTIONS);
```

- [ ] **Step 3: Добавить bulk toggle button в header-row**

Найти блок `<div className="flex items-center gap-3">` около строки 347 (контейнер с Recalculating-индикатором и export-кнопками). Перед `<Button onClick={handleExportXlsx}` (строка ~355) вставить:

```tsx
          {collapse.allOpen ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={collapse.collapseAll}
              disabled={exporting || recalculating}
            >
              <ChevronsDownUp className="mr-1.5 size-3.5" />
              Свернуть всё
            </Button>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              onClick={collapse.expandAll}
              disabled={exporting || recalculating}
            >
              <ChevronsUpDown className="mr-1.5 size-3.5" />
              Развернуть всё
            </Button>
          )}
```

- [ ] **Step 4: Обернуть `go-no-go` секцию (line 452-468)**

Найти:
```tsx
          {/* Go/No-Go hero */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base">
                    Go/No-Go решение (Y1-Y10)
                  </CardTitle>
                  <CardDescription>
                    NPV ≥ 0 AND Contribution Margin ≥ 25%
                  </CardDescription>
                </div>
                <div className="scale-150 origin-right">
                  <GoNoGoBadge value={goNoGoY1Y10} />
                </div>
              </div>
            </CardHeader>
          </Card>
```

Заменить на:
```tsx
          <CollapsibleSection
            sectionId="go-no-go"
            title="Go/No-Go решение (Y1-Y10)"
            isOpen={collapse.isOpen("go-no-go")}
            onToggle={() => collapse.toggle("go-no-go")}
          >
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardDescription>
                      NPV ≥ 0 AND Contribution Margin ≥ 25%
                    </CardDescription>
                  </div>
                  <div className="scale-150 origin-right">
                    <GoNoGoBadge value={goNoGoY1Y10} />
                  </div>
                </div>
              </CardHeader>
            </Card>
          </CollapsibleSection>
```

(Удалён `<CardTitle>` — заголовок переехал в `title` prop CollapsibleSection.)

- [ ] **Step 5: Обернуть `ai-explain` (условный, line 471-479)**

Найти:
```tsx
          {/* AI Explain KPI (Phase 7.2) — под Go/No-Go hero */}
          {selectedScenarioId !== null && (
            <ExplainKpiInline
              projectId={projectId}
              projectName={project?.name ?? "Проект"}
              scenarioId={selectedScenarioId}
              scope="y1y5"
              savedCommentary={project?.ai_kpi_commentary as Record<string, unknown> | null}
            />
          )}
```

Заменить на:
```tsx
          {selectedScenarioId !== null && (
            <CollapsibleSection
              sectionId="ai-explain"
              title="AI комментарий KPI"
              isOpen={collapse.isOpen("ai-explain")}
              onToggle={() => collapse.toggle("ai-explain")}
            >
              <ExplainKpiInline
                projectId={projectId}
                projectName={project?.name ?? "Проект"}
                scenarioId={selectedScenarioId}
                scope="y1y5"
                savedCommentary={project?.ai_kpi_commentary as Record<string, unknown> | null}
              />
            </CollapsibleSection>
          )}
```

- [ ] **Step 6: Обернуть `ai-exec-summary` (line 482-489)**

Найти:
```tsx
          {/* AI Executive Summary (Phase 7.4) */}
          <ExecutiveSummaryInline
            projectId={projectId}
            projectName="Проект"
            savedSummary={null}
            onSaved={() => {
              /* В 7.5 — refresh project data */
            }}
          />
```

Заменить на:
```tsx
          <CollapsibleSection
            sectionId="ai-exec-summary"
            title="AI Executive Summary"
            isOpen={collapse.isOpen("ai-exec-summary")}
            onToggle={() => collapse.toggle("ai-exec-summary")}
          >
            <ExecutiveSummaryInline
              projectId={projectId}
              projectName="Проект"
              savedSummary={null}
              onSaved={() => {
                /* В 7.5 — refresh project data */
              }}
            />
          </CollapsibleSection>
```

- [ ] **Step 7: Обернуть `npv` row (line 492-515)**

Найти:
```tsx
          {/* NPV row */}
          <div>
            <h3 className="mb-2 text-sm font-semibold text-muted-foreground">
              NPV (чистая приведённая стоимость)
            </h3>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              {SCOPE_ORDER.map((scope) => {
                const r = resultsByScope[scope];
                return (
                  <KpiCard
                    key={scope}
                    label={SCOPE_LABELS[scope]}
                    value={formatMoney(r?.npv ?? null)}
                    valueClassName={
                      r?.npv !== undefined &&
                      r.npv !== null &&
                      Number(r.npv) >= 0
                        ? "text-green-600"
                        : "text-red-600"
                    }
                  />
                );
              })}
            </div>
          </div>
```

Заменить на:
```tsx
          <CollapsibleSection
            sectionId="npv"
            title="NPV (чистая приведённая стоимость)"
            isOpen={collapse.isOpen("npv")}
            onToggle={() => collapse.toggle("npv")}
          >
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              {SCOPE_ORDER.map((scope) => {
                const r = resultsByScope[scope];
                return (
                  <KpiCard
                    key={scope}
                    label={SCOPE_LABELS[scope]}
                    value={formatMoney(r?.npv ?? null)}
                    valueClassName={
                      r?.npv !== undefined &&
                      r.npv !== null &&
                      Number(r.npv) >= 0
                        ? "text-green-600"
                        : "text-red-600"
                    }
                  />
                );
              })}
            </div>
          </CollapsibleSection>
```

(Удалены wrapper `<div>` и `<h3>` — `<CollapsibleSection>` сам формирует header + space-y-2 + pt-1 контент.)

- [ ] **Step 8: Обернуть `irr` row (~line 518-534)**

Найти `<h3>` с текстом `IRR (внутренняя норма доходности)`, найти его `<div>` wrapper, заменить аналогично Step 7 на:

```tsx
          <CollapsibleSection
            sectionId="irr"
            title="IRR (внутренняя норма доходности)"
            isOpen={collapse.isOpen("irr")}
            onToggle={() => collapse.toggle("irr")}
          >
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              {SCOPE_ORDER.map((scope) => {
                const r = resultsByScope[scope];
                return (
                  <KpiCard
                    key={scope}
                    label={SCOPE_LABELS[scope]}
                    value={formatPercent(r?.irr ?? null)}
                  />
                );
              })}
            </div>
          </CollapsibleSection>
```

- [ ] **Step 9: Обернуть `roi` row (~line 537-553)**

Аналогично, для секции «ROI (возврат на инвестиции)»:

```tsx
          <CollapsibleSection
            sectionId="roi"
            title="ROI (возврат на инвестиции)"
            isOpen={collapse.isOpen("roi")}
            onToggle={() => collapse.toggle("roi")}
          >
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              {SCOPE_ORDER.map((scope) => {
                const r = resultsByScope[scope];
                return (
                  <KpiCard
                    key={scope}
                    label={SCOPE_LABELS[scope]}
                    value={formatPercent(r?.roi ?? null)}
                  />
                );
              })}
            </div>
          </CollapsibleSection>
```

- [ ] **Step 10: Обернуть `payback` row (~line 556-574)**

```tsx
          <CollapsibleSection
            sectionId="payback"
            title="Payback (срок окупаемости, Y1-Y10)"
            isOpen={collapse.isOpen("payback")}
            onToggle={() => collapse.toggle("payback")}
          >
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <KpiCard
                label="Простой"
                value={formatPayback(
                  resultsByScope.y1y10?.payback_simple ?? null,
                )}
              />
              <KpiCard
                label="Дисконтированный"
                value={formatPayback(
                  resultsByScope.y1y10?.payback_discounted ?? null,
                )}
              />
            </div>
          </CollapsibleSection>
```

- [ ] **Step 11: Обернуть `margins` row (~line 577-594)**

```tsx
          <CollapsibleSection
            sectionId="margins"
            title="Маржинальность (overall)"
            isOpen={collapse.isOpen("margins")}
            onToggle={() => collapse.toggle("margins")}
          >
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <KpiCard
                label="Contribution Margin"
                value={formatPercent(cmRatio)}
                valueClassName={marginClass(cmRatio)}
                subtitle="Порог Go/No-Go: ≥ 25%"
              />
              <KpiCard
                label="EBITDA Margin"
                value={formatPercent(ebitdaMargin)}
                valueClassName={marginClass(ebitdaMargin)}
              />
            </div>
          </CollapsibleSection>
```

- [ ] **Step 12: Обернуть `per-unit` секцию (~line 597-654)**

Найти комментарий `{/* Per-unit metrics (Phase 8.3) */}` и wrap `<div>` с заголовком + table:

```tsx
          <CollapsibleSection
            sectionId="per-unit"
            title="Per-unit экономика (средняя за период)"
            isOpen={collapse.isOpen("per-unit")}
            onToggle={() => collapse.toggle("per-unit")}
          >
            <div className="overflow-x-auto">
              <table className="w-full text-xs border-collapse">
                <thead>
                  <tr className="border-b">
                    <th className="px-2 py-1.5 text-left font-medium text-muted-foreground">
                      Показатель
                    </th>
                    {SCOPE_ORDER.map((scope) => (
                      <th key={scope} className="px-2 py-1.5 text-right font-medium" colSpan={2}>
                        {SCOPE_LABELS[scope]}
                      </th>
                    ))}
                  </tr>
                  <tr className="border-b">
                    <th />
                    {SCOPE_ORDER.map((scope) => (
                      <Fragment key={scope}>
                        <th className="px-2 py-1 text-right text-[10px] font-medium text-muted-foreground">
                          ₽/шт
                        </th>
                        <th className="px-2 py-1 text-right text-[10px] font-medium text-muted-foreground">
                          ₽/(л/кг)
                        </th>
                      </Fragment>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {PER_UNIT_ROWS.map((row) => (
                    <tr key={row.key} className="border-b last:border-0 hover:bg-muted/30">
                      <td className={`px-2 py-1.5 whitespace-nowrap ${row.bold ? "font-medium" : ""}`}>
                        {row.label}
                      </td>
                      {SCOPE_ORDER.map((scope) => {
                        const r = resultsByScope[scope];
                        const u = (r?.[row.unitField] as string | null) ?? null;
                        const l = (r?.[row.literField] as string | null) ?? null;
                        return (
                          <Fragment key={scope}>
                            <td className="px-2 py-1.5 text-right tabular-nums">
                              {formatMoneyPerUnit(u)}
                            </td>
                            <td className="px-2 py-1.5 text-right tabular-nums">
                              {formatMoneyPerUnit(l)}
                            </td>
                          </Fragment>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CollapsibleSection>
```

(Удалён `<h3>` — title в prop.)

- [ ] **Step 13: Обернуть `color-legend` (~line 656-661)**

Найти:
```tsx
          {/* Color legend (Phase 8.6) */}
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span>Цветовая индикация:</span>
            <span className="text-green-600 font-semibold">NPV &ge; 0 / маржа &ge; 25%</span>
            <span className="text-yellow-600 font-semibold">маржа 15-25%</span>
            <span className="text-red-600 font-semibold">NPV &lt; 0 / маржа &lt; 15%</span>
          </div>
```

Заменить на:
```tsx
          <CollapsibleSection
            sectionId="color-legend"
            title="Цветовая индикация"
            isOpen={collapse.isOpen("color-legend")}
            onToggle={() => collapse.toggle("color-legend")}
          >
            <div className="flex items-center gap-4 text-xs text-muted-foreground">
              <span className="text-green-600 font-semibold">NPV &ge; 0 / маржа &ge; 25%</span>
              <span className="text-yellow-600 font-semibold">маржа 15-25%</span>
              <span className="text-red-600 font-semibold">NPV &lt; 0 / маржа &lt; 15%</span>
            </div>
          </CollapsibleSection>
```

(Удалён `<span>Цветовая индикация:</span>` — это переехало в title.)

- [ ] **Step 14: `tsc --noEmit`**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```

Expected: **0 ошибок**.

- [ ] **Step 15: Restart frontend с purge `.next`**

```bash
docker compose -f infra/docker-compose.dev.yml stop frontend
docker compose -f infra/docker-compose.dev.yml run --rm frontend sh -c "rm -rf .next/* .next/.[!.]* 2>/dev/null"
docker compose -f infra/docker-compose.dev.yml up -d frontend
```

Подождать ~10 сек, убедиться `dbpassport-dev-frontend-1   Up <время>`:

```bash
docker compose -f infra/docker-compose.dev.yml ps frontend
```

- [ ] **Step 16: Manual smoke в браузере**

Открыть `http://localhost:3000/projects/<id>` → таб «Результаты». Чек-лист:

1. Все 10 секций раскрыты (default).
2. Каждая секция имеет header-кнопку с chevron справа (▼).
3. Клик на header «NPV» → секция плавно сворачивается, chevron → ▶.
4. Клик на header «NPV» снова → разворачивается обратно.
5. Кнопка «Свернуть всё» в правом верхнем углу (рядом с XLSX/PPTX/PDF). Клик → все секции свёрнуты, лейбл сменился на «Развернуть всё».
6. Клик «Развернуть всё» → все раскрылись.
7. F5 → если последнее состояние было «всё свёрнуто», после reload — всё свёрнуто.
8. Сменить scenario в Select → секции не моргают (state-based, не data-based).
9. Запустить «Пересчитать» → секции, развёрнутые до этого, остаются развёрнутыми.

Если все 9 пунктов ok — Task 4 готов. Иначе откатить step и разобраться.

- [ ] **Step 17: Закоммитить**

```bash
git add frontend/components/projects/results-tab.tsx
git commit -m "$(cat <<'EOF'
feat(c22): wrap results-tab sections in CollapsibleSection

10 секций обёрнуты: go-no-go, ai-explain, ai-exec-summary, npv, irr,
roi, payback, margins, per-unit, color-legend. Bulk toggle «Свернуть/
Развернуть всё» добавлен в header-row рядом с export-кнопками.

Заголовки секций перенесены из <h3>/<CardTitle> в title prop
<CollapsibleSection>; внутренние <div> wrappers удалены за избыточностью
(space-y-2 даёт <CollapsibleSection>).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Обернуть Sensitivity tab + bulk toggle

**Files:**
- Modify: `frontend/components/projects/sensitivity-tab.tsx`

**Контекст:** 4 секции (`base-values`, `ai-interpretation`, `tornado`, `matrix`). Bulk toggle добавить в существующий header-row (line 147-171, контейнер с Select + Recalculate button).

- [ ] **Step 1: Добавить импорты**

Добавить в существующие импорты (1-36):

```tsx
import { ChevronsDownUp, ChevronsUpDown } from "lucide-react";
import { CollapsibleSection } from "@/components/ui/collapsible";
import { SENSITIVITY_SECTIONS } from "@/lib/analysis-sections";
import { useCollapseState } from "@/lib/use-collapse-state";
```

- [ ] **Step 2: Добавить хук**

После существующих `useState`-блоков (после строки 97 `const [scope, setScope] = useState<string>("y1y10");`) добавить:

```tsx
  const collapse = useCollapseState(projectId, "sensitivity", SENSITIVITY_SECTIONS);
```

- [ ] **Step 3: Добавить bulk toggle button**

Найти `<div className="flex items-center gap-3">` (строка 147). Перед `<Select>` (строка 148) вставить:

```tsx
          {collapse.allOpen ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={collapse.collapseAll}
              disabled={loading}
            >
              <ChevronsDownUp className="mr-1.5 size-3.5" />
              Свернуть всё
            </Button>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              onClick={collapse.expandAll}
              disabled={loading}
            >
              <ChevronsUpDown className="mr-1.5 size-3.5" />
              Развернуть всё
            </Button>
          )}
```

- [ ] **Step 4: Обернуть `base-values` (line 188-220)**

Найти `{/* Base reference card */}` + `<Card>...</Card>`. Заменить на:

```tsx
          <CollapsibleSection
            sectionId="base-values"
            title="Базовые значения"
            isOpen={collapse.isOpen("base-values")}
            onToggle={() => collapse.toggle("base-values")}
          >
            <Card>
              <CardHeader>
                <CardDescription>
                  Точка отсчёта для всех ячеек ниже (базовый сценарий).
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div>
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">
                      NPV {SCOPE_OPTIONS.find((o) => o.value === scope)?.label ?? scope}
                    </p>
                    <p className="mt-1 text-xl font-semibold">
                      {data.base_npv_y1y10 === null
                        ? "—"
                        : formatMoney(String(data.base_npv_y1y10))}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">
                      Contribution Margin
                    </p>
                    <p className="mt-1 text-xl font-semibold">
                      {data.base_cm_ratio === null
                        ? "—"
                        : formatPercent(String(data.base_cm_ratio))}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </CollapsibleSection>
```

(Удалён `<CardTitle>` — переехал в title prop.)

- [ ] **Step 5: Обернуть `ai-interpretation` (line 222-230)**

Найти:
```tsx
          {/* AI interpretation (Phase 7.3) */}
          {baseScenarioId !== null && (
            <ExplainSensitivityInline
              projectId={projectId}
              projectName={project?.name ?? "Проект"}
              scenarioId={baseScenarioId}
              savedCommentary={project?.ai_sensitivity_commentary as Record<string, unknown> | null}
            />
          )}
```

Заменить на:
```tsx
          {baseScenarioId !== null && (
            <CollapsibleSection
              sectionId="ai-interpretation"
              title="AI интерпретация чувствительности"
              isOpen={collapse.isOpen("ai-interpretation")}
              onToggle={() => collapse.toggle("ai-interpretation")}
            >
              <ExplainSensitivityInline
                projectId={projectId}
                projectName={project?.name ?? "Проект"}
                scenarioId={baseScenarioId}
                savedCommentary={project?.ai_sensitivity_commentary as Record<string, unknown> | null}
              />
            </CollapsibleSection>
          )}
```

- [ ] **Step 6: Обернуть `tornado` (line 232-233)**

Найти:
```tsx
          {/* B-11: Tornado chart */}
          <TornadoChart data={data} />
```

Заменить на:
```tsx
          <CollapsibleSection
            sectionId="tornado"
            title="Tornado-диаграмма"
            isOpen={collapse.isOpen("tornado")}
            onToggle={() => collapse.toggle("tornado")}
          >
            <TornadoChart data={data} />
          </CollapsibleSection>
```

- [ ] **Step 7: Обернуть `matrix` (line 235-317)**

Найти `{/* Sensitivity table */}` + `<Card>...</Card>`. Заменить начало:

```tsx
          <CollapsibleSection
            sectionId="matrix"
            title="Матрица 5 × 4 (NPV / CM%)"
            isOpen={collapse.isOpen("matrix")}
            onToggle={() => collapse.toggle("matrix")}
          >
            <Card>
              <CardHeader>
                <CardDescription>
                  Строки = уровни изменения (−20%..+20%). Колонки = параметры.
                  Каждая ячейка: NPV Y1-Y10 (главное) и Contribution Margin
                  (мелким серым).
                </CardDescription>
              </CardHeader>
              <CardContent>
                {/* ...table content без изменений (строки 248-307)... */}
                {/* ...mt-3 legend без изменений (строки 308-315)... */}
              </CardContent>
            </Card>
          </CollapsibleSection>
```

Конкретно: удалить `<CardTitle>` (строки 238-240), заменить `<Card>` на обёртку выше; контент Card не меняется. Закрывающий `</CollapsibleSection>` ставится перед `</>` (line 318).

- [ ] **Step 8: `tsc --noEmit`**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```

Expected: **0 ошибок**.

- [ ] **Step 9: Restart frontend + purge .next** (как в Task 4 Step 15).

- [ ] **Step 10: Manual smoke**

Открыть `/projects/<id>` → «Чувствительность». Проверки:
1. 4 секции раскрыты по дефолту.
2. Chevron работает на каждой.
3. Bulk toggle в верхнем правом (рядом с Select scope + Пересчитать).
4. F5 — persistence работает.
5. AI секция (если `baseScenarioId` есть) — обёрнута, состояние сохраняется при появлении/исчезании.

- [ ] **Step 11: Закоммитить**

```bash
git add frontend/components/projects/sensitivity-tab.tsx
git commit -m "$(cat <<'EOF'
feat(c22): wrap sensitivity-tab sections in CollapsibleSection

4 секции: base-values, ai-interpretation, tornado, matrix. Bulk toggle
добавлен в header-row рядом с scope Select + Пересчитать.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Обернуть Pricing tab + bulk toggle

**Files:**
- Modify: `frontend/components/projects/pricing-tab.tsx`

**Контекст:** 3 секции (`shelf-price`, `ex-factory`, `costs-margins`). В этом табе **нет** существующих контролов сверху — добавить новую панель `<div className="flex justify-end">` для bulk toggle. Сейчас таб начинается с `<div className="space-y-6">` сразу с Card'ов.

- [ ] **Step 1: Добавить импорты**

```tsx
import { ChevronsDownUp, ChevronsUpDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CollapsibleSection } from "@/components/ui/collapsible";
import { PRICING_SECTIONS } from "@/lib/analysis-sections";
import { useCollapseState } from "@/lib/use-collapse-state";
```

(`Button` импорта в файле нет — добавляем впервые.)

- [ ] **Step 2: Добавить хук**

В `PricingTab` после `const [loading, setLoading] = useState(true);` (строка 65) добавить:

```tsx
  const collapse = useCollapseState(projectId, "pricing", PRICING_SECTIONS);
```

- [ ] **Step 3: Добавить bulk toggle перед первой секцией**

Найти `<div className="space-y-6">` (строка 97). Сразу внутри (перед `{/* Shelf Prices Table */}`) вставить:

```tsx
      <div className="flex justify-end">
        {collapse.allOpen ? (
          <Button variant="ghost" size="sm" onClick={collapse.collapseAll}>
            <ChevronsDownUp className="mr-1.5 size-3.5" />
            Свернуть всё
          </Button>
        ) : (
          <Button variant="ghost" size="sm" onClick={collapse.expandAll}>
            <ChevronsUpDown className="mr-1.5 size-3.5" />
            Развернуть всё
          </Button>
        )}
      </div>
```

- [ ] **Step 4: Обернуть `shelf-price` (line 98-138)**

Найти `{/* Shelf Prices Table */}` + `<Card>...</Card>`. Заменить начало `<Card>`:

```tsx
      <CollapsibleSection
        sectionId="shelf-price"
        title="Цена полки (₽/шт)"
        isOpen={collapse.isOpen("shelf-price")}
        onToggle={() => collapse.toggle("shelf-price")}
      >
        <Card>
          <CardContent className="overflow-x-auto pt-6">
            {/* ...table contents без изменений (строки 104-136)... */}
          </CardContent>
        </Card>
      </CollapsibleSection>
```

Заметки:
- Удалить `<CardHeader>` и `<CardTitle>` целиком (заголовок в `title` prop).
- К `<CardContent>` добавить `pt-6` (компенсация удалённого header'а).

- [ ] **Step 5: Обернуть `ex-factory` (line 141-179)**

Аналогично:

```tsx
      <CollapsibleSection
        sectionId="ex-factory"
        title={
          <>
            Цена отгрузки / Ex-Factory (₽/шт)
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              НДС {pct(data.vat_rate)}
            </span>
          </>
        }
        isOpen={collapse.isOpen("ex-factory")}
        onToggle={() => collapse.toggle("ex-factory")}
      >
        <Card>
          <CardContent className="overflow-x-auto pt-6">
            {/* ...table contents без изменений (строки 150-178)... */}
          </CardContent>
        </Card>
      </CollapsibleSection>
```

Заметка: `title` принимает `ReactNode` — JSX с `<span>` НДС-аннотации сохранён.

- [ ] **Step 6: Обернуть `costs-margins` (line 181-223)**

```tsx
      <CollapsibleSection
        sectionId="costs-margins"
        title="Себестоимость и маржи"
        isOpen={collapse.isOpen("costs-margins")}
        onToggle={() => collapse.toggle("costs-margins")}
      >
        <Card>
          <CardContent className="overflow-x-auto pt-6">
            {/* ...table contents без изменений (строки 186-222)... */}
          </CardContent>
        </Card>
      </CollapsibleSection>
```

- [ ] **Step 7: `tsc --noEmit`**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```

Expected: **0 ошибок**.

- [ ] **Step 8: Restart frontend + purge .next**

- [ ] **Step 9: Manual smoke**

`/projects/<id>` → «Цены». Проверки:
1. 3 секции раскрыты.
2. Bulk toggle сверху справа.
3. Chevron работает.
4. F5 — persistence.
5. НДС badge в title `ex-factory` отображается корректно.

- [ ] **Step 10: Закоммитить**

```bash
git add frontend/components/projects/pricing-tab.tsx
git commit -m "$(cat <<'EOF'
feat(c22): wrap pricing-tab sections in CollapsibleSection

3 секции: shelf-price, ex-factory, costs-margins. Bulk toggle добавлен
в новую панель сверху (в табе не было top-controls раньше).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Обернуть Value-chain и P&L (без bulk toggle)

**Files:**
- Modify: `frontend/components/projects/value-chain-tab.tsx`
- Modify: `frontend/components/projects/pnl-tab.tsx`

**Контекст:** В обоих табах ровно 1 секция, поэтому bulk toggle не делаем (spec §8.1). Хук всё равно используем (для consistency и persistence в LS — single section может быть свёрнута).

### Sub-task 7a: Value-chain (1 секция)

- [ ] **Step 1: Добавить импорты в `value-chain-tab.tsx`**

```tsx
import { CollapsibleSection } from "@/components/ui/collapsible";
import { VALUE_CHAIN_SECTIONS } from "@/lib/analysis-sections";
import { useCollapseState } from "@/lib/use-collapse-state";
```

- [ ] **Step 2: Добавить хук в `ValueChainTab`**

После `const [isStale, setIsStale] = useState(false);` (строка 126) добавить:

```tsx
  const collapse = useCollapseState(projectId, "value-chain", VALUE_CHAIN_SECTIONS);
```

- [ ] **Step 3: Обернуть Card (line 181-278)**

Найти `<Card>` с заголовком `<CardTitle>Unit-экономика (₽/шт) ...</CardTitle>` (line 181-189). Заменить на:

```tsx
      <CollapsibleSection
        sectionId="unit-economy"
        title={
          <>
            Unit-экономика (&#8381;/шт)
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              НДС {pct(data.vat_rate)} &middot; per-unit экономика на базовый период
            </span>
          </>
        }
        isOpen={collapse.isOpen("unit-economy")}
        onToggle={() => collapse.toggle("unit-economy")}
      >
        <Card>
          <CardContent className="overflow-x-auto pt-6">
            {/* ...table contents без изменений (строки 191-277)... */}
          </CardContent>
        </Card>
      </CollapsibleSection>
```

Удалить `<CardHeader>` и `<CardTitle>` целиком. Закрывающий `</Card>` остаётся; `</CollapsibleSection>` после него.

- [ ] **Step 4: `tsc --noEmit`**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```

Expected: **0 ошибок**.

### Sub-task 7b: P&L (1 секция)

- [ ] **Step 5: Импорты в `pnl-tab.tsx`**

```tsx
import { CollapsibleSection } from "@/components/ui/collapsible";
import { PNL_SECTIONS } from "@/lib/analysis-sections";
import { useCollapseState } from "@/lib/use-collapse-state";
```

- [ ] **Step 6: Хук в `PnlTab`**

После `const [isStale, setIsStale] = useState(false);` (строка 148) добавить:

```tsx
  const collapse = useCollapseState(projectId, "pnl", PNL_SECTIONS);
```

- [ ] **Step 7: Обернуть Card (line 216-264)**

Найти `<Card>` с `<CardTitle>P&L — {MODE_LABELS[mode]}</CardTitle>` (line 216-221). Заменить на:

```tsx
      <CollapsibleSection
        sectionId="pnl"
        title={`P&L — ${MODE_LABELS[mode]}`}
        isOpen={collapse.isOpen("pnl")}
        onToggle={() => collapse.toggle("pnl")}
      >
        <Card>
          <CardContent className="overflow-x-auto pt-6">
            {/* ...table contents без изменений (строки 223-263)... */}
          </CardContent>
        </Card>
      </CollapsibleSection>
```

- [ ] **Step 8: `tsc --noEmit`**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```

Expected: **0 ошибок**.

- [ ] **Step 9: Restart frontend + purge .next**

```bash
docker compose -f infra/docker-compose.dev.yml stop frontend
docker compose -f infra/docker-compose.dev.yml run --rm frontend sh -c "rm -rf .next/* .next/.[!.]* 2>/dev/null"
docker compose -f infra/docker-compose.dev.yml up -d frontend
```

- [ ] **Step 10: Manual smoke на обоих**

Value-chain: открыть таб → 1 секция «Unit-экономика» имеет chevron, сворачивается, F5 сохраняет state. **Bulk toggle не должен присутствовать.**

P&L: открыть таб → 1 секция «P&L — Кварталы» (или Месяцы/Годы по mode). Mode-toggle buttons остаются над секцией. Chevron работает, persistence работает. **Bulk toggle не должен присутствовать.**

- [ ] **Step 11: Закоммитить (один коммит на оба таба)**

```bash
git add frontend/components/projects/value-chain-tab.tsx frontend/components/projects/pnl-tab.tsx
git commit -m "$(cat <<'EOF'
feat(c22): wrap value-chain and pnl single sections in CollapsibleSection

По 1 секции на табе → bulk toggle намеренно не добавляем (spec §8.1).
useCollapseState всё равно используется для consistency и LS persistence.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Документация — STATUS + CHANGELOG

**Files:**
- Modify: `docs/CLIENT_FEEDBACK_v2_STATUS.md` (line 38)
- Modify: `CHANGELOG.md` (`## Phase C` → `### Added`)

- [ ] **Step 1: Обновить STATUS**

В `docs/CLIENT_FEEDBACK_v2_STATUS.md` найти строку 38:

```
| Collapse/expand разделов | ❌ | Глобального механизма свёртывания блоков отчёта нет. Только локальные expansions: `financial-plan-editor` раскрывает OPEX-разбивку, `value-chain-tab` / `channels-panel` / `sensitivity-tab` имеют локальные раскрытия. Сохранение состояния между сессиями — нет. |
```

Заменить на:

```
| Collapse/expand разделов | ✅ | Закрыто C #22 (2026-05-16). Section-level collapse добавлен на 5 табах группы «Анализ» (Results, Sensitivity, Pricing, Value-chain, P&L) через wrapper `<CollapsibleSection>` поверх `@base-ui/react/collapsible`. Persistence — localStorage по ключу `db2:analysis-collapse:v1` (projectId × tabKey × sectionId). Bulk toggle «Свернуть/Развернуть всё» в табах с >1 секциями (Results 10, Sensitivity 4, Pricing 3). Локальные row-level раскрытия не тронуты. См. spec `docs/superpowers/specs/2026-05-16-c22-analysis-collapsible-design.md`. |
```

Также обновить строку 270 (если есть запись «13. Collapse/expand разделов»):

Найти:
```
13. **Collapse/expand разделов** (1.2, ❌).
```

Заменить на:
```
13. **Collapse/expand разделов** (1.2, ✅ — закрыто C #22 2026-05-16).
```

- [ ] **Step 2: Добавить запись в `CHANGELOG.md`**

Открыть `CHANGELOG.md`, найти `## Phase C` → `### Added` (под существующей C #14 записью, перед `### Changed`). После строки с C #14 добавить:

```markdown
- **C #22 Collapse/expand разделов «Анализ» (MEMO 1.3, 2026-05-16).**
  Section-level collapse/expand на 5 табах группы ⑤ «Анализ»: Results
  (10 секций), Sensitivity (4), Pricing (3), Value-chain (1), P&L (1).
  Новый wrapper `<CollapsibleSection>` поверх `@base-ui/react/collapsible`
  + хук `useCollapseState` с localStorage persistence по (projectId,
  tabKey, sectionId). Bulk toggle «Свернуть/Развернуть всё» в табах с
  >1 секциями. Backend/БД/API не тронуты; экспорт PDF/PPTX/XLSX
  игнорирует collapse-state (всегда полный отчёт).
  - Spec: `docs/superpowers/specs/2026-05-16-c22-analysis-collapsible-design.md`
  - Plan: `docs/superpowers/plans/2026-05-16-c22-analysis-collapsible.md`
  - Verification: `npx tsc --noEmit` 0 ошибок; manual smoke на всех 5 табах ok.
```

- [ ] **Step 3: Закоммитить**

```bash
git add docs/CLIENT_FEEDBACK_v2_STATUS.md CHANGELOG.md
git commit -m "$(cat <<'EOF'
docs(c22): close MEMO 1.3 — collapse/expand разделов «Анализ»

- docs/CLIENT_FEEDBACK_v2_STATUS.md: статус ❌ → ✅ для строк 38 и 270.
- CHANGELOG.md: запись C #22 в Phase C ### Added.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Финальная проверка + merge

**Files:** (verification + merge)

- [ ] **Step 1: Проверить ветку**

```bash
git status
git log --oneline main..HEAD
```

Expected (8 коммитов на ветке, плюс spec-коммит):
```
<hash> docs(c22): close MEMO 1.3 — collapse/expand разделов «Анализ»
<hash> feat(c22): wrap value-chain and pnl single sections in CollapsibleSection
<hash> feat(c22): wrap pricing-tab sections in CollapsibleSection
<hash> feat(c22): wrap sensitivity-tab sections in CollapsibleSection
<hash> feat(c22): wrap results-tab sections in CollapsibleSection
<hash> feat(c22): add analysis-sections.ts section ID constants
<hash> feat(c22): add useCollapseState hook with localStorage persistence
<hash> feat(c22): add CollapsibleSection wrapper over base-ui Collapsible
ce09125 docs(c22): spec — collapse/expand разделов группы «Анализ»
```

(`git status` clean.)

- [ ] **Step 2: Финальная статика — tsc**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```

Expected: **0 ошибок**.

- [ ] **Step 3: Финальный backend pytest (страховка — мы бэк не трогали, должно остаться 508 passed)**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration 2>&1 | tail -3
```

Expected: `508 passed`.

- [ ] **Step 4: Final manual smoke — все 5 табов**

Открыть `http://localhost:3000/projects/<id>` и пройти по табам ⑤ «Анализ» подряд:
- **Результаты** → 10 секций, bulk toggle, F5 persist.
- **Чувствительность** → 4 секции, bulk toggle.
- **Цены** → 3 секции, bulk toggle, НДС в title ex-factory.
- **Unit-экономика** → 1 секция, **без** bulk toggle.
- **P&L** → 1 секция, mode-toggle над секцией, **без** bulk toggle.

Проверить, что в localStorage появилась запись:
- Открыть DevTools → Application → Local Storage → `http://localhost:3000` → ключ `db2:analysis-collapse:v1`.
- Свернуть несколько секций → значение обновляется в реальном времени (refresh DevTools).
- `expandAll` (Развернуть всё) → запись для таба удаляется; если все табы expanded — ключ либо пустой `by_project: {}`, либо его нет.

- [ ] **Step 5: Спросить пользователя о merge стратегии**

Подобно C #13:
- **fast-forward** (`--ff-only`) — все 9 коммитов в линейной истории main; default для атомарной задачи такого размера.
- **--no-ff** — сохраняет «эпиковый» merge commit (как C #14); хорошо если ретроспективно видеть, какие коммиты были в одной задаче.
- **squash** — 1 commit на main; сжимает 9 коммитов в один, теряя гранулярность.

Рекомендация: **fast-forward** (как C #13). 9 коммитов в линейной истории, каждый атомарен и осмыслен.

**НЕ мержить без подтверждения пользователя.**

- [ ] **Step 6: После approval — merge**

Пример (fast-forward):
```bash
git checkout main
git merge feat/c22-analysis-collapsible --ff-only
git log --oneline -12
```

- [ ] **Step 7: Удалить ветку**

```bash
git branch -d feat/c22-analysis-collapsible
git branch
```

Expected: `* main`, без `feat/c22-*`.

- [ ] **Step 8: Краткий отчёт пользователю**

- C #22 закрыт; ветка смержена в main, удалена.
- Изменены 5 файлов фронтенда (5 таб-компонентов), добавлены 3 новых файла (CollapsibleSection wrapper + хук + section ID константы).
- STATUS и CHANGELOG обновлены.
- Tests: 508 backend passed, tsc 0 ошибок, manual smoke ok на всех 5 табах.
- Phase C: 3/18 ✅ (#14 + #13 + #22).
- Следующий кандидат — по рекомендации GO4: #16 (каналы группы) или #17 (АКБ) для unblock #15/#18.

---

## Self-review checklist

- ✅ **Spec coverage:**
  - §1 Goal/User Stories → Tasks 1-7 implement core feature; Task 4 step 16 / Task 9 step 4 проверяют US-1 (focus on NPV), US-2 (bulk toggle), US-3 (F5 persist), US-4 (independent per project).
  - §2 Out of scope → плэн НЕ трогает другие группы, backend, экспорт, server preferences. ✓
  - §3 Architecture → Tasks 1-3 создают 3 новых файла как описано. ✓
  - §4 Карта секций → IDs в Task 3 совпадают с §4.1-4.5. Wrap-операции в Tasks 4-7 покрывают все секции из §4. ✓
  - §5 CollapsibleSection contract → реализован в Task 1; controlled, без defaultOpen. ✓
  - §6 useCollapseState contract → реализован в Task 2; API подпись совпадает. ✓
  - §7 LocalStorage schema → реализована в Task 2 (`STORAGE_KEY`, schema_version проверка, fallback на null). ✓
  - §8 Bulk toggle UX → Tasks 4 (Results), 5 (Sensitivity), 6 (Pricing) добавляют bulk toggle; Task 7 НЕ добавляет (1 секция). ✓
  - §9 Existing local expansions → плэн их НЕ трогает. ✓
  - §10 Testing strategy → tsc + manual smoke в каждой Task'е; §10.4 acceptance criteria покрыты Task 9 Step 4. ✓
  - §11 Edge cases → SSR-guard в Task 2; keepMounted=true в Task 1 (AI секции переживают collapse). ✓
  - §12 Non-goals → плэн не реализует. ✓
  - §13 File map → совпадает с Tasks. ✓
  - §14 Branch/commits → 9 коммитов, fast-forward merge — соответствует. ✓

- ✅ **Placeholders:** Нет TBD / TODO / «implement later». Все code blocks — конкретные.

- ✅ **Type consistency:**
  - `AnalysisTabKey` literal union: `"results" | "sensitivity" | "pricing" | "value-chain" | "pnl"` — совпадает в `useCollapseState` (Task 2) и в первом аргументе хука в Tasks 4-7. ✓
  - `CollapsibleSectionProps` — `sectionId: string`, `title: ReactNode`, `isOpen: boolean`, `onToggle: () => void`, `children: ReactNode`, `className?: string` — везде используется одинаково. ✓
  - `CollapseStateApi.isOpen(sectionId: string): boolean` — все вызовы передают string. ✓
  - `STORAGE_KEY = "db2:analysis-collapse:v1"` — соответствует spec §7.1. ✓
  - lucide icons: `ChevronDown` (Task 1), `ChevronsDownUp` + `ChevronsUpDown` (Tasks 4, 5, 6) — все верифицированы в node_modules. ✓

- ✅ **Scope:** Plan строго в рамках spec'a. Не добавляет «улучшайзинг»: bulk toggle ровно где спека сказала (>1 секции), title-prop вместо CardTitle везде одинаково, никаких feature-флагов / экспериментальных режимов.

- ✅ **Decomposition:** 9 атомарных task'ов; каждый коммит самодостаточен. Tasks 4-7 параллелизуемы (5 разных файлов, независимые правки), что хорошо для subagent-driven workflow.
