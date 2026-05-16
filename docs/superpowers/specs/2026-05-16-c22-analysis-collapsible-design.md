# C #22 — Collapse/expand разделов группы «Анализ» (design)

> **Brainstorm session:** 2026-05-16
> **Источник:** MEMO 1.3 / CLIENT_FEEDBACK_v2.md:23 («скрытие/раскрытие блоков — особенно актуально при выводе в отчёт») + STATUS BL-#22.
> **Scope category:** UX / навигация. Чисто frontend, без БД/API.

---

## §1. Цель

Дать пользователю возможность сворачивать/разворачивать секции на табах группы ⑤ «Анализ» (Results, Sensitivity, Pricing, Value-chain, P&L) — чтобы фокусироваться на нужных KPI без скролла мимо нерелевантного. Состояние сворачивания **сохраняется между сессиями в localStorage** на уровне (projectId, tabKey, sectionId).

### §1.1 User stories

- **US-1.** Как маркетолог, открывший результаты расчёта, я хочу свернуть «AI executive summary», чтобы быстрее видеть NPV/IRR/Payback на одном экране.
- **US-2.** Как аналитик, я хочу одним кликом «Свернуть всё» свернуть все разделы и потом точечно раскрывать нужное.
- **US-3.** Как пользователь, я хочу, чтобы после `F5` мои свёрнутые секции остались свёрнутыми, потому что я работаю с одним проектом часами.
- **US-4.** Как пользователь, переключающийся между проектами, я хочу, чтобы collapse-state у проектов был независим (свернул в проекте А → проект Б открыл с дефолтом).

---

## §2. Out of scope (что НЕ делаем)

| Что | Почему |
|---|---|
| Collapse в табах группы ① Основа / ③ Дистрибуция / ④ Моделирование | Только «отчётные» табы по решению пользователя в брейнсторме. |
| Backend изменения (новые таблицы, миграции, API) | Persistence через localStorage — backend бесплатен. |
| Влияние collapse на экспорт PDF/PPTX/XLSX | Решено в брейнсторме: экспорт всегда полный, collapse — чисто UX для просмотра в браузере. Селективный экспорт сделает отдельный пункт #27 (PDF чекбоксы выбора секций). |
| Свернутый-по-умолчанию режим | Решено: default = развёрнуто (current behaviour). |
| Server-side preferences (user-wide settings) | YAGNI: localStorage достаточно. Если в Фазе D появится user preferences UI — мигрируется через одноразовый импорт. |
| Изменение существующих локальных раскрытий (`financial-plan-editor` collapse CAPEX/OPEX, value-chain expandable rows, sensitivity-tab row details) | Это row-level раскрытия, ортогональны section-level из #22. Не трогаем. |
| Анимация плавнее, чем дефолт `@base-ui/react` Collapsible | Используем дефолтную height-transition primitive'а. |

---

## §3. Архитектурный обзор

Три новых файла + правки в 5 существующих:

```
frontend/
├── components/ui/
│   └── collapsible.tsx                    NEW  ~50 строк
├── lib/
│   ├── use-collapse-state.ts              NEW  ~60 строк
│   └── analysis-sections.ts               NEW  ~25 строк
└── components/projects/
    ├── results-tab.tsx                    EDIT wrap 10 секций
    ├── sensitivity-tab.tsx                EDIT wrap 4 секции
    ├── pricing-tab.tsx                    EDIT wrap 3 секции
    ├── value-chain-tab.tsx                EDIT wrap 1 секцию
    └── pnl-tab.tsx                        EDIT wrap 1 секцию
```

**Поток данных:**

