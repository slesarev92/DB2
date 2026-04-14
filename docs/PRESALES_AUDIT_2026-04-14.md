# Аудит готовности к продажам — Цифровой паспорт проекта

**Дата:** 2026-04-14
**Версия:** git tip после коммита `98971dc` (v0.3.0 + Client Feedback v1 — 38/40 закрыто)
**Цель:** оценить готовность продукта для enterprise-продаж FMCG-клиентам.
**Формат:** 5 фаз аудита, каждая завершается findings + блокеры.
**Связанные документы:**
- [`docs/ENGINE_AUDIT_REPORT.md`](ENGINE_AUDIT_REPORT.md) — математика ядра
- [`docs/SECURITY_AUDIT_2026-04-14.md`](SECURITY_AUDIT_2026-04-14.md) — security
- [`docs/TZ_VS_EXCEL_DISCREPANCIES.md`](TZ_VS_EXCEL_DISCREPANCIES.md) — D-01..D-22 формулы
- [`docs/CLIENT_FEEDBACK_v1.md`](CLIENT_FEEDBACK_v1.md) — 40 замечаний заказчика
- [`docs/ERRORS_AND_ISSUES.md`](ERRORS_AND_ISSUES.md) — журнал проблем

---

## Executive summary

_(раздел наполняется по мере закрытия фаз)_

| Фаза | Scope | Статус | Блокеры |
|---|---|---|---|
| 1 | Математика + security | ✅ закрыта | 🔴 IDOR, 🔴 admin/admin123 |
| 2 | Invalidation после PATCH | ✅ закрыта | 🟡 нет staleness UI (F-01/F-02), AI cache OK через context hash |
| 3 | Dropdowns/labels | ✅ закрыта | 🟡 L-01..L-06 неконсистентная русификация (fix ~1.5ч) |
| 4 | Usability + export quality | ✅ закрыта | 🔴 U-02 BUG-01 prod export, U-03 empty-SKU layout; 🟡 U-01 toasts, U-04 progress |
| 5 | HelpButton (реализация) | ⏳ | — |

---

## Фаза 1 — Математика + security

**Результат:** ✅ pipeline корректен. См. ENGINE_AUDIT_REPORT § "Update 2026-04-14"
и SECURITY_AUDIT_2026-04-14.md.

**Блокеры продаж (из Фазы 1):**
1. 🔴 **S-01 IDOR** — `project_service.get_project()` не фильтрует по
   `created_by`; любой юзер читает/меняет/удаляет чужие проекты. Fix 3-5ч.
2. 🔴 **S-02 admin/admin123 на prod** — `scripts/seed_demo_project.py`
   бьёт по проду с тривиальным паролем. Fix 30 мин.

**Известные ограничения (не блокеры):**
- Нет ценовой эластичности / каннибализации / промо-лифта (Phase 3-4 roadmap).
- Нет loss carryforward в налогах (quick win, 2 часа).
- Rate limiting только на AI endpoints.

---

## Фаза 2 — Invalidation после PATCH

**Scope:** проверить что изменение editable полей (ProjectSKU rates, PSC
channel params, PeriodValue fine-tuning, Project параметры, BOMItem,
Scenario deltas) помечает ScenarioResult как устаревший и уведомляет
пользователя.

### Архитектура (как есть сейчас)

```
PATCH /api/project-skus/{id}           ◁── user меняет rate
    └─ project_sku_service.update()
         └─ UPDATE project_skus SET ..., updated_at=NOW()  ← триггер onupdate
         └─ session.commit()
         └─ return updated row                  ◁── НЕТ invalidation

scenario_results — без изменений:
    npv, irr, roi, calculated_at = вчерашний timestamp
    go_no_go = True (возможно теперь False)
    is_stale: колонки нет

AI cache в Redis:
    ai_cache:{project_id}:{feature}:{input_hash} — живёт 24ч
    (никто не удаляет при PATCH)
```

### Findings

**🟡 F-01 (MEDIUM) — ScenarioResult не имеет флага staleness**

`backend/app/models/entities.py:756` (class ScenarioResult) содержит:
- `calculated_at: datetime` — timestamp последнего расчёта
- НЕТ `is_stale: bool` или `invalidated_at: datetime | None`

