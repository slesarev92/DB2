# Фаза C #13 Q4 — OBPPC: перенос в группу «Основа» (design)

**Дата:** 2026-05-16
**Автор:** SashaS (через brainstorm с LLM-агентом)
**Статус:** Design — ожидает user review перед writing-plans
**Связанные документы:**
- `GO4.md` §2 — backlog Фазы C, рекомендация warmup'а
- `docs/CLIENT_FEEDBACK_v2_DECISIONS.md:61-73` — фиксация Q4 (вариант (а))
- `docs/CLIENT_FEEDBACK_v2.md` MEMO 1.3 — постановка от заказчика
- `docs/CLIENT_FEEDBACK_v1.md:444-446` — BL-12 (исходное замечание)

---

## 1. Цель

Перенести таб **OBPPC** в навигации проекта из группы **«Дистрибуция» ③** в группу **«Основа» ①**, поставив его сразу после таба **«Содержание»**.

Это закрывает MEMO 1.3 / BL-12: «OBPPC логичнее в описании, а не в Дистрибуции» — таб содержательно описывает ценовое позиционирование SKU по форматам/каналам, а не дистрибуцию как таковую.

**Acceptance:**
- В сайдбаре проекта `<OBPPC>` отображается под `<Содержание>` в группе ① «Основа»
- В группе ③ «Дистрибуция» остаются только `<Каналы>` и `<АКБ>`
- Существующие записи `obppc_entries` загружаются без потерь; FK на `channels.id` сохранён
- `npx tsc --noEmit` — 0 ошибок
- Backend + БД + миграции — без изменений

---

## 2. Решения по подсхемам (зафиксировано)

### 2.1 Скоуп — **только frontend navigation**

Decision Q4 (вариант (а)) явно зафиксирован: БД, API, OBPPCService — без изменений. Миграция данных не нужна, FK `ProjectSKU × Channel` сохраняется.

### 2.2 Позиция OBPPC в группе «Основа» — **после `content`**

User pick: `overview → content → obppc → financial-plan`. Мотивация — таб OBPPC семантически продолжает «Содержание» (описание ценового позиционирования SKU), и пользователь хотел минимальное число изменений.

Альтернативы (отклонены):
- В конец группы (после `financial-plan`) — разрывает связь content ↔ obppc
- Переименование группы `basics` в «Содержание» — коллизия с `SECTION_LABELS.content = "Содержание"`
- Переименование и группы, и таба `content` — расширяет scope без необходимости

### 2.3 Название группы — **«Основа» остаётся**

Не переименовываем `basics.label` и `SECTION_LABELS.content`. Никаких текстовых правок в UI.

### 2.4 Что НЕ делаем (явно из decision)

- Не схлопываем матрицу OBPPC до одной записи на SKU (вариант (б) отклонён)
- Не меняем `OBPPCRead` / `OBPPCCreate` schemas
- Не трогаем cross-tab references (например, `frontend/lib/use-project-progress.ts` использует `SECTION_GROUPS.map(...)` — автоматически подхватит новый порядок)

---

## 3. Архитектура изменений

### 3.1 Файл `frontend/lib/project-nav-context.tsx`

Единственный source-of-truth по навигации. Изменения в двух массивах:

**`TAB_ORDER` (строки 23-40)** — `"obppc"` со строки 31 (после `akb`) переезжает на позицию 3 (после `content`):

```ts
export const TAB_ORDER = [
  "overview",
  "content",
  "obppc",        // ← было после akb
  "financial-plan",
  "skus",
  "ingredients",
  "channels",
  "akb",
  "periods",
  "fine-tuning",
  "scenarios",
  "results",
  "sensitivity",
  "pricing",
  "value-chain",
  "pnl",
] as const;
```

**`SECTION_GROUPS` (строки 70-76)** — `obppc` перемещается из `distribution.tabs` в `basics.tabs`:

```ts
export const SECTION_GROUPS: readonly SectionGroup[] = [
  { key: "basics", label: "Основа", number: "①",
    tabs: ["overview", "content", "obppc", "financial-plan"] },
  { key: "product", label: "Продукт", number: "②",
    tabs: ["skus", "ingredients"] },
  { key: "distribution", label: "Дистрибуция", number: "③",
    tabs: ["channels", "akb"] },
  { key: "modeling", label: "Моделирование", number: "④",
    tabs: ["periods", "fine-tuning", "scenarios"] },
  { key: "analysis", label: "Анализ", number: "⑤",
    tabs: ["results", "sensitivity", "pricing", "value-chain", "pnl"] },
];
```

**Тип `TabValue` остаётся идентичным** (порядок в `as const` tuple меняется, но union literal не меняется).

### 3.2 Документация

- `docs/CLIENT_FEEDBACK_v2_STATUS.md:49` — статус строки «OBPPC — перенести из Дистрибуции в Содержание» → ✅ со ссылкой на коммит/PR
- `CHANGELOG.md` `[Unreleased]` — запись `feat(c13): move OBPPC tab to «Основа» group (after «Содержание»)`

### 3.3 Что не меняется

