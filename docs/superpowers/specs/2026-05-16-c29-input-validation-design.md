# C #29 — Валидация вводных (minimum protection)

**Дата:** 2026-05-16
**Эпик:** C #29 (Phase C completion run)
**Источник:** `docs/CLIENT_FEEDBACK_v2.md` строки 250–256 (MEMO заказчика от 23.04.2026, пункт 29)
**Связанная память:** [[project-phase-c-completion-run]], [[feedback-brainstorm-no-micro-questions]]

---

## 1. Цель

Добавить inline-предупреждения (не блокирующие save) для критических числовых полей, где значение `0` проходит Pydantic-валидацию `ge=0`, но даёт некорректный downstream-расчёт. Это закрывает обещание Claude в CLIENT_FEEDBACK_v2.md (минимальная защита: «отрицательное = ошибка, нулевое = предупреждение»).

Отрицательные значения уже блокируются Pydantic (`ge=0` везде) и `useFieldValidation` (`min: 0`) — здесь ничего не меняется. Эпик добавляет **новую концепцию warnings** в `useFieldValidation`.

## 2. Scope

### Поля в scope (4 поля × 3 формы)

| Поле | Форма (файл) | Текущая защита | Новое поведение |
|------|--------------|----------------|-----------------|
| `shelf_price_reg` | `channel-form.tsx` | `min=0` (Pydantic `ge=0`) | warning при `=0` |
| `offtake_target` | `channel-form.tsx` | `min=0` | warning при `=0` |
| `price_per_unit` (BOM) | `bom-panel.tsx` | `min=0` | warning при `=0` |
| `volume_l` (SKU) | `add-sku-dialog.tsx` | `min=0` | warning при `=0` |

### Тексты warning-сообщений

- `shelf_price_reg = 0` → «Цена полки 0 ₽ — выручка обнулится»
- `offtake_target = 0` → «Целевой offtake 0 — продаж не будет»
- `price_per_unit = 0` (BOM) → «Цена сырья 0 — компонент не попадёт в COGS»
- `volume_l = 0` (SKU) → «Объём 0 — расчёты per-unit некорректны»

### Out of scope (документировать как известное, отложенное)