Ни один из 12 PATCH-файлов в `backend/app/api/` не делает:
- `DELETE FROM scenario_results WHERE scenario_id IN (SELECT FROM scenarios WHERE project_id = ?)`
- `UPDATE scenario_results SET is_stale = true WHERE ...`
- Redis AI cache `DEL ai_cache:{project_id}:*`

**Означает:** пользователь меняет любое поле → результаты в БД остаются
старыми, UI показывает их как актуальные. Пользователь должен **вручную**
нажать "Пересчитать".

**🟡 F-02 (MEDIUM) — нет UI-индикатора "результаты устарели"**

Frontend:
- `frontend/types/api.ts:506` — `calculated_at: string` передаётся, но
  не используется.
- Нет React Query / SWR → нет автоматического staleTime.
- Нет логики сравнения `calculated_at` vs `updated_at` (ни на бэке,
  ни на фронте).
- В результатных табах (Results, Scenarios, P&L, ValueChain) нет badge
  "⚠️ Расчёт устарел на N минут".

**Пример риска:** аналитик поменял VAT rate на 10%, посмотрел на старый
KPI-экран, скопировал NPV в презентацию клиенту, **забыл пересчитать**.
В проде: NPV в презентации — неверный.

**🟢 F-03 (LOW) — AI cache: TTL-only, но `input_hash` включает ScenarioResult**

`ai_cache.py:112-125` — `hash_context(context: dict)` вычисляет SHA-256
от **всего** context dict (sorted JSON). `AIContextBuilder` кладёт туда
актуальные NPV/IRR/ROI/margins из ScenarioResult. Значит:
- После recalculate → новые scenario_results → новый context → новый хэш →
  cache miss → свежий AI-комментарий. ✅
- PATCH без recalc → старые scenario_results → старый хэш → cache hit →
  старый комментарий. Но это абсурдный flow (KPI-комментарий по устаревшим
  данным бессмыслен для UX), и после обязательного recalc инвалидация
  происходит автоматически через diff хэша.

Комментарий в ai_cache.py (Phase 7.5 TODO) неточный — explicit
invalidation **не требуется** для корректности при типичном flow
(PATCH → recalc → AI). Но безвредна как belt-and-suspenders.

**🟢 F-04 (OK) — `updated_at` обновляется автоматически**

`TimestampMixin` использует `server_default=func.now(), onupdate=func.now()`
— при любом UPDATE БД автоматически обновляет `updated_at`. Инфраструктура
для staleness проверки есть (только не используется).

**🟡 F-05 (MEDIUM) — Celery-worker без auto-reload**

CLAUDE.md явно указывает:
> Restart celery-worker — ОБЯЗАТЕЛЬНО после изменений в calculation_service,
> engine/, sensitivity_service. Celery НЕ имеет auto-reload.
> Признак проблемы: API работает, recalculate возвращает 200, но в БД
> старые значения / новые поля = NULL.

В `infra/docker-compose.dev.yml` нет `watchmedo auto-restart` для celery-worker.
Это чисто dev-issue (prod деплой всегда пересобирает образ), но в dev
приводит к "работает на моём браузере, а в БД чушь" моментам.

### Рекомендации для Фазы 2

**Минимальный fix (3-4 часа):**

1. **Backend** (`calculation_service.py`, все PATCH endpoints):
   - При PATCH любого entity, которое влияет на pipeline — вызывать
     `await invalidation_service.mark_project_stale(session, project_id)`:
     ```python
     await session.execute(
         update(ScenarioResult)
         .where(ScenarioResult.scenario_id.in_(
             select(Scenario.id).where(Scenario.project_id == project_id)
         ))
         .values(is_stale=True)
     )
     await ai_cache.invalidate_project(redis, project_id)
     ```
   - Добавить колонку `is_stale: bool` на ScenarioResult (миграция
     с `server_default='false'`).
   - После успешного recalculate — сбросить `is_stale=False`.