```
┌──────────────────────────────────────────────┐
│ results-tab.tsx (или другой analysis-таб)    │
│                                              │
│ const collapse = useCollapseState(           │
│   projectId, "results", RESULTS_SECTIONS,    │
│ );                                           │
│                                              │
│ <BulkToggleButton                            │
│   allOpen={collapse.allOpen}                 │
│   onClick={() => collapse.allOpen           │
│     ? collapse.collapseAll()                 │
│     : collapse.expandAll()                   │
│   }                                          │
│ />                                           │
│                                              │
│ <CollapsibleSection                          │
│   sectionId="npv"                            │
│   title="NPV"                                │
│   isOpen={collapse.isOpen("npv")}            │
│   onToggle={() => collapse.toggle("npv")}    │
│ >                                            │
│   ...три KPI карточки NPV...                 │
│ </CollapsibleSection>                        │
└──────────────────────────────────────────────┘
              │ внутри хука
              ▼
┌──────────────────────────────────────────────┐
│ localStorage["db2:analysis-collapse:v1"]      │
│ { schema_version: 1, by_project: { ... } }   │
└──────────────────────────────────────────────┘
```

---

## §4. Карта секций по табам

Section ID = стабильный kebab-case slug; не меняется без миграции схемы localStorage (см. §7.3). Заголовки уточнены по фактическому коду на 2026-05-16.

### §4.1 Results (`results-tab.tsx`) — 10 секций

| sectionId | title (current) | location |
|---|---|---|
| `go-no-go` | «Go/No-Go решение (Y1-Y10)» | line 452 |
| `ai-explain` | (AI Explain KPI inline) | line 471, рендерится условно |
| `ai-exec-summary` | (AI Executive Summary) | line 482 |
| `npv` | «NPV (чистая приведённая стоимость)» | line 492 |
| `irr` | «IRR (внутренняя норма доходности)» | line 518 |
| `roi` | «ROI (возврат на инвестиции)» | line 537 |
| `payback` | «Payback (срок окупаемости, Y1-Y10)» | line 556 |
| `margins` | «Маржинальность (overall)» | line 577 |
| `per-unit` | «Per-unit экономика (средняя за период)» | line 597 |
| `color-legend` | «Цветовая индикация» | line 656 |

«Staleness badge» (line 445) **НЕ оборачиваем** — это inline-уведомление, не «секция».

### §4.2 Sensitivity (`sensitivity-tab.tsx`) — 4 секции

| sectionId | title |
|---|---|
| `base-values` | «Базовые значения» (line 191) |
| `ai-interpretation` | (`<ExplainSensitivityInline>`, line 224) |
| `tornado` | (`<TornadoChart>`, line 233) — title из компонента |
| `matrix` | «Матрица 5 × 4 (NPV / CM%)» (line 239) |

`<TornadoChart>` — это самостоятельный компонент-Card; оборачиваем как есть.

### §4.3 Pricing (`pricing-tab.tsx`) — 3 секции

| sectionId | title |
|---|---|
| `shelf-price` | «Цена полки (₽/шт)» (line 101) |
| `ex-factory` | «Цена отгрузки / Ex-Factory (₽/шт)» (line 143) |
| `costs-margins` | «Себестоимость и маржи» (line 184) |

### §4.4 Value-chain (`value-chain-tab.tsx`) — 1 секция

| sectionId | title |
|---|---|
| `unit-economy` | «Unit-экономика (₽/шт)» (line 183) |

### §4.5 P&L (`pnl-tab.tsx`) — 1 секция

| sectionId | title |
|---|---|
| `pnl` | «P&L — {modeLabel}» (line 218) |

---

## §5. Контракт `<CollapsibleSection>`

```tsx
// frontend/components/ui/collapsible.tsx

import { Collapsible as BaseCollapsible } from "@base-ui/react";
import { ChevronDown } from "lucide-react";
import type { ReactNode } from "react";

export interface CollapsibleSectionProps {
  /** Стабильный ID для localStorage. Не менять без миграции схемы. */
  sectionId: string;
  /** Заголовок (string | ReactNode). Рисуется внутри clickable button. */
  title: ReactNode;
  /** Controlled: true = раскрыта. */
  isOpen: boolean;
  /** Вызывается на клик по заголовку / на keyboard activate. */
  onToggle: () => void;
  /** Контент секции. */
  children: ReactNode;
  /** Дополнительные классы на wrapper-div. */
  className?: string;
}

export function CollapsibleSection(props: CollapsibleSectionProps): JSX.Element;
```

