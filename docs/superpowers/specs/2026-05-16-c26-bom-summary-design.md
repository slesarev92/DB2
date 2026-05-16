# C #26 — BOM сводка справа

**Дата:** 2026-05-16
**Эпик:** C #26 (Phase C completion run)
**Источник:** MEMO заказчика, пункт «BOM сводка справа (Сырьё/Материалы/Прочее/Итого)»; `docs/CLIENT_FEEDBACK_v2_STATUS.md` пункт 22.
**Связанная память:** [[project-phase-c-completion-run]], [[feedback-brainstorm-no-micro-questions]]

---

## 1. Цель

Сейчас агрегация BOM по категориям ингредиентов рендерится компактно в `CardHeader` BOM-таблицы (`bom-panel.tsx:605-616`) — мелкие строки в правом верхнем углу, легко пропустить. Заказчик просит более заметный отдельный блок «справа от таблицы» с разбивкой по 3 категориям и итогом.

Эпик переносит агрегацию в отдельный sidebar-компонент `BomSummarySidebar`, видимый на одном уровне с таблицей, и удаляет inline-блок из CardHeader (один источник истины, без дублирования).

## 2. Scope

### 2.1 Layout

`BomPanel` (`frontend/components/projects/bom-panel.tsx`) — это `Card` с таблицей + add-form + COGS preview header. Сейчас оформление вертикальное. После эпика — горизонтальная сетка с sidebar справа на десктопе и складывающаяся под таблицу на узких экранах.

Используем Tailwind grid:
- Контейнер таблицы: `grid grid-cols-1 md:grid-cols-3 gap-4`
- Таблица + add-form: `md:col-span-2`
- Sidebar: `md:col-span-1`

`md` breakpoint = 768px. Ниже — sidebar под таблицу (mobile-стиль), хотя проект desktop-focused и это редкий кейс. Допустимо.

### 2.2 Новый компонент

**Файл:** `frontend/components/projects/bom-summary-sidebar.tsx`

**Props:**
```ts
interface BomSummarySidebarProps {
  items: BOMItemRead[];
}
```

**Содержимое (renders Card or section):**
- Заголовок «Сводка BOM» (`<CardTitle>` или `<h3>`)
- Empty state если `items.length === 0`: «Добавьте позиции BOM для расчёта»
- Иначе три category-строки в фиксированном порядке:
  1. Сырьё (raw_material)
  2. Упаковка (packaging)
  3. Прочее (other)
  Каждая строка содержит:
  - Label («Сырьё», «Упаковка», «Прочее»)
  - Сумма ₽ (через `formatMoney`)
  - Кол-во позиций
  - % от итога (`(catSum / total) × 100`, округление до 1 знака)
  Если категория пустая (0 позиций) — строка показывается с серым «—» вместо суммы/процента (фиксированный шаблон, чтобы layout не «прыгал»).
- Разделитель (`<Separator />` shadcn или `border-t`)
- Итоговая строка «Итого»: общая сумма + общее кол-во позиций

**Расчёт:**
- Сумма категории = `Σ qty × price × (1 + loss)` per items в этой категории. Та же формула что `computeCogsPreview`.
- Категория позиции = `item.ingredient_category ?? "other"` (если ингредиент привязан через `ingredient_id`, поле приходит из backend join; иначе fallback на other).
- `useMemo` внутри компонента, dep — `items`.

### 2.3 Терминология

`CATEGORY_LABELS_BOM = { raw_material: "Сырьё", packaging: "Упаковка", other: "Прочее" }` — **оставляем как есть**, не меняем на «Материалы».

**Обоснование:** `packaging` явно про упаковку (FK `Ingredient.category` со строгим CHECK CONSTRAINT). «Упаковка» — точная семантика и устоявшаяся метка в проекте. «Материалы» в MEMO заказчика — обобщённое слово, не противоречит «Упаковке». Если заказчик в ревью попросит — переименуем в одном месте (`CATEGORY_LABELS_BOM` в `bom-panel.tsx:409-413`).

### 2.4 Что удаляем

Inline-блок категорийных сумм в `CardHeader` (`bom-panel.tsx:605-616`) удаляется. В CardHeader остаётся только общий `cogsPreview` (заголовок + сумма). Категории — только в sidebar.

`categorySums` useMemo (`bom-panel.tsx:182-194`) удаляется — вычисление переезжает в `BomSummarySidebar` (изолированный компонент).

`CATEGORY_LABELS_BOM` константа переезжает из `bom-panel.tsx:409-413` в `bom-summary-sidebar.tsx` (только sidebar теперь её использует). В bom-panel остаётся только если используется ещё где-то — проверить grep.