2. **Frontend:**
   - В results-tab / scenarios-tab / pnl-tab читать `scenario_result.is_stale`,
     показывать badge:
     ```tsx
     {result.is_stale && (
       <Alert variant="warning">
         <AlertTitle>Расчёт устарел</AlertTitle>
         <AlertDescription>
           Данные проекта были изменены после последнего пересчёта.
           <Button onClick={recalculate}>Пересчитать сейчас</Button>
         </AlertDescription>
       </Alert>
     )}
     ```

3. **AI cache invalidation** (`ai_cache.py`):
   - Функция `invalidate_project(redis, project_id)`:
     ```python
     pattern = f"ai_cache:{project_id}:*"
     async for key in redis.scan_iter(pattern):
         await redis.delete(key)
     ```
   - Вызывается из PATCH endpoints и /recalculate.

4. **Celery-worker dev auto-reload** (optional, quality-of-life):
   - В `docker-compose.dev.yml` заменить команду на:
     `watchmedo auto-restart --directory=/app --pattern=*.py --recursive
     -- celery -A app.worker worker --loglevel=info`
   - Добавить `watchdog` в `requirements-dev.txt`.

**Estimated total effort:** 4-5 часов + 5-6 integration-тестов.

### Блокеры продаж из Фазы 2

- 🟡 **F-01/F-02 (UX)** — средний приоритет. Для enterprise-продаж
  клиент **будет** спрашивать "а если я поменял данные, мне покажут что
  нужно пересчитать?". Если нет — выглядит как "сырой продукт".
  **Не блокер**, но сильно понижает impression на демо.

- 🟡 **F-03 (AI staleness)** — низкий-средний приоритет. AI-комментарии
  маркетинговая фича, не data integrity. Но клиент может скриншотить
  противоречие "KPI NPV = 50М, AI-комментарий: 'проект выглядит слабо
  с NPV 20М'" — плохой look.

---

## Фаза 3 — Dropdowns / labels

**Scope:** все Select / option компоненты в `frontend/components/projects/`,
все enum values из backend (ScenarioType, PeriodScope, PeriodType, SourceType,
PriceTier, PackFormat, GateStage, FunctionReadinessStatus, UserRole,
OpexCategory), консистентность русских переводов.

### Coverage matrix

| Enum | Backend values | Frontend LABELS map | Покрытие | Комментарий |
|---|---|---|---|---|
| ScenarioType | base / conservative / aggressive | ❌ **расхождение** | 33% | Три разных map в разных tabs |
| PeriodScope | y1y3 / y1y5 / y1y10 | SCOPE_LABELS ✅ | 100% | "Y1-Y3 / Y1-Y5 / Y1-Y10" (аббр ок) |
| PeriodType | monthly / annual | ❌ нет map | 0% | Raw values в SelectItem |
| GateStage | G0-G5 | GATE_LABELS ✅ | 100% | "Идея/Концепция/.../Масштабирование" |
| FunctionReadinessStatus | green / yellow / red | FUNCTION_STATUS_LABELS ✅ | 100% | Ок |
| PriceTier | premium / mainstream / value | ❌ нет map | 0% | `obppc-tab.tsx:236-238` hardcoded английский |
| PackFormat | "bottle" (только это используется) | ❌ нет map и нет enum | 0% | `obppc-tab.tsx:92` raw "bottle" |
| OpexCategory | 14 значений | OPEX_CATEGORY_LABELS ⚠️ | 50% | **Смешаны:** "Digital"/"PR"/"SMM" + "ПОСМ"/"Листинги" |
| SourceType | predict / finetuned / actual | SOURCE_LABELS ❌ | 0% | `value-history-dialog.tsx:34-37` на английском |
| ViewMode (P&L) | monthly / quarterly / annual | MODE_LABELS ✅ | 100% | Ок |

### Findings

**🟡 L-01 (MEDIUM) — SCENARIO_LABELS расходятся в 3 файлах**

Один и тот же enum `ScenarioType` переводится по-разному:
- `scenarios-tab.tsx:45-49` → "Base" / "Conservative" / "Aggressive" 🔴
- `periods-tab.tsx:38-42` → "Base" / "Conservative" / "Aggressive" 🔴
- `results-tab.tsx:50-54` → "Базовый" / "Консервативный" / "Агрессивный" ✅