### §5.1 Поведение

- **Триггер**: header-button (полная ширина), keyboard Enter/Space toggle через base-ui.
- **Chevron**: lucide `ChevronDown`, поворот через `rotate-180` при `isOpen={false}`.
- **Анимация**: дефолтная height-transition base-ui Collapsible (~150ms).
- **A11y**: `aria-expanded`, `aria-controls` — base-ui делает сам.

### §5.2 Стили (Tailwind)

- Wrapper: `<div className="space-y-2 ...rest">` (наследует `space-y-6` из parent).
- Header button: `flex w-full items-center justify-between text-sm font-semibold text-muted-foreground hover:text-foreground transition-colors`.
- Content: `pt-2 space-y-4` (отступ от header).

Дизайн интегрируется в существующий `space-y-6` вёрстку табов; визуально header похож на текущие `<h3>` (uppercase tracking-wide).

### §5.3 Что НЕ принимает компонент

- `defaultOpen` — не поддерживается, всегда controlled (иначе bulk toggle не работает консистентно).
- Не оборачивает контент в `<Card>` — секция может быть и Card, и div. Wrapper — нейтральный.

---

## §6. Контракт `useCollapseState`

```tsx
// frontend/lib/use-collapse-state.ts

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
  /** Все ID из sectionIds → закрыты. */
  collapseAll: () => void;
  /** Удаляет все записи для (projectId, tabKey) → всё default open. */
  expandAll: () => void;
  /** true если все sectionIds открыты (для лейбла bulk-кнопки). */
  allOpen: boolean;
}

export function useCollapseState(
  projectId: number,
  tabKey: AnalysisTabKey,
  sectionIds: readonly string[],
): CollapseStateApi;
```

### §6.1 Поведение

- **Init**: на mount читает `localStorage["db2:analysis-collapse:v1"]`, парсит JSON, fallback на пустой объект на любой ошибке (invalid JSON / SecurityError в iframe).
- **State**: React `useState<Record<string, boolean>>` (только для текущего проекта × таба).
- **Persist**: на каждое изменение пишет в localStorage через debounced effect (или прямо в callbacks; debounce overkill для редких кликов).
- **Schema version mismatch**: если в LS `schema_version !== 1` — игнорируем содержимое, возвращаем дефолт. Никаких эксепшнов наружу.
- **Storage failures** (quota exceeded, disabled): тихо `console.warn`, продолжаем работу с in-memory state.

### §6.2 `expandAll()` поведение

Удаляет запись `by_project[projectId][tabKey]` (а не записывает `{ id: true, ... }`). Так состояние «всё открыто» = «нет записи» — minimal LS footprint.

---

## §7. Схема localStorage

### §7.1 Ключ и формат

```
key:    db2:analysis-collapse:v1
value:  JSON

interface CollapseStorage {
  schema_version: 1;
  by_project: {
    [projectId: string]: {           // projectId — String(number)
      [tabKey: string]: {            // AnalysisTabKey
        [sectionId: string]: false;  // false = свёрнуто; отсутствие = развёрнуто
      };
    };
  };
}
```

Пример:
```json
{
  "schema_version": 1,
  "by_project": {
    "42": {
      "results": { "ai-explain": false, "color-legend": false },
      "sensitivity": { "tornado": false }
    },
    "17": {
      "pricing": { "ex-factory": false }
    }
  }
}
```

### §7.2 Почему только `false` (свёрнуто)?

- Default = открыто. Хранить `{ id: true }` для всех открытых ID — расход места и шум.
- «Свёрнуть всё» → пишем все `id: false`. «Развернуть всё» → удаляем `by_project[projectId][tabKey]`.

### §7.3 Версионирование

- `:v1` суффикс ключа + `schema_version: 1` внутри. Если в будущем поменяется схема (например, добавим row-level collapse) — bump до `v2`, добавим `schema_version: 2`. Старые `v1` ключи игнорируем, не мигрируем (LS не source of truth, потеря пользовательских предпочтений — не катастрофа).

