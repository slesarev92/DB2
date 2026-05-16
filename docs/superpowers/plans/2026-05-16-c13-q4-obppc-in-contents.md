# C #13 Q4 — OBPPC в группу «Основа» (implementation plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Переместить таб **OBPPC** из группы «Дистрибуция» ③ в группу «Основа» ① (после таба «Содержание») в навигации проекта.

**Architecture:** Чисто frontend navigation refactor. Изменения в двух массивах-литералах в `frontend/lib/project-nav-context.tsx` (single source of truth по навигации) + обновление двух файлов документации. Бэкенд, БД, API, OBPPCService — без изменений; миграция данных не нужна.

**Tech Stack:** Next.js 14 App Router, TypeScript, React. Verification — `npx tsc --noEmit` + manual browser smoke (frontend проект не имеет unit-test runner-а; единственный test-файл — `frontend/e2e/smoke.spec.ts`).

**Spec reference:** `docs/superpowers/specs/2026-05-16-c13-q4-obppc-in-contents-design.md`

**Branch:** `feat/c13-obppc-in-basics` (уже создана, спека закоммичена `d9d823b`).

---

## TDD note

Этот план **не использует TDD-цикл**, потому что:
1. Нет нового кода или логики — только перестановка элементов в двух const-массивах
2. Во `frontend/` нет unit-test runner-а (jest/vitest); единственный тест — e2e smoke (`frontend/e2e/smoke.spec.ts`), не покрывающий навигационную раскладку
3. Verification: `npx tsc --noEmit` (статическая проверка типов) + manual smoke в браузере

Это сознательный выбор; см. spec §4.

---

## Task 1: Перенести `obppc` в `TAB_ORDER` и `SECTION_GROUPS`

**Files:**
- Modify: `frontend/lib/project-nav-context.tsx:23-40` (`TAB_ORDER`)
- Modify: `frontend/lib/project-nav-context.tsx:70-76` (`SECTION_GROUPS`)

- [ ] **Step 1: Изменить `TAB_ORDER`** — переместить строку `"obppc"` с позиции после `"akb"` на позицию после `"content"`.

Найти строки 23-40 и заменить блок целиком на:

```ts
export const TAB_ORDER = [
  "overview",
  "content",
  "obppc",
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

**Что было:** `"obppc"` на позиции 8 (между `"akb"` и `"periods"`).
**Что стало:** `"obppc"` на позиции 3 (между `"content"` и `"financial-plan"`).
**Тип `TabValue`** (union из всех значений tuple) остаётся идентичным — `"obppc"` присутствует в обоих раскладках.

- [ ] **Step 2: Изменить `SECTION_GROUPS`** — переместить `"obppc"` из `distribution.tabs` в `basics.tabs` (после `"content"`).

Найти строки 70-76 и заменить блок целиком на:

```ts
export const SECTION_GROUPS: readonly SectionGroup[] = [
  { key: "basics", label: "Основа", number: "①", tabs: ["overview", "content", "obppc", "financial-plan"] },
  { key: "product", label: "Продукт", number: "②", tabs: ["skus", "ingredients"] },
  { key: "distribution", label: "Дистрибуция", number: "③", tabs: ["channels", "akb"] },
  { key: "modeling", label: "Моделирование", number: "④", tabs: ["periods", "fine-tuning", "scenarios"] },
  { key: "analysis", label: "Анализ", number: "⑤", tabs: ["results", "sensitivity", "pricing", "value-chain", "pnl"] },
];
```

**Что было:** `basics.tabs` = 3 элемента, `distribution.tabs` = 3 элемента (`obppc` в конце).
**Что стало:** `basics.tabs` = 4 элемента (`obppc` после `content`), `distribution.tabs` = 2 элемента.

- [ ] **Step 3: Проверить, что больше ничего не нужно править в этом файле**

`SECTION_LABELS` (строки 44-61), `TabValue`, типы и Provider — без изменений. Команды:

```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend grep -n "obppc" /app/lib/project-nav-context.tsx
```

Expected output (3 строки):
```
26:  "obppc",
52:  obppc: "OBPPC",
73:    tabs: ["overview", "content", "obppc", "financial-plan"] },
```

(Номера строк ориентировочные — главное, чтобы `obppc` появлялся ровно 3 раза: в `TAB_ORDER`, в `SECTION_LABELS`, в `basics.tabs`.)

---

## Task 2: Type-check + restart frontend

**Files:** (verification only, no edits)

- [ ] **Step 1: Запустить TypeScript-проверку**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```