| Артефакт | Состояние |
|---|---|
| Бэкенд / API / БД | без изменений |
| `obppc_entries`, FK constraints | без изменений |
| `frontend/components/projects/obppc-tab.tsx` | без изменений |
| `frontend/lib/obppc.ts` (client) | без изменений |
| `frontend/app/(app)/projects/[id]/page.tsx` строка `activeTab === "obppc"` | без изменений (рендер таба тот же) |
| `frontend/lib/use-project-progress.ts` | без изменений (порядок ключей в `FilledMap` инициализаторе косметически менять не обязательно — TypeScript требует все ключи, но порядок свободный; группы пересчитываются через `SECTION_GROUPS.map(...)`) |
| `SECTION_LABELS.obppc = "OBPPC"` | без изменений |
| `SECTION_LABELS.content = "Содержание"` | без изменений |

---

## 4. Тестирование

### 4.1 Type-check

```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```

Ожидаемо: 0 ошибок (изменения только в литералах массивов, тип `TabValue` идентичен).

### 4.2 Frontend restart (структурное изменение SECTION_GROUPS)

По правилу `feedback-frontend-structural-restart` — после правки контейнер frontend перезапускается с очисткой `.next` (Windows+Docker HMR не подхватывает изменения структуры const).

### 4.3 Smoke в браузере

1. Открыть существующий проект (например, `/projects/1`)
2. Sidebar показывает:
   - ① **Основа**: Параметры, Содержание, **OBPPC** (под Содержание), Фин. план
   - ③ **Дистрибуция**: Каналы, АКБ (без OBPPC)
3. Клик на OBPPC → рендерится `<ObppcTab>` с существующими записями (если есть)
4. Создание новой OBPPC-записи: канал-dropdown работает, FK сохраняется
5. Прогресс-индикатор группы «Основа» считает 4 секции (был 3); группы «Дистрибуция» — 2 секции (был 3)

### 4.4 Acceptance GORJI

Не запускаем — расчётное ядро не трогаем, нулевой риск drift'а. Но прогон стандартного suite (`pytest -q --ignore=tests/integration`) ожидаем = 508 passed (без новых backend-тестов).

---

## 5. Риски и заметки

### 5.1 UX-риск: OBPPC раньше channels в порядке заполнения

После переезда OBPPC в группу ① пользователь видит таб **до** того, как заполнит группу ③ «Дистрибуция» (channels). Это означает, что при первом открытии OBPPC dropdown «канал» может быть пустым.

**Митигация:** не нужна — `<ObppcTab>` уже корректно показывает `EmptyState` при отсутствии каналов, и сценарий «открыл OBPPC до channels» возможен и сейчас (порядок табов в сайдбаре — рекомендательный, не обязательный). Decision заказчика сознательный.

### 5.2 Прогресс группы — 4/4 vs 3/3

Группа «Основа» теперь содержит 4 секции, из которых `obppc` всегда `false` в `useProjectProgress` (helper держит `obppc: false` константой, так как deep check «есть ли OBPPC-записи» дорогой). Пользователь увидит группу «Основа» как заведомо неполную (max 3/4), пока вручную не заполнит OBPPC.

**Решение:** оставляем как есть. Это совпадает с поведением для `ingredients`, `akb` и других «всегда optional» секций. Не вводим спец-логику ради одной группы.

### 5.3 Persistence активного таба

Если у пользователя в URL/localStorage сохранён `activeTab=obppc`, переход останется валидным — `TabValue` union содержит `"obppc"` в обоих раскладках. Никаких миграций runtime-состояния не нужно.

---

## 6. План реализации (preview, детально — в writing-plans)

1. **Изменить `frontend/lib/project-nav-context.tsx`** — 2 правки в литералах массивов (`TAB_ORDER`, `SECTION_GROUPS`)
2. **`npx tsc --noEmit`** — убедиться, что 0 ошибок
3. **Restart frontend контейнера + purge `.next`**
4. **Smoke в браузере** (§4.3)
5. **Обновить `docs/CLIENT_FEEDBACK_v2_STATUS.md:49`** — статус ❓ → ✅
6. **Запись в `CHANGELOG.md` [Unreleased]**
7. **Коммит** на ветке `feat/c13-obppc-in-basics`: `feat(c13): move OBPPC tab to «Основа» group`
8. **Merge** в main (single-commit, можно squash или fast-forward — не эпик, `--no-ff` не нужен)

Effort estimate: **30–60 минут** end-to-end.

Subagent-driven workflow **не применяется** — задача меньше порога (5+ task'ов) из memory `feedback-subagent-driven-workflow`. Controller (= текущая сессия) делает всё сам.

---

## 7. Файлы, затронутые изменением

| Файл | Тип изменения |
|---|---|
| `frontend/lib/project-nav-context.tsx` | edit (2 массива) |
| `docs/CLIENT_FEEDBACK_v2_STATUS.md` | edit (1 строка статуса) |
| `CHANGELOG.md` | edit (запись в `[Unreleased]`) |
| `docs/superpowers/specs/2026-05-16-c13-q4-obppc-in-contents-design.md` | new (этот файл) |
| `docs/superpowers/plans/2026-05-16-c13-q4-obppc-in-contents.md` | new (создаст writing-plans) |
