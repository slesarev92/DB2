# C #20 — Раскраска чувствительности с настраиваемыми порогами

**Дата:** 2026-05-16
**Эпик:** C #20 (Phase C completion run)
**Источник:** `docs/CLIENT_FEEDBACK_v2.md` §6.2; `docs/CLIENT_FEEDBACK_v2_STATUS.md` пункт 17.
**Связанная память:** [[project-phase-c-completion-run]], [[feedback-brainstorm-no-micro-questions]]

---

## 1. Цель и диагностика

**MEMO 6.2:** «Раскраска таблицы чувствительности — пояснить логику (текущая цветовая схема непонятна). Реализовать: зелёный (выше базы), красный (ниже базы), с настраиваемыми порогами».

**Текущее состояние (diagnose):**
- `sensitivity-tab.tsx:67-72` функция `npvClass()` — бинарная раскраска: `> base` зелёный, `< base` красный, `= base` нейтральный. Никаких **% порогов**.
- `tornado-chart.tsx:138-146` — bars hardcoded `#22c55e`/`#ef4444` без логики порогов (цвет зависит только от знака delta).
- Backend `sensitivity_service.py` — параметры hardcoded (`SENSITIVITY_DELTAS`, `SENSITIVITY_PARAMS`). Response shape без threshold settings.

**Проблема:** даже delta 0.0001% от base покрасит ячейку зелёным/красным, что и делает текущую раскраску «непонятной».

## 2. Scope