### §7.4 Граница объёма

Худший case: 100 проектов × 5 табов × 10 секций × ~30 байт на запись ≈ 150KB. localStorage quota ≥ 5MB во всех современных браузерах → запас 33×.

---

## §8. Bulk toggle UX

### §8.1 Размещение

- **Results**: добавить кнопку в существующий header-row (line 314 «flex flex-wrap items-end justify-between»), слева от «Скачать XLSX». Группа кнопок: `[Свернуть/Развернуть всё] [XLSX] [PPTX] [PDF] [Пересчитать]`.
- **Sensitivity / Pricing**: в существующих контролах сверху таба (если их нет — добавить лёгкую панель `<div className="flex justify-end">`).
- **Value-chain / P&L**: 1 секция → bulk toggle **не рисуем** (бессмысленно).

### §8.2 Лейбл и иконка

- Лейбл: `«Свернуть всё»` если `allOpen === true`, иначе `«Развернуть всё»`.
- Иконка (lucide): `<ChevronsDownUp>` для collapse, `<ChevronsUpDown>` для expand.
- Variant: `Button` `variant="ghost"` или `"outline"` (consistent с export-кнопками).

### §8.3 Pseudo-code

```tsx
{collapse.allOpen ? (
  <Button variant="ghost" size="sm" onClick={collapse.collapseAll}>
    <ChevronsDownUp className="mr-2 h-4 w-4" />
    Свернуть всё
  </Button>
) : (
  <Button variant="ghost" size="sm" onClick={collapse.expandAll}>
    <ChevronsUpDown className="mr-2 h-4 w-4" />
    Развернуть всё
  </Button>
)}
```

---

## §9. Взаимодействие с существующими локальными раскрытиями

| Файл | Существующее раскрытие | Конфликт? | Действие |
|---|---|---|---|
| `financial-plan-editor.tsx` (B.9b) | CAPEX/OPEX collapse (`collapsed.capex`, `collapsed.opex`) | Нет — это в табе ① «Фин. план», вне Анализ. | Не трогаем. |
| `value-chain-tab.tsx` | Раскрытие строк таблицы (?) | Возможно row-level. | Не трогаем; section-level collapse работает поверх. |
| `sensitivity-tab.tsx` | Раскрытие row-деталей (?) | Возможно row-level. | Не трогаем. |
| `channels-panel.tsx` | Локальные expansions per channel | Не в Анализ. | Не трогаем. |

Принцип: row-level / item-level expansions — ортогональны section-level из #22. Никаких миграций существующих collapse-state'ов в новый механизм.

---

## §10. Тестирование

В `frontend/` нет unit-test runner-а (jest/vitest); единственный тест — `frontend/e2e/smoke.spec.ts`. Стратегия:

### §10.1 Статика

- `npx tsc --noEmit` — 0 ошибок. **Обязательно** перед коммитом (см. memory `feedback-frontend-checklist`).

### §10.2 Manual smoke

На каждом из 5 табов:
1. Открыть таб — все секции раскрыты (если LS пуст).
2. Кликнуть chevron на секции → анимация → секция свёрнута → chevron повёрнут.
3. F5 → секция остаётся свёрнутой.
4. Открыть другой проект с тем же id → state независим.
5. Где есть bulk toggle: кликнуть «Свернуть всё» → все секции свёрнуты, лейбл сменился. Кликнуть «Развернуть всё» → все раскрыты.

### §10.3 Регрессии

- e2e `smoke.spec.ts` — должен пройти без правок (проверяет базовую навигацию).
- Существующие локальные expansions (CAPEX/OPEX, row details) — продолжают работать.
- Экспорт PDF/PPTX/XLSX — генерит файлы с полным набором секций (collapse-state игнорируется).

### §10.4 Acceptance criteria