Expected: **0 ошибок, без output**.

Если есть ошибки — НЕ продолжать. Скорее всего опечатка в литерале или нарушение типа `TabValue`/`SectionGroup`. Прочитать ошибку, исправить, перезапустить.

- [ ] **Step 2: Restart frontend контейнера с purge `.next`**

По правилу `feedback-frontend-structural-restart` (Windows+Docker HMR не подхватывает изменения структуры const):

```bash
docker compose -f infra/docker-compose.dev.yml stop frontend
docker compose -f infra/docker-compose.dev.yml run --rm frontend sh -c "rm -rf .next"
docker compose -f infra/docker-compose.dev.yml up -d frontend
```

Подождать ~10 сек, проверить:

```bash
docker compose -f infra/docker-compose.dev.yml ps frontend
```

Expected: `Up <время> (healthy)` (или просто `Up <время>` если у frontend нет healthcheck).

- [ ] **Step 3: Дождаться готовности Next.js dev server**

```bash
docker compose -f infra/docker-compose.dev.yml logs --tail=30 frontend
```

Expected (в последних строках): `▲ Next.js 14.x.x` и `✓ Ready in <time>`. Если в логах ошибки сборки — исправить и перезапустить.

---

## Task 3: Smoke-тест в браузере

**Files:** (verification only)

- [ ] **Step 1: Открыть существующий проект**

В браузере: `http://localhost:3000/projects/1` (или любой существующий project id; если БД пустая — сначала создать проект через `/projects/new`).

- [ ] **Step 2: Проверить раскладку сайдбара**

Sidebar должен показать пять групп в порядке:

```
① Основа
   • Параметры
   • Содержание
   • OBPPC          ← новая позиция
   • Фин. план

② Продукт
   • SKU и BOM
   • Ингредиенты

③ Дистрибуция
   • Каналы
   • АКБ            ← OBPPC отсюда удалён

④ Моделирование
   • Fine tuning (периоды)
   • Fine Tuning per-period
   • Сценарии

⑤ Анализ
   • Результаты
   • Чувствительность
   • Цены
   • Unit-экономика
   • P&L
```

- [ ] **Step 3: Клик на OBPPC → таб отрисовывается**

Кликнуть «OBPPC» в группе ① «Основа». В правой панели должен появиться компонент `<ObppcTab>` (таблица OBPPC-записей с колонками SKU, Канал, Тир, Формат, ml, Цена). Если записей нет — `EmptyState` с предложением создать запись.

- [ ] **Step 4: Создание OBPPC-записи (если есть SKU и каналы)**

Если у проекта есть хотя бы один SKU и один канал — нажать «+ Добавить запись», выбрать SKU, выбрать канал из dropdown, заполнить остальные поля, сохранить. Запись должна сохраниться (POST /api/projects/{id}/obppc → 200/201). Это подтверждает, что FK `obppc_entries.channel_id → channels.id` работает после перемещения таба.

- [ ] **Step 5: Прогресс-индикаторы**

Прогресс группы «Основа» считает 4 секции (max 4/4). Прогресс группы «Дистрибуция» считает 2 секции (max 2/2). До правки было 3/3 и 3/3 соответственно.

- [ ] **Step 6: Перезагрузка страницы**

F5 на `/projects/1`. Сайдбар отрисовывается тот же — OBPPC в «Основа», нет в «Дистрибуция».

Если все 6 шагов пройдены — Task 3 готов.

---

## Task 4: Коммит фронтенд-правок

**Files:** (commit only)

- [ ] **Step 1: Стейджить изменённый файл**