Добавить UI настройки **% порогов** (доли от base NPV) для раскраски таблицы чувствительности и tornado-bars. Пороги хранятся в `localStorage` (как C #27 PDF sections), не передаются в backend и не персистятся в DB.

### 2.1 Пороги (две настройки)

- **Green threshold (%)** — отклонение от base NPV ≥ +X% → зелёный.
- **Red threshold (%)** — отклонение ≥ X% **в минус** → красный.
- Между порогами — нейтральный (без подсветки или светло-серый).

**Default:** `greenPct: 5`, `redPct: 5` (симметричные 5%/5%, типичное FMCG поведение).

**Range:** 0% — 100%. Если пользователь поставит 0% — раскраска становится бинарной (как сейчас).

**Раздельные** (зелёный и красный), а не симметричные: пользователь может предпочесть жёсткую красную (5%) и мягкую зелёную (10%) или наоборот.

### 2.2 UI controls

Расположение: header вкладки «Чувствительность», рядом с scope selector (Y1-Y3 / Y1-Y5 / Y1-Y10).

Контролы — два `<Input type="number">` с лейблами «Зелёный ≥ %» и «Красный ≤ −%», шаг 1, диапазон 0-100. Сохранение в `localStorage` на blur (или сразу onChange — debounce не нужен, всё локально).

Маленькая кнопка-link «Сбросить» рядом — возвращает default 5%/5%.

Подпись/tooltip: «Пороги раскраски — отклонение NPV от базового сценария в процентах».

### 2.3 Применение раскраски

**Таблица NPV (`sensitivity-tab.tsx`):**
- `npvClass(value, baseValue, thresholds)` пересчитывается с порогами.
- `deltaRatio = (value - baseValue) / baseValue`
- Если `deltaRatio >= thresholds.greenPct / 100` → `text-green-600`
- Если `deltaRatio <= -thresholds.redPct / 100` → `text-red-600`
- Иначе нейтральный (без класса)
- Edge case `baseValue === 0` или `null` → нейтральный (как сейчас).

**Tornado bars (`tornado-chart.tsx`):**
- Принимает `thresholds` prop.
- Для каждого bar (`npv_y1y10` для конкретной (param, delta)): рассчитать deltaRatio относительно base, применить ту же логику.
- Если bar нейтральный — серый (`#9ca3af` Tailwind `gray-400`).

## 3. Архитектура

### 3.1 Новый файл `frontend/lib/sensitivity-thresholds.ts`

```ts
export interface SensitivityThresholds {
  greenPct: number;  // 0..100, default 5
  redPct: number;    // 0..100, default 5
}

export const DEFAULT_SENSITIVITY_THRESHOLDS: SensitivityThresholds = {
  greenPct: 5,
  redPct: 5,
};

const STORAGE_KEY = "sensitivity-thresholds-v1";

export function loadSensitivityThresholds(): SensitivityThresholds { /* localStorage */ }
export function saveSensitivityThresholds(t: SensitivityThresholds): void { /* localStorage */ }
```

Pattern скопирован с `frontend/lib/pdf-sections.ts`. SSR-safe (`typeof window !== "undefined"` guard).

### 3.2 Новый компонент `frontend/components/projects/sensitivity-thresholds-controls.tsx`

```tsx
interface Props {
  value: SensitivityThresholds;
  onChange: (next: SensitivityThresholds) => void;
}
```

2 number-input + reset button. Авто-сохранение в localStorage в parent.

### 3.3 Изменения в `sensitivity-tab.tsx`

- `useState<SensitivityThresholds>(loadSensitivityThresholds())` в начале компонента.
- При onChange — save + setState.
- Передать в `npvClass()` (новый параметр) и в `<TornadoChart thresholds={thresholds} ...>`.
- `npvClass(value, base, thresholds)` принимает 3й аргумент.
- Render `<SensitivityThresholdsControls>` в header рядом со scope selector.

### 3.4 Изменения в `tornado-chart.tsx`

- Новый prop `thresholds: SensitivityThresholds`.
- Динамические цвета bars: функция `getBarColor(value: number, base: number, thresholds): string` возвращает hex.
- Учитывает edge case `base === 0` или `null` → серый.

## 4. Backend

**НЕ трогаем.** Sensitivity API остаётся как есть — расчёт NPV не зависит от UI порогов. Hardcoded deltas (-0.20…+0.20) и parameters не меняются.

## 5. Out of scope

- **DB persistence** порогов (`Project.sensitivity_threshold_*` поля + миграция) — Phase 2 если потребуется sync между устройствами.
- **API параметр** для threshold в response — не нужен, раскраска чисто UI.
- **Изменение списка параметров** чувствительности (Цена / COGS / WACC / CAPEX) — не в этом эпике.
- **Изменение deltas** (-0.20..+0.20) — не в этом эпике.

## 6. Файлы (~5)

| # | Файл | Изменение |
|---|------|-----------|
| 1 | `frontend/lib/sensitivity-thresholds.ts` | new (~30 строк) |
| 2 | `frontend/components/projects/sensitivity-thresholds-controls.tsx` | new (~50 строк) |
| 3 | `frontend/components/projects/sensitivity-tab.tsx` | useState, передача в npvClass + TornadoChart, render controls в header |
| 4 | `frontend/components/projects/tornado-chart.tsx` | thresholds prop, getBarColor helper |
| 5 | `frontend/e2e/c20-sensitivity-thresholds.spec.ts` | Playwright test.skip с TODO |
| 6 | `CHANGELOG.md` + `docs/CLIENT_FEEDBACK_v2_STATUS.md` | пункт 17 🟡 → ✅ |

## 7. Testing

### 7.1 Compile-time

`npx tsc --noEmit` — 0 новых ошибок.

### 7.2 Playwright e2e

```ts
test.skip("C #20 — изменение порога меняет раскраску ячеек", async ({ page }) => {
  // TODO: требует проект с рассчитанной чувствительностью.
  // Ожидаемое: установить green=15%, ячейки между +5% и +15% становятся
  // нейтральными (были зелёными при default 5%).
});
```

### 7.3 Manual в браузере

После реализации controller:
- Открыть вкладку Чувствительность → видны два input «Зелёный ≥ %» / «Красный ≤ −%» с default 5/5.
- Изменить green на 20 → ячейки с delta < +20% становятся нейтральными.
- Tornado bars: нейтральные бары становятся серыми.
- Reload страницы → пороги сохранены (localStorage).
- Reset кнопка → возвращает 5/5.

## 8. Acceptance criteria

- [ ] `frontend/lib/sensitivity-thresholds.ts` создан, SSR-safe localStorage
- [ ] `SensitivityThresholdsControls` компонент создан (2 input + reset)
- [ ] `sensitivity-tab.tsx`: useState + onChange + проброс
- [ ] `tornado-chart.tsx`: thresholds prop + динамические цвета
- [ ] `npvClass()` принимает thresholds, edge case base=null/0 → нейтральный
- [ ] tsc clean
- [ ] Playwright spec создан (skip с TODO)
- [ ] CHANGELOG + STATUS обновлены (#17)
- [ ] Manual smoke: изменение порога меняет раскраску, reload сохраняет, reset работает

## 9. Open решения

- **localStorage vs DB**: localStorage (как C #27). Простота > sync между устройствами на текущей стадии.
- **Раздельные пороги** vs **симметричный slider**: раздельные. Точнее, гибче.
- **Default 5%/5%**: типично для FMCG чувствительности.
- **Reset button**: одна кнопка, не два (общий reset обоих порогов).