- **Upper bound `copacking_rate`** (ДЫРА #4 в inventory): сейчас `Field(default=0, ge=0)` без `le=`, теоретически допускает значение `>1`, что даёт отрицательный COGS. Требует бизнес-решения (ставка как доля или абсолютная). Открыть отдельный эпик после уточнения у заказчика.
- **Per-period warnings в Fine-Tuning / FinancialPlan** (43 ячейки per канал): сложный UX (warning per cell в `period-grid`), вне minimum scope.
- **Backend warnings API**: Pydantic не возвращает warnings (только 422 errors). Реализация потребовала бы отдельного response wrapper — overengineering для текущего scope. Warnings остаются frontend-only.
- **Bulk-импорт Excel**: warnings в `excel_import` flow не показываются (отдельный сценарий, не диалог).
- **ChannelDeltasEditor / Scenario dialogs**: дельты `-1..+1` корректны как 0 (нулевая дельта = нет изменения), warning не нужен.

## 3. Архитектура

### 3.1 Расширение `useFieldValidation` hook

**Файл:** `frontend/lib/use-field-validation.ts`

```ts
export interface FieldRule {
  required?: boolean;
  min?: number;
  max?: number;
  numeric?: boolean;
  message?: string;
  /** Optional warning: triggers if predicate matches AND no error present. */
  warn?: {
    when: (n: number) => boolean;
    message: string;
  };
}

export type FieldWarnings<T extends string = string> = Partial<Record<T, string>>;
```

**Изменения:**

1. `validateField(value, rule)` возвращает `{ error?: string; warning?: string }` вместо `string | null`.
   - Error preserved as before (required, numeric parse, min/max).
   - Если error отсутствует и `rule.warn.when(num)` истинно → возвращает `warning: rule.warn.message`.
2. `useFieldValidation` отдаёт **новое** `warnings: FieldWarnings<T>` параллельно `errors`.
3. `validateOne(field, value)` обновляет и `errors[field]`, и `warnings[field]`.
4. `validateAll(values)` обновляет оба state-объекта; **возвращает `true`/`false` только по errors** — warnings не блокируют submit.
5. `clearError(field)` — очищает только error (warning остаётся, чтобы пользователь видел жёлтое сообщение пока поле не обновили).
6. `clearAll()` — очищает оба.
7. `hasErrors` — оставить как было (только по errors).

**Обоснование** (выбора расширить hook vs. создать параллельный `useFieldWarnings`):
- Все поля с warnings уже имеют rules в существующем hook — добавление параллельного hook удвоило бы количество wiring per field.
- Save policy остаётся в одном месте (`validateAll` принимает решение по errors, warnings игнорируются для submit).
- Backwards compatible: формы, не использующие `warn`, продолжают работать без изменений.

### 3.2 Новый компонент `FieldWarning`

**Файл:** `frontend/components/ui/field-warning.tsx`

```tsx
import { AlertTriangle } from "lucide-react";

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

**Обоснование:**
- Симметричный API с `FieldError` (`error` prop → `warning` prop).
- Цвет `text-amber-600` — стандартный warning tone (отличается от `text-destructive` = red).
- Иконка `AlertTriangle` из `lucide-react` (уже установлен).
- `role="status"` (не `alert`) — assistive tech не прерывает пользователя (warning ≠ blocking).

### 3.3 Per-form интеграция

Для каждого поля в scope:

1. В rules-объекте формы добавить `warn`:
   ```ts
   shelf_price_reg: {
     required: true, numeric: true, min: 0,
     warn: { when: (n) => n === 0, message: "Цена полки 0 ₽ — выручка обнулится" },
   },
   ```
2. В JSX рядом с `<FieldError error={errors.x} />` добавить `<FieldWarning warning={warnings.x} />`.
3. Деструктуризация hook: `const { errors, warnings, validateOne, validateAll, clearError } = useFieldValidation(...)`.

## 4. Backend

**НЕ трогаем.** Pydantic schemas остаются с `ge=0` (отрицательные → 422). Warnings — чисто фронтовый UX. Бэкенд получает валидное значение `0`, продолжает работу как раньше (расчёт даст 0, что соответствует существующему поведению).

## 5. Файлы (~8 шт.)

| # | Файл | Изменение |
|---|------|-----------|
| 1 | `frontend/lib/use-field-validation.ts` | Расширить `FieldRule.warn`, `validateField()`, hook отдаёт `warnings` |
| 2 | `frontend/components/ui/field-warning.tsx` | Новый компонент (amber, AlertTriangle) |
| 3 | `frontend/components/projects/channel-form.tsx` | Добавить `warn` в rules для 2 полей + render `FieldWarning` |
| 4 | `frontend/components/projects/bom-panel.tsx` | Добавить `warn` в `BOM_RULES` для `price_per_unit` + render |
| 5 | `frontend/components/projects/add-sku-dialog.tsx` | Добавить warn для `volume_l` + render |
| 6 | `frontend/e2e/c29-input-validation.spec.ts` | Playwright e2e — 4 positive + 1 negative scenarios |
| 7 | `CHANGELOG.md` | Секция [Unreleased] → C #29 |
| 8 | `docs/CLIENT_FEEDBACK_v2_STATUS.md` | Поменять статус «Валидация вводных» с ❌ на ✅ (minimum protection) |

## 6. Testing

**Фронт-инфра DB2 не содержит vitest/jest** — тесты в `frontend/e2e/*.spec.ts` через Playwright (требует Docker stack). Из-за этого «полноценные unit-тесты» для hook'а заменяются комбинацией: TypeScript types (compile-time), Playwright e2e (integration), manual browser verify (controller).

### 6.1 Compile-time (`npx tsc --noEmit`)

Новый shape `validateField()` (`{ error?: string; warning?: string }`) и новое поле `warnings` в hook return-объекте должны компилироваться без ошибок. Каждая form-интеграция деструктурирует `warnings` — несоответствие даст compile error.

### 6.2 Playwright e2e (новый файл `frontend/e2e/c29-input-validation.spec.ts`)

Каждый из 4 кейсов = отдельный test():

- **ChannelForm shelf_price_reg=0:** открыть проект → вкладка Каналы → добавить канал → ввести 0 в "Цена полки" → blur → проверить наличие текста "Цена полки 0 ₽ — выручка обнулится" → submit → форма закрылась (без блока).
- **ChannelForm offtake_target=0:** аналогично, "Целевой offtake 0 — продаж не будет".
- **BOMPanel price_per_unit=0:** проект → SKU и BOM → выбрать SKU → добавить компонент → 0 в "Цена за единицу" → blur → warning виден → submit → проходит.
- **AddSkuDialog volume_l=0:** проект → SKU и BOM → "Добавить SKU" → 0 в "Объём" → blur → warning виден → submit → SKU создан.

Дополнительно один negative-кейс: ввести `-1` в `shelf_price_reg` → видно red-error, submit заблокирован (нет навигации/закрытия диалога).

### 6.3 Manual в браузере

После Playwright passes, controller проходит 4 кейса вручную и подтверждает читаемость текста (amber-цвет различим, иконка не съезжает).

## 7. Риски и ограничения

- **Не охватывает все «странные» вводы:** warning только на ровно `0`. Очень маленькие положительные значения (`0.0001`) проходят без warning. Это сознательное упрощение — minimum scope, не подменяет настоящую бизнес-валидацию.
- **Warnings не персистятся:** перезагрузил страницу → warning исчезает до следующего blur. Это ОК для minimum scope (warnings — UX-нюдж в момент ввода).
- **Per-period editors** (Fine-Tuning, FinancialPlan, ChannelDeltasEditor) **не модифицируются** — там 43 ячейки per канал/SKU, warning-механизм потребует другого UX (например, агрегированный badge на секции). Отложено.

## 8. Acceptance criteria

- [ ] `useFieldValidation` отдаёт `warnings: FieldWarnings<T>` рядом с `errors`
- [ ] `FieldWarning` компонент создан и используется в 3 формах
- [ ] 4 поля показывают amber-warning при значении `0`
- [ ] Submit формы с warning-only state не блокируется
- [ ] Submit с error продолжает блокироваться
- [ ] Playwright e2e `c29-input-validation.spec.ts` — 5 кейсов (4 positive + 1 negative) проходят
- [ ] `frontend tsc --noEmit` — 0 ошибок
- [ ] `CHANGELOG.md` + `docs/CLIENT_FEEDBACK_v2_STATUS.md` обновлены
- [ ] Manual smoke: 4 кейса в браузере подтверждены controller