```bash
git add frontend/lib/project-nav-context.tsx
git status
```

Expected:
```
On branch feat/c13-obppc-in-basics
Changes to be committed:
        modified:   frontend/lib/project-nav-context.tsx
```

(Никаких других файлов в staged быть не должно. Если есть — разобраться откуда.)

- [ ] **Step 2: Закоммитить**

```bash
git commit -m "$(cat <<'EOF'
feat(c13): move OBPPC tab to «Основа» group (after «Содержание»)

C #13 Q4 (MEMO 1.3 / BL-12): OBPPC семантически описывает ценовое
позиционирование SKU, а не дистрибуцию — переезжает из группы
«Дистрибуция» ③ в «Основа» ① после таба «Содержание».

Изменения только в frontend/lib/project-nav-context.tsx:
- TAB_ORDER: "obppc" с позиции 8 на позицию 3
- SECTION_GROUPS: "obppc" из distribution.tabs в basics.tabs

Backend, БД, API, OBPPCService — без изменений; миграция данных не
нужна; FK obppc_entries.channel_id сохраняется.

Spec: docs/superpowers/specs/2026-05-16-c13-q4-obppc-in-contents-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Подтвердить коммит**

```bash
git log --oneline -3
```

Expected (топ): `<hash> feat(c13): move OBPPC tab to «Основа» group ...`.

---

## Task 5: Обновить документацию

**Files:**
- Modify: `docs/CLIENT_FEEDBACK_v2_STATUS.md:49`
- Modify: `CHANGELOG.md` (раздел `[Unreleased]`)

- [ ] **Step 1: Обновить `docs/CLIENT_FEEDBACK_v2_STATUS.md:49`**

Найти строку:
```
| OBPPC — перенести из Дистрибуции в Содержание | ❓ | Сейчас группа `distribution` в `project-nav-context.tsx:71` содержит `channels, akb, obppc`. Таблица `obppc_entries` имеет FK на `channels.id`. Перенос в "Содержание" возможен без миграции данных — таб переедет в группу `basics`. Решение от заказчика не зафиксировано. |
```

Заменить целиком на:
```
| OBPPC — перенести из Дистрибуции в Содержание | ✅ | Закрыто C #13 Q4 (2026-05-16). `obppc` перемещён из `distribution.tabs` в `basics.tabs` после `content` в `frontend/lib/project-nav-context.tsx`. БД/API/сервис без изменений, FK сохранён. См. spec `docs/superpowers/specs/2026-05-16-c13-q4-obppc-in-contents-design.md`. |
```

- [ ] **Step 2: Добавить запись в `CHANGELOG.md` [Unreleased]**

Открыть `CHANGELOG.md`, найти раздел `## [Unreleased]`. Под существующим заголовком фазы (например, `### Changed (Phase B)` или ниже всех B-записей) добавить **новую секцию** для фазы C:

```markdown
### Changed (Phase C)

- **C #13 Q4 OBPPC — перенос в группу «Основа» (MEMO 1.3, 2026-05-16).**
  Таб OBPPC семантически описывает ценовое позиционирование SKU,
  а не дистрибуцию. Перемещён из группы «Дистрибуция» ③ в «Основа» ①
  после таба «Содержание». Чисто frontend navigation refactor:
  `frontend/lib/project-nav-context.tsx` — `TAB_ORDER` и
  `SECTION_GROUPS`. Backend, БД, API, OBPPCService не тронуты;
  миграция данных не нужна; FK `obppc_entries.channel_id → channels.id`
  сохранён.
  - Spec: `docs/superpowers/specs/2026-05-16-c13-q4-obppc-in-contents-design.md`
  - Plan: `docs/superpowers/plans/2026-05-16-c13-q4-obppc-in-contents.md`
  - Verification: `npx tsc --noEmit` 0 ошибок; manual browser smoke ok.
```