На экране **Сценарии** (scenarios-tab) показано "Base", на экране
**Результаты** (results-tab) то же самое называется "Базовый". Для
enterprise-клиента это выглядит как "разные разработчики писали, никто
не проверил согласованность" — первый красный флажок на демо.

**Fix:** вынести единый `SCENARIO_LABELS` в `frontend/types/api.ts`
с русскими значениями, импортировать во все 3 файла (plus
`channel-deltas-editor.tsx:231`). **15 минут.**

**🟡 L-02 (MEDIUM) — PriceTier / PackFormat / SourceType без LABELS**

- `obppc-tab.tsx:236-238` — `<SelectItem value="premium">Premium</SelectItem>`
  — английский захардкожен.
- `obppc-tab.tsx:92` — `pack_format === "bottle"` без перевода → в UI
  отображается сырое `"bottle"`.
- `value-history-dialog.tsx:34-37` — `SOURCE_LABELS = {predict: "Predict",
  finetuned: "Fine-tuned", actual: "Actual"}` — **весь history-диалог
  на английском.**

**Fix:** создать PRICE_TIER_LABELS, PACK_FORMAT_LABELS, SOURCE_LABELS
в `types/api.ts`, заменить raw values на `LABELS[value] ?? value`. **30 мин.**

**🟡 L-03 (MEDIUM) — OpexCategory смешанный язык**

`types/api.ts:607-622`:
```typescript
OPEX_CATEGORY_LABELS = {
  digital: "Digital",        // ← англ
  pr: "PR",                  // ← англ (аббр)
  smm: "SMM",                // ← англ (аббр)
  design: "Design",          // ← англ
  posm: "ПОСМ",              // ← рус
  listings: "Листинги",      // ← рус
  other: "Другое",           // ← рус
  ...
}
```

В одном выпадающем списке маркетинговых категорий пользователь видит
"Digital / PR / SMM / Design / ПОСМ / Листинги / Другое" — half-and-half.
**Fix:** единообразно все по-русски: "Диджитал / PR / СММ / Дизайн /
ПОСМ / Листинги / Другое". Аббревиатуры PR/SMM можно оставить латиницей
(индустриальный стандарт), но тогда последовательно везде. **15 мин.**

**🟢 L-04 (LOW) — fallback к raw enum**

`scenarios-tab.tsx:231`, `periods-tab.tsx:224`, `channel-deltas-editor.tsx:231`:
```tsx
{SCENARIO_LABELS[s.type] ?? s.type}   // fallback показывает "base"/"aggressive"
```

Если backend вернёт новый тип сценария (например `"custom"`), UI покажет
сырой enum. Это на будущее — сейчас enum стабилен. **Fix:** fallback
на `"—"`. 5 минут.

**🟡 L-05 (MEDIUM) — tornado chart без русификации**

`tornado-chart.tsx:30-34`:
```typescript
PARAM_LABELS = { nd: "ND", offtake: "Off-take", shelf_price: "Shelf price", cogs: "COGS" }
```

Tornado chart — визуальный ключевой артефакт на демо (sensitivity analysis).
"Off-take" и "Shelf price" — английский. "ND" и "COGS" — аббревиатуры
можно оставить с подсказкой в HelpButton (Phase 5), но "Off-take" должно
стать "Отгрузка" (или оставить "Off-take" как индустриальный термин
с подсказкой).

**🟡 L-06 (MEDIUM) — AI panel history endpoint labels**

`ai-panel-history.tsx:14-26`:
```typescript
ENDPOINT_LABELS = {
  explain_kpi: "Explain KPI",
  sensitivity: "Sensitivity",
  executive_summary: "Executive Summary",
  ...
}
```

Весь history-просмотр AI-запросов на английском. **Fix:** "Объяснение KPI /
Анализ чувствительности / Executive summary / ...". 10 минут.

### Untranslated placeholders / UI strings (не критично)

✅ Good:
- Все form placeholders: "Выберите SKU", "Выберите канал", "Нет данных".
- Заголовки карточек, labels, кнопки — русские.
- Validation messages базовые ("Обязательное поле").

🟡 Minor:
- `content-tab.tsx:361` — `<SelectValue placeholder="—" />` для G0-G5
  (placeholder norm, но можно "Выберите стадию").
