# C #25 — Дублирование ввода SKU между табами устранить

**Дата:** 2026-05-16
**Эпик:** C #25 (Phase C completion run)
**Источник:** `docs/CLIENT_FEEDBACK_v2.md` §4.4, `docs/CLIENT_FEEDBACK_v2_STATUS.md` пункт 20.
**Связанная память:** [[project-phase-c-completion-run]], [[feedback-brainstorm-no-micro-questions]]

---

## 1. Цель и диагностика

**MEMO заказчика (4.4):** «SKU создаётся в "SKU и BOM", а в "Каналах" должен только **привязываться** к каналу. Два независимых места создания SKU недопустимы — риск рассинхронизации».

**Реальное состояние (diagnose):**

Структурного дублирования нет. `AddSkuDialog` (`frontend/components/projects/add-sku-dialog.tsx`) — единственный компонент создания SKU, используется через общий `SkuPanel` в обеих вкладках («SKU и BOM», «Каналы»). Backend защищён `ProjectSKU.sku_id` с `ondelete="RESTRICT"` — orphan невозможен.

**UX-проблема:** `AddSkuDialog` имеет два режима (`mode: "existing" | "new"`, по умолчанию `"existing"`). Пользователь на вкладке «Каналы» нажимает `+ Добавить` в SkuPanel — открывается тот же диалог, переключается в режим «Создать новый» и **создаёт новый SKU прямо из вкладки Каналы**. Это противоречит MEMO 4.4 — Каналы должны только **привязывать существующие** SKU.

## 2. Scope

Запретить режим «создать новый SKU» в `AddSkuDialog` когда он открыт из вкладки «Каналы». На вкладке «SKU и BOM» оба режима остаются доступными.

### 2.1 Изменение `AddSkuDialog`

Новый prop:
```ts
interface AddSkuDialogProps {
  // ... existing props
  /**
   * Если true — режим «создать новый SKU» скрыт. Диалог работает
   * только в `mode="existing"` (выбор из каталога). Используется на
   * вкладке «Каналы» где SKU должны только привязываться (MEMO 4.4).
   */
  existingOnly?: boolean;
}
```

Логика:
- `useState<Mode>("existing")` — default unchanged.
- При `existingOnly === true`:
  - Сегмент-tab/радио переключения mode НЕ рендерится (или disabled).
  - `setMode("new")` ниоткуда не вызывается (защита от программного переключения).
- При `existingOnly !== true` (default false) — текущее поведение сохраняется.

Заголовок диалога при `existingOnly`: «Привязать SKU к проекту» (вместо текущего «Добавить SKU в проект») — точнее семантика.

### 2.2 Изменение `SkuPanel`

```ts
interface SkuPanelProps {
  // ... existing
  /**
   * Передаётся в AddSkuDialog. На вкладке «Каналы» = true, на вкладке
   * «SKU и BOM» = false/undefined (по умолчанию).
   */
  existingOnly?: boolean;
}
```

В JSX: `<AddSkuDialog ... existingOnly={existingOnly} />`.

Кнопка `+ Добавить` остаётся видимой — пользователь всё ещё хочет привязать существующий SKU к проекту со вкладки Каналы (это валидный use case).

Label кнопки тоже можно адаптировать: при `existingOnly` — «+ Привязать SKU», иначе текущий «+ Добавить». **Micro-UX-улучшение**, ясная семантика.

### 2.3 Изменение `ChannelsTab` и `SkusTab`

`channels-tab.tsx`: `<SkuPanel ... existingOnly />` (true).
`skus-tab.tsx`: `<SkuPanel ... />` (без prop, default false).

## 3. Backend

**НЕ трогаем.** `ProjectSKU.sku_id` уже с `RESTRICT FK`. Эпик чисто UX/frontend.

Out of scope: добавление backend-валидации «контекст вызова» (variant 3 из diagnose) — overengineering, frontend-gate достаточен.

## 4. Что НЕ меняем

- Создание SKU через `POST /api/skus` (общий endpoint, работает в обеих вкладках через диалог).
- BOMItem каскадное удаление через ProjectSKU.
- Channels tab logic (Phase 1 чекбоксы / Phase 2 метрики из C #16).
- Никаких миграций.

## 5. Файлы (~4-5)

| # | Файл | Изменение |
|---|------|-----------|
| 1 | `frontend/components/projects/add-sku-dialog.tsx` | `existingOnly?: boolean` prop, скрыть mode toggle если true, заголовок «Привязать SKU к проекту» |
| 2 | `frontend/components/projects/sku-panel.tsx` | `existingOnly?: boolean` prop, проброс в `<AddSkuDialog>`, label кнопки `+ Привязать SKU` при true |
| 3 | `frontend/components/projects/channels-tab.tsx` | `<SkuPanel ... existingOnly />` |
| 4 | `frontend/components/projects/skus-tab.tsx` | проверить что без prop (default false), не менять если уже корректно |
| 5 | `frontend/e2e/c25-sku-no-duplication.spec.ts` | Playwright (skip с TODO seed) |
| 6 | `CHANGELOG.md` + `docs/CLIENT_FEEDBACK_v2_STATUS.md` | пункт 20 ❌ → ✅ |

## 6. Testing

### 6.1 Compile-time

`npx tsc --noEmit` — 0 новых ошибок.

### 6.2 Playwright e2e (`frontend/e2e/c25-sku-no-duplication.spec.ts`)

Skip с TODO seed (типично для C-эпиков):
- Test 1 (skip): открыть вкладку Каналы, нажать «+ Привязать SKU» в SkuPanel, проверить что mode toggle отсутствует и виден только Select из каталога.
- Test 2 (skip): открыть вкладку SKU и BOM, нажать «+ Добавить», проверить что mode toggle виден (existing + new).

### 6.3 Manual в браузере

После реализации controller:
- Открыть проект → вкладка Каналы → кнопка показывает «+ Привязать SKU» → диалог открывается с заголовком «Привязать SKU к проекту», ТОЛЬКО Select каталога, без переключения на «Создать новый».
- Открыть вкладку SKU и BOM → кнопка «+ Добавить» → диалог с обоими режимами (как сейчас).

## 7. Acceptance criteria

- [ ] `AddSkuDialog` получил prop `existingOnly?: boolean`
- [ ] При `existingOnly` mode toggle не рендерится, форма «new» недоступна
- [ ] Заголовок диалога при `existingOnly` — «Привязать SKU к проекту»
- [ ] `SkuPanel` пробрасывает `existingOnly` в диалог, label кнопки адаптирован
- [ ] `channels-tab.tsx` передаёт `existingOnly`
- [ ] `skus-tab.tsx` без prop (default режим)
- [ ] tsc clean
- [ ] Playwright spec создан (test.skip с TODO acceptable)
- [ ] CHANGELOG.md + CLIENT_FEEDBACK_v2_STATUS.md обновлены (#20)
- [ ] Manual smoke: оба flow работают корректно

## 8. Open questions / решения

- **Backend-валидация контекста**: НЕ делаем (frontend-gate достаточен per MEMO интерпретации). Если в будущем появится API-route куда можно создать SKU обходом UI — отдельный эпик.
- **Терминология «Привязать»** — выбрано вместо «Добавить» только для случая existingOnly. Семантически точнее, на ru ясно: «privyazat'» = bind.
- **Кнопка «+» visibility** при `existingOnly`: оставляем видимой — пользователь должен иметь возможность добавить ещё один SKU к проекту со вкладки Каналы.