Если в `[Unreleased]` уже есть раздел `### Changed (Phase C)` (например, после закрытого C #14) — добавить пункт C #13 первым/вторым в существующий раздел, не дублировать заголовок.

- [ ] **Step 3: Закоммитить документацию**

```bash
git add docs/CLIENT_FEEDBACK_v2_STATUS.md CHANGELOG.md
git status
```

Expected:
```
Changes to be committed:
        modified:   CHANGELOG.md
        modified:   docs/CLIENT_FEEDBACK_v2_STATUS.md
```

```bash
git commit -m "$(cat <<'EOF'
docs(c13): close MEMO 1.3 — OBPPC в «Основа» (STATUS + CHANGELOG)

- docs/CLIENT_FEEDBACK_v2_STATUS.md: статус «OBPPC — перенести из
  Дистрибуции в Содержание» ❓ → ✅ со ссылкой на spec.
- CHANGELOG.md [Unreleased]: запись C #13 Q4 в Phase C.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Финальная проверка и merge на main

**Files:** (verification + merge)

- [ ] **Step 1: Проверить, что ветка чистая**

```bash
git status
git log --oneline main..HEAD
```

Expected (3 коммита на ветке):
```
<hash3> docs(c13): close MEMO 1.3 — OBPPC в «Основа» (STATUS + CHANGELOG)
<hash2> feat(c13): move OBPPC tab to «Основа» group (after «Содержание»)
d9d823b docs(c13): spec — move OBPPC to «Основа» group
```

- [ ] **Step 2: Повторный type-check (страховка)**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T frontend npx tsc --noEmit
```

Expected: 0 ошибок.

- [ ] **Step 3: Backend test suite (страховка — backend не трогали, должно остаться 508 passed)**

```bash
docker compose -f infra/docker-compose.dev.yml exec -T backend pytest -q --ignore=tests/integration 2>&1 | tail -3
```

Expected: `508 passed`.

- [ ] **Step 4: Спросить пользователя о merge стратегии**

Поскольку C #13 = small navigation refactor (не эпик), merge стратегия зависит от предпочтения пользователя:

- **squash** (1 коммит на main) — компактно для маленькой задачи
- **fast-forward** (3 коммита: spec → code → docs) — сохраняет историю
- **--no-ff** (4 коммита: 3 + merge-коммит) — как в C #14 для эпиков

Default — **fast-forward** (по правилу «squash для single-commit fixes, --no-ff для эпиков»; у нас 3 коммита, между — `--no-ff` опционален).

**НЕ мержить без подтверждения пользователя**.

- [ ] **Step 5: После approval — merge**

Пример (fast-forward):
```bash
git checkout main
git merge feat/c13-obppc-in-basics --ff-only
git log --oneline -5
```

Пример (squash):
```bash
git checkout main
git merge --squash feat/c13-obppc-in-basics
git commit -m "feat(c13): move OBPPC to «Основа» group (Q4, MEMO 1.3) ..."
```

- [ ] **Step 6: Удалить feature-ветку**

```bash
git branch -d feat/c13-obppc-in-basics
git branch
```

Expected: `* main`, без `feat/c13-...`.

- [ ] **Step 7: Сообщить пользователю о готовности**

Краткий отчёт:
- C #13 закрыт; ветка смержена в main, удалена
- Изменён 1 файл фронтенда (`project-nav-context.tsx`), обновлены STATUS + CHANGELOG
- Tests: 508 passed (backend без изменений); tsc 0 ошибок; manual smoke ok
- Phase C: 2/18 ✅ (#14 + #13)
- Следующий кандидат — по рекомендации GO4: brainstorm #16 (каналы группы) или #17 (АКБ)

---

## Self-review checklist

- ✅ **Spec coverage:** §1, §2, §3.1, §3.2, §4 спеки покрыты Tasks 1-5; §6 (план) = весь этот документ; §7 (file map) — упоминается в Task 4-5.
- ✅ **Placeholders:** Нет TBD/TODO. Все команды и патчи показаны полностью.
- ✅ **Type consistency:** `TabValue`, `SectionGroup`, `SECTION_GROUPS`, `TAB_ORDER` используются единообразно.
- ✅ **Scope:** Plan focused — единственный frontend файл + 2 doc-файла. Декомпозиция не требуется.