- Validation "Score 0-100" hardcoded где-то в формах.

### Рекомендации по Фазе 3

**Total effort:** ~1.5 часа для полного fix всех 6 labels issues.

Приоритет:
1. **L-01** SCENARIO_LABELS — видно на каждом табе. Fix first.
2. **L-02** PriceTier/PackFormat/SourceType — видно при opening value history.
3. **L-03** OpexCategory смешанный — видно в финплане.
4. **L-05** Tornado chart — важно для demo по sensitivity.
5. **L-06** AI history — менее заметно, но нужно для полноты.
6. **L-04** fallback — defensive, можно отложить.

### Блокеры продаж из Фазы 3

**Нет 🔴 блокеров.** Но 🟡 **L-01/L-02/L-03/L-05** суммарно создают
впечатление "русификация не доведена" — для enterprise-клиента это
аргумент снизить цену / попросить "доделать перед оплатой". **Fix
перед первой продажей.**

## Фаза 4 — Usability + export quality

**Scope:** critical paths, empty states, error messages, keyboard navigation,
loading states, visual hierarchy, mobile/tablet responsiveness, export quality
(XLSX/PPTX/PDF на GORJI), demo-readiness для enterprise-клиента.

### Что работает хорошо (acceptance)

- **Empty states информативны:** `skus-tab.tsx:107-114` ("В проекте пока нет
  SKU..."), `channels-panel.tsx:140-143`, `results-tab.tsx:393-406` ("Расчёт
  ещё не выполнен. Нажмите «Пересчитать»..."). Пользователь не видит пустых
  голых списков.
- **Inline form validation:** `FieldError` компонент + `aria-invalid` работают
  (`channel-form.tsx:237-250`). `useFieldValidation` hook переиспользуется.
- **Loading states:** recalculate показывает phased статус ("В очереди →
  Считаем → Обновляем"), buttons disabled при save/export (защита от
  дублирования запросов).
- **KPI color coding:** зелёный/жёлтый/красный маржи в results-tab (пороги
  25% / 15% / <15%) — индустриально-стандартная визуализация.
- **Form layout responsive:** grid-based (`md:grid-cols-3`), корректно
  стакируется на мобильных.
- **Russian labels** практически везде (за вычетом L-01..L-06 из Phase 3).
- **Exports физически работают** на dev (проверено через openpyxl):
  - XLSX: 17.8KB, 3 листа "Вводные / PnL по периодам / KPI", русские заголовки, `₽`.
  - PPTX: 50.4KB, 16 слайдов (+3 с Phase 8).
  - PDF: 43.8KB (<5MB лимит плана).

### Findings

**🔴 U-01 (HIGH) — нет toast/snackbar уведомлений, все ошибки в Card**

Ошибки API (`422`, `500`, `4xx`) показываются в Card внизу экрана
(`sku-panel.tsx:95-100`, `channels-panel.tsx:106-114`, `results-tab.tsx:372-377`).

- **Проблема 1:** при длинной форме (Channel form на 300+ строк,
  `channel-form.tsx`) пользователь нажимает "Сохранить", скроллит вниз
  чтобы увидеть результат → не видит reaction на кнопке.
- **Проблема 2:** при save нескольких форм подряд Card показывает только
  последнюю ошибку, предыдущие теряются.
- **Проблема 3:** success не показывается вообще ("всё сохранено" —
  silent). Пользователь может сохранить дважды.

**Fix:** добавить `<Sonner />` (sonner уже в shadcn ecosystem) с
`toast.success("Сохранено")` / `toast.error("...")`. ~1 час.

**🔴 U-02 (HIGH) — BUG-01 экспорт не работает на prod**

В Phase 1 аудите заказчик (CLIENT_FEEDBACK_v1.md BUG-01) указал что
«Кнопки экспорта (XLSX/PPTX/PDF) не работают на проде». Проверка на dev
(через прямой вызов `generate_project_xlsx/pptx/pdf`) показывает что
генерация **работает** — файлы валидные, русские символы корректны,
KPI заполнены.

**Значит проблема не в backend, а в доставке:**
- CORS (unlikely, но проверить `CORS_ORIGINS` на prod)
- SSL mixed content (если nginx отдаёт https, а backend http)
- `Content-Disposition` header на response endpoint'е
- Browser block на `window.location = blob` (deprecated pattern)
- Новый сервер 85.239.63.206 не имеет правильной proxy-конфигурации для
  передачи binary response от backend

**Action:** открыть Network tab в Chrome на prod, нажать «Скачать XLSX»,
проверить:
- 200 OK от backend?
- Есть ли `Content-Disposition: attachment`?
- Есть ли CORS-related ошибки в console?

**Оценка:** 1-2 часа дебага + fix (вероятнее всего nginx или
frontend blob-handling).

**🟡 U-03 (MEDIUM) — BUG-07 layout ломается при пустом списке SKU**

`skus-tab.tsx:32` — `min-h-[200px]` на BOM panel, но grid `grid-cols-1
gap-6 md:grid-cols-3` не гарантирует стабильную высоту левой (SKU)
колонки при `items.length === 0`. Верстка может съехать — ранний
feedback в Client Feedback v1.

**Fix:** добавить `min-h-[300px]` на SkuPanel контейнер, или использовать
`h-full` и явный parent height. 10 минут.

**🟡 U-04 (MEDIUM) — export loading без progress/ETA**

`results-tab.tsx:350, 357, 364` — кнопка показывает только "Экспорт..."
во время генерации. Нет:
- Spinner / progress bar
- Текста "Генерирую XLSX..."
- ETA (обычно 2-5 сек)

При медленном интернете на демо (hotel wifi) пользователь может решить
что приложение зависло и кликнуть повторно.

**Fix:** заменить на `<Loader2 className="animate-spin" />` +
`"Генерирую XLSX..."` + disable button. 15 минут.

**🟡 U-05 (MEDIUM) — AI Panel без skeleton loading**

`ai-panel-chat.tsx` — во время запроса к Polza AI (5-15 сек латентность)
chat показывает пустой экран. На медленном интернете можно подумать
что AI down.

**Fix:** добавить typing indicator или skeleton bubble ("…"). 15 мин.

**🟡 U-06 (MEDIUM) — BUG-10 truncate без tooltip**

`channels-panel.tsx:171` — `max-w-[180px] truncate` обрезает длинное
название канала. Нет `<Tooltip>` чтобы показать полное имя на hover.

**Fix:** обернуть в `Tooltip` из shadcn. 10 минут.

**🟢 U-07 (LOW) — keyboard navigation частично**

- Sortable headers (`channels-panel.tsx:148-162`) — `cursor-pointer`,
  но нет `:focus-visible` стиля → при Tab не видно куда фокус уехал.
- AG Grid (`periods-grid.tsx`) — нет подсказки "Enter для редактирования
  ячейки" при первом открытии.
- Dialog Escape — работает (shadcn default).
- Enter submit — работает в основных формах.

**Fix:** добавить `focus-visible:ring-2` к sortable headers, onboarding
hint для AG Grid. 30 минут.

**🟢 U-08 (LOW) — responsiveness таблиц**

- `periods-grid.tsx` AG Grid на экранах <768px горизонтально скроллится
  (expected для таблицы с 43 периодами).
- `financial-plan-editor.tsx:169+` — нет явного `overflow-x-auto` на
  wrapper.
- `value-chain-tab.tsx:200+` — есть `overflow-x-auto` ✅.

**Fix:** везде на табличных wrapper'ах `overflow-x-auto`. 15 минут.

### Performance

Измерено через acceptance test `test_e2e_gorji.py` на Docker dev:
- **Full pipeline (8 SKU × 6 каналов × 3 сценария × 3 scope = 72 KPI):**
  ~5 секунд через Celery task (pipeline pure Python, ~50ms на сценарий
  из ENGINE_AUDIT_REPORT).
- **Export XLSX:** ~1 секунда.
- **Export PPTX:** ~1 секунда.
- **Export PDF (WeasyPrint):** ~2 секунды.

Итого: пересчёт + 3 экспорта на GORJI = **~10 секунд**. Для MVP
приемлемо. На 20 SKU × 10 каналов = больше (lineside scaling O(N×M)),
но вряд ли >30 сек.

### Client Feedback v1 BUG-01..BUG-12 статусы (верификация)

Попросил агент проверить в коде по каждому. Сводка:

| BUG | Статус в коде | Коммит-предполагаемый | Комментарий |
|---|---|---|---|
| BUG-01 Export не работает | 🔴 OPEN (prod) | — | Dev работает, prod не работает — nginx/CORS/blob. См. U-02. |
| BUG-02 CAPEX=0 | 🟡 FRONTEND OK | 530c976 | `min="0"` в HTML. Backend validation проверить. |
| BUG-03 Image upload | ⚠️ NEED TEST | — | `sku-image-upload.tsx` есть, надо воспроизвести на prod. |
| BUG-04 OBPPC ошибка | ⚠️ NEED TEST | — | Воспроизвести. |
| BUG-05 Сценарии periodic | ⚠️ NEED TEST | — | Подозрение: race в polling (`results-tab.tsx:191-214`, 1s interval). |
| BUG-06 GateTimeline refresh | 🟡 PARTIAL | 66c9378 | Компонент использует `currentGate` prop. Нужен refetch после PATCH. |
| BUG-07 Layout пустой SKU | 🔴 OPEN | — | См. U-03. |
| BUG-08 Красное в BOM | ⚠️ NEED INFO | 02c2528 | `bom-panel.tsx` — validation styling? |
| BUG-09 Ingredients layout | ⚠️ NEED INFO | 66c9378 | Нет screenshot. |
| BUG-10 Channel name overflow | 🟡 PARTIAL | — | Truncate без tooltip. См. U-06. |
| BUG-11 SupplierQuotes | ⚠️ NEED INFO | — | Нет screenshot. |
| BUG-12 Periods layout | 🟡 PARTIAL | — | AG Grid horiz scroll на mobile. |

**Вывод:** пользователь заявил "38/40 замечаний v1 закрыты", но **BUG-01,
BUG-07 реально открыты** в коде; BUG-02/05/06/08/10/12 — частично;
BUG-03/04/09/11 — нужна верификация на prod с клиентом.

### Блокеры демо

🔴 **Критичные перед демо:**
1. **U-02 BUG-01** export на prod — если клиент нажмёт «Скачать» на
   живом демо и увидит ошибку — катастрофа.
2. **U-03 BUG-07** layout при пустом SKU — первая картинка нового
   проекта выглядит криво.

🟡 **Средние (улучшат impression):**
3. **U-01 toast** — отсутствие явного success feedback делает UI
   "безответным".
4. **U-04 export progress** — без ETA выглядит зависшим.
5. **L-01 SCENARIO_LABELS** из Phase 3 — "Base/Conservative/Aggressive"
   на одном экране вместо "Базовый/Консервативный/Агрессивный".

### Quick wins (1-2 часа суммарно)

1. **U-01** Sonner toasts — 1ч.
2. **U-03** min-h SKU panel — 10 мин.
3. **U-04** export progress — 15 мин.
4. **U-06** tooltip channel name — 10 мин.
5. **L-01..L-06** русификация labels — 1.5ч (Phase 3).

Всего: **~3.5 часа** полного fix quick wins + BUG-01 дебаг (~1-2ч) = ~5
часов до демо-ready.

**U-02 (BUG-01 prod export)** — отдельный debug session с прод-логами
и Chrome Network tab. Без этого демо показывать только без export buttons.

## Фаза 5 — HelpButton (реализация)

_(ещё не проходили)_

---

## Итоги по готовности к продажам (обновляется)

### 🔴 Блокеры (не продавать enterprise до fix)
1. S-01 IDOR — 3-5 часов.
2. S-02 admin/admin123 на prod — 30 минут.

### 🟡 Средние (заметны на демо, но не блокируют)
1. F-01/F-02 — invalidation + staleness UI.
2. F-03 — AI cache invalidation.
3. S-03 — CORS verify на prod.
4. S-04 — rate limit на критичных endpoints.

### 🟢 Готово к продажам (прошло аудит)
1. Математика pipeline — D-01..D-22 верифицированы.
2. XSS в PDF защищён.
3. SQL-injection защита (ORM).
4. Raw SQL — только в тестах.