- Все 5 табов имеют section-level collapse с chevron.
- LocalStorage persistence работает через F5 для (projectId, tabKey, sectionId).
- Bulk toggle на Results/Sensitivity/Pricing (3 таба с >1 секциями).
- `tsc --noEmit` 0 ошибок.
- Manual smoke по чеклисту §10.2 пройден на всех 5 табах.

---

## §11. Edge cases

| Случай | Поведение |
|---|---|
| `AI Explain` секция в Results рендерится только при `selectedScenarioId !== null` | State в LS персистится независимо. При первом появлении секции применяется сохранённый state. |
| LocalStorage отключен (Private mode, browser policy) | `console.warn` один раз, state работает только в памяти текущей сессии. UI не падает. |
| Quota exceeded | `console.warn`, дальнейшие записи silently fail. UI работает на текущей сессии. |
| Старая запись из `:v0` (если когда-то добавим) | Игнорируется; default. |
| Section ID добавили в код, но в LS его нет | `isOpen()` возвращает `true` (default). |
| Section ID удалили из кода, в LS осталось | Запись «висит», места занимает чуть-чуть, не мешает. (Можно почистить при следующем bump schema_version.) |
| User переключается между табами в рамках одного проекта | Каждый таб = свой инстанс хука, читает/пишет одну и ту же запись в LS, но React-state свой → no cross-tab синхронизации (она и не нужна, переход = re-mount). |

---

## §12. Non-goals / Future

- **Server-side persistence**: при появлении user preferences UI (Фаза D?) можно мигрировать localStorage → user_preferences.collapse_state JSONB.
- **Sync между табами браузера**: localStorage `storage` event — не реализуем (overhead > value).
- **Анимация плавнее**: дефолт base-ui достаточен.
- **Collapse в input-табах** (BOM, channels): следующая итерация если запросят. Из текущего scope — out.

---

## §13. File map (для writing-plans)

| Файл | Тип | Краткое описание |
|---|---|---|
| `frontend/components/ui/collapsible.tsx` | NEW | `<CollapsibleSection>` обёртка над base-ui Collapsible. |
| `frontend/lib/use-collapse-state.ts` | NEW | Хук `useCollapseState(projectId, tabKey, sectionIds)` с localStorage I/O. |
| `frontend/lib/analysis-sections.ts` | NEW | Константные массивы `RESULTS_SECTIONS`, `SENSITIVITY_SECTIONS`, `PRICING_SECTIONS`, `VALUE_CHAIN_SECTIONS`, `PNL_SECTIONS`. |
| `frontend/components/projects/results-tab.tsx` | EDIT | Обернуть 10 секций (см. §4.1), добавить bulk toggle в header-row. |
| `frontend/components/projects/sensitivity-tab.tsx` | EDIT | Обернуть 4 секции, добавить bulk toggle. |
| `frontend/components/projects/pricing-tab.tsx` | EDIT | Обернуть 3 секции, добавить bulk toggle. |
| `frontend/components/projects/value-chain-tab.tsx` | EDIT | Обернуть 1 секцию, без bulk toggle. |
| `frontend/components/projects/pnl-tab.tsx` | EDIT | Обернуть 1 секцию, без bulk toggle. |
| `docs/CLIENT_FEEDBACK_v2_STATUS.md` | EDIT | Строка 38 (BL-#22) ❌ → ✅. |
| `CHANGELOG.md` | EDIT | `## Phase C` → `### Added` или `### Changed` — добавить запись. |

---

## §14. Branch / commit hygiene

- **Branch**: `feat/c22-analysis-collapsible` (от `main`).
- **Коммиты** ожидаемо ~4-5 атомарных:
  1. `feat(c22): add CollapsibleSection wrapper + useCollapseState hook`
  2. `feat(c22): wrap results-tab sections in CollapsibleSection`
  3. `feat(c22): wrap sensitivity/pricing/value-chain/pnl sections`
  4. `docs(c22): close MEMO 1.3 — collapse/expand разделов отчёта`
- **Merge**: fast-forward на `main` (по аналогии с C #13).