### 2.5 Что не меняем

- `BOMItem` модель и миграции — `Ingredient.category` уже существует, `BOMItemRead.ingredient_category` уже attach'ится в fetch.
- `cost_level` (max/normal/optimal) — не группируем, сводка по категориям только.
- API endpoints — backend не трогается вообще.
- Add-form, table, COGS preview логика — остаются как есть.

## 3. Out of scope

- **Expandable tree** позиций внутри категории — пользователь видит позиции в основной таблице, дублировать нет смысла (YAGNI).
- **Сводка per cost_level** (max/normal/optimal) — не запрашивалась, отдельная фича.
- **Сравнение между cost_level** — не запрашивалось.
- **Drag-to-reorder** в sidebar — не нужно.
- **Sticky sidebar** при скролле — желательно бы, но Tailwind `sticky top-N` потребует точной настройки относительно AppBar; откладываем до отдельного UX-эпика. По умолчанию sidebar скроллится с страницей.
- **Custom иконки** на категории — текстовые labels достаточны для minimum scope.

## 4. Файлы

| # | Файл | Изменение |
|---|------|-----------|
| 1 | `frontend/components/projects/bom-summary-sidebar.tsx` | Новый компонент (~80 строк) |
| 2 | `frontend/components/projects/bom-panel.tsx` | Layout `grid-cols-1 md:grid-cols-3`, удалить inline `categorySums` в CardHeader (lines ~605-616) и его useMemo (~182-194), удалить `CATEGORY_LABELS_BOM` (~409-413), вставить `<BomSummarySidebar items={bom} />` |
| 3 | `frontend/e2e/c26-bom-summary.spec.ts` | Playwright: empty state + 1 категория с позициями. Test может быть `test.skip` если seed-зависимо (по аналогии с C #29) |
| 4 | `CHANGELOG.md` | Секция `[Unreleased]` → C #26 (перед C #29) |
| 5 | `docs/CLIENT_FEEDBACK_v2_STATUS.md` | Пункт 22 «BOM сводка справа» ❌ → ✅; в таблице 3.4 (если есть) тоже обновить |

## 5. Testing

### 5.1 Compile-time (`npx tsc --noEmit`)

Новый компонент типизируется без ошибок. Тип `BOMItemRead` из `frontend/types/api.ts:334-346`.

### 5.2 Playwright e2e (`frontend/e2e/c26-bom-summary.spec.ts`)

- **Test 1:** Открыть проект без BOM → видно sidebar с empty state «Добавьте позиции BOM для расчёта».
- **Test 2 (test.skip с TODO seed-data):** проект с BOM из 3 категорий → видны 3 строки + Итого с правильной суммой.

Test 1 runnable без seed (новый проект автоматически создаётся в smoke flow). Test 2 — TODO.

### 5.3 Manual в браузере

После реализации controller проверяет:
- BOM с одной позицией категории «Сырьё» → sidebar показывает «Сырьё: X ₽ (1 позиция, 100%)», «Упаковка: — (0 позиций)», «Прочее: — (0 позиций)», «Итого: X ₽ (1 позиция)»
- BOM из позиций трёх категорий → правильные суммы и проценты в сумме дают 100% ± 0.1% (округление)
- Пустой BOM → empty state
- Очень узкий экран (`< md`) → sidebar складывается под таблицу

## 6. Acceptance criteria

- [ ] Компонент `BomSummarySidebar` создан, типизирован
- [ ] `BomPanel` использует grid-layout, sidebar виден справа от таблицы (md+)
- [ ] Inline-блок категорийных сумм в CardHeader удалён
- [ ] Дубликаты constant (`CATEGORY_LABELS_BOM`) и `categorySums` useMemo не остались в `bom-panel.tsx`
- [ ] Empty state работает (`items.length === 0`)
- [ ] Итог корректно агрегирует все 3 категории
- [ ] % от итога округляется до 1 знака, сумма ± 0.1% даёт 100%
- [ ] `frontend tsc --noEmit` — 0 новых ошибок
- [ ] Playwright e2e `c26-bom-summary.spec.ts` — test 1 проходит, test 2 skip с TODO
- [ ] CHANGELOG.md + CLIENT_FEEDBACK_v2_STATUS.md обновлены

## 7. Открытые вопросы / решения

- **Терминология** «Упаковка» оставлена осознанно (см. §2.3). Если заказчик в ревью попросит «Материалы» — fix в одном месте.
- **Sticky sidebar** отложен до отдельного UX-эпика (§3).
- **Иконки категорий** не используются — текста достаточно.
