# Аудит расчётного ядра — Цифровой паспорт проекта

**Дата:** 2026-04-12 (первичный аудит), обновлён **2026-04-14**.
**Версия продукта:** v0.3.0 (Phase 8 complete) + Client Feedback v1 (38/40 закрыты).
**Scope аудита:** 12-шаговый pipeline (s01-s12), контекст, агрегатор,
оркестратор, сервис расчёта. 1400+ строк engine/, 400+ строк service.
**Верификация:** 444 pytest + 4 acceptance (GORJI эталон, NPV drift y1y3=0.00%, y1y10=0.03%).

---

## Update 2026-04-14 — перепроверка после LOGIC-01..07 и D-12 fix

**Что изменилось с 2026-04-12:**
- `LOGIC-01` — copacking mode (own/copacking) добавлен в Project и ProjectSKU,
  шаг `s03_cogs` учитывает `copacking_rate` при `production_mode=copacking`.
- `LOGIC-02` — `cm_threshold` (порог Go/No-Go) стал настраиваемым полем Project
  (default 0.25), `s12_gonogo.py` больше не содержит хардкода.
- `LOGIC-04` — sensitivity analysis принимает `period_scope` (Y1-Y3 / Y1-Y5 / Y1-Y10).
- `LOGIC-06` — P&L экспорт выведен как отдельная DATA-структура (43 per-period строк).
- `LOGIC-07` — `vat_rate` добавлен на BOMItem (per-ingredient НДС: 0% / 10% / 20%).
- `D-12 fix` — scope Y1-Y5 в `SCOPE_BOUNDS` (s11_kpi.py) исправлен с 6 столбцов
  (Excel-typo) на 5 лет (коммит 530c976). Решение по бизнес-смыслу вместо
  буквального следования Excel; раньше было задокументировано как "сохранён
  намеренно", теперь — исправлено.

**Acceptance-перепрогон (2026-04-14):**
| Scope | Drift vs Excel-эталон | Статус |
|---|---|---|
| Y1-Y3 | 0.00% | ✅ идеально |
| Y1-Y10 | 0.03% | ✅ в пределах Variant B |
| Y1-Y5 | 50.03% | ⚠️ **expected** — Excel-эталон держит typo (6 столбцов), наш код правильный (5) |

`test_e2e_gorji.py` обновлён: Y1-Y5 исключён из drift-проверки с комментарием
про D-12 fix. Регрессия для Y1-Y5 ловится через совпадение Y1-Y3 и Y1-Y10
(одни и те же формулы, разный scope). PPTX slide count 13 → 16 (Phase 8).

**Что закрыто в разделе 3 "Что работает ПЛОХО" после LOGIC-01..07:**
- ~~Copacking = 0 (нет поля)~~ → **закрыто LOGIC-01** (см. 3.2, 4.x)
- ~~Go/No-Go: CM ≥ 25% захардкожен~~ → **закрыто LOGIC-02**
- ~~D-12: Y1-Y5 = 6 лет (Excel-typo сохранён)~~ → **закрыто D-12 fix**

**Что осталось из 3.1 CRITICAL (не блокеры для Gate Review, но лимиты roadmap):**
- Ценовая эластичность — нет (Phase 3).
- Каннибализация между SKU — нет (Phase 4).
- Промо-лифт — нет (Phase 3).
- Loss carryforward — нет (Phase 2, 2 часа).

**Не-математические находки аудита 2026-04-14 (security):** вынесены отдельно
в `docs/SECURITY_AUDIT_2026-04-14.md`. Критично: IDOR на projects endpoints
(**блокер для enterprise-продаж**), hardcoded prod admin creds.

---

## 1. Общая оценка

| Критерий | Оценка | Комментарий |
|---|---|---|
| Корректность формул | ✅ Высокая | Все 20 расхождений ТЗ vs Excel выявлены и исправлены (D-01...D-22) |
| Верификация | ✅ Пройдена | Per-unit accuracy совпадает с GORJI Excel до 0.01% |
| Архитектура кода | ✅ Чистая | Pure Python pipeline без side effects, frozen inputs, нет двойного учёта |
| Полнота для Gate Review | ✅ Достаточная | NPV/IRR/ROI/Payback/Go-No-Go — стандартный набор для FMCG gate |
| Полнота для ценовой оптимизации | ❌ Отсутствует | Нет эластичности спроса, нет промо-лифта |
| Полнота для портфельного анализа | ❌ Отсутствует | Нет каннибализации, нет portfolio NPV |
| Полнота для risk assessment | ⚠️ Базовая | 3 сценария (Base/Cons/Aggr), но нет Monte Carlo / диапазонов |

**Вердикт:** Модель соответствует уровню **Excel-моделей, которые используют
80% FMCG-компаний в РФ/СНГ для Gate Reviews** (Unilever, Mars, P&G на
ранних стадиях G0-G2). Для следующего уровня (ценовая оптимизация,
портфельное планирование) требуются значительные доработки — это уровень
enterprise-инструментов типа SAP IBP / Anaplan / o9 Solutions (от $100K/год).

---

## 2. Что работает ХОРОШО

### 2.1 Формулы верифицированы и корректны

Все критические формулы проверены против Excel-эталона:

| ID | Проблема | Статус | Влияние если бы не исправили |
|---|---|---|---|
| D-01 | OCF: формула Working Capital | ✅ Исправлено | Ошибка −4.6М₽ на Y1 |
| D-02 | VAT: деление vs умножение | ✅ Исправлено | Ошибка 4.17% по ex-factory |
| D-03 | Tax: база = Contribution, не EBITDA | ✅ Исправлено | Завышение налога |
| D-04 | Production cost: % от ex-factory | ✅ Исправлено | Неправильная привязка к инфляции |
| D-14 | Годовые периоды: множитель ×12 | ✅ Исправлено | 12-кратный недоучёт объёмов Y4-Y10 |
| D-22 | Перерасчёт WC/Tax на годовом уровне | ✅ Исправлено | Σ(monthly ΔWC) ≠ annual ΔWC |

Полный список: `docs/TZ_VS_EXCEL_DISCREPANCIES.md` (20 позиций, все закрыты).

### 2.2 Нет двойного учёта

Каждая статья вычитается **ровно один раз** в строго определённом месте:

```
Net Revenue
  − COGS (материалы + производство + копакинг)     → s03
= Gross Profit                                      → s04
  − Логистика − Project OPEX                        → s05
= Contribution                                       → s05
  − CA&M (% от NR) − Marketing (% от NR)           → s06
= EBITDA                                             → s06
  + ΔWC + Tax                                        → s07, s08
= Operating Cash Flow                               → s09
  − CAPEX                                            → s09
= Free Cash Flow                                    → s09
```

Проверено: нет пересечений между шагами. Нет циклических зависимостей
(строгий DAG, каждый шаг зависит только от предыдущих).

### 2.3 Гибкость входных параметров

Pipeline принимает **per-period tuples** (43 значения: M1-M36 + Y4-Y10)
для всех ключевых параметров:

- `shelf_price_reg` — цена полки с инфляцией по месяцам
- `bom_unit_cost` — BOM с инфляцией сырья
- `logistics_cost_per_kg` — логистика с инфляцией
- `production_cost_rate` — ставка производства (с учётом copacking windows)
- `channel_margin`, `promo_discount`, `promo_share` — параметры канала

Это значит **инфляция, сезонность, launch lag** применяются корректно
по месяцам без аппроксимации.

### 2.4 Архитектурная чистота

- **PipelineInput** — frozen dataclass (immutable), валидация длин массивов
  в `__post_init__`
- **PipelineContext** — мутабельный контейнер, каждый шаг проверяет
  pre-conditions (нужные поля предыдущих шагов)
- **12 файлов = 12 шагов**, каждый делает одну вещь
- Pipeline = pure Python, не ходит в БД, нет side effects
- Service layer грузит данные → формирует PipelineInput → запускает pipeline
  → сохраняет результат

---

## 3. Что работает ПЛОХО / ограничения

### 3.1 Критичные для бизнес-решений

#### 3.1.1 Нет ценовой эластичности спроса

**Проблема:** Модель считает volume = f(ND, offtake, seasonality). Цена
**не влияет на объём**. Если поднять shelf_price на 20% — NR вырастет на
20%, volume останется прежним.

**В реальности:** CPG-компании используют коэффициенты эластичности:
```
% изменения объёма = elasticity × % изменения цены
```
Типичная эластичность FMCG: −1.5...−2.5 (повышение цены на 5% →
падение объёма на 7.5-12.5%). По данным отраслевых исследований,
CPG-бренд тестировал +5% цены, эконометрическая модель предсказала
−3.8% объёма, факт был −3.6% — что позволило уверенно поднять маржу
на 12% ([CPG Data Insights](https://www.cpgdatainsights.com/answer-business-questions/how-to-apply-price-elasticity/)).

**Влияние:** Без эластичности невозможно ответить на вопрос "какая цена
максимизирует прибыль?" — это ключевой вопрос Revenue Growth Management.

#### 3.1.2 Нет каннибализации между SKU

**Проблема:** Если запустить 4 SKU одного бренда в одном канале, модель
считает что каждый берёт **свой** объём (ND × offtake). В реальности
новый SKU частично **ворует объём** у существующих SKU того же бренда.

**Влияние:** NPV проекта с 4 SKU может быть **завышен на 20-40%** если
каннибализация не учтена. Enterprise-инструменты (o9 Solutions) имеют
специальные модули: "by analyzing similar products and market opportunities,
you can prevent cannibalization effects"
([o9 Solutions](https://o9solutions.com/articles/sap-ibp-isnt-the-best-path-for-an-integrated-business-planning-evolution)).

#### 3.1.3 Нет промо-лифта (volume uplift от промо-акций)

**Проблема:** В модели промо влияет **только на цену** (через promo_discount
и promo_share). Объём не меняется — промо просто снижает среднюю цену.

**В реальности:** Промо-акция 30% off обычно даёт **2-5x volume lift** на
период акции. По данным Nielsen, ~59-60% trade promotions в FMCG не
окупаются, потому что "volume is not incremental profit — promoted volume
can grow while profitability declines if discounts, fees, and decay exceed
the contribution margin from lift"
([RapidPricer](https://www.rapidpricer.com/post/are-your-promotions-really-profitable-measuring-true-roi-in-fmcg-trade-promotions)).

Также критически важен **post-promotion decay**: после промо объём
проседает на 40-60% от baseline в первую неделю, восстанавливается к
4-й неделе. Модель этого не учитывает.

**Влияние:** Без промо-лифта и decay оценка trade spend ROI невозможна.

#### 3.1.4 Нет переноса налоговых убытков (loss carryforward)

**Проблема:** Если Contribution в Y1 отрицательный (запуск, большие
инвестиции), налог = 0. В Y2 (прибыльный) налог считается с полной CM
без вычета убытка Y1.

**В реальности:** В РФ убытки можно переносить вперёд до 5 лет (ст. 283
НК РФ), уменьшая налогооблагаемую базу до 50% от прибыли.

**Влияние:** Для проектов с убыточным Y1-Y2 (типичный FMCG launch)
налог в Y3-Y5 **завышен** на 10-20%.

### 3.2 Средние — влияют на точность прогноза

| # | Ограничение | Суть |
|---|---|---|
| 1 | **WACC постоянный** (19%) | Ставка не меняется 10 лет — в реальности зависит от ключевой ставки ЦБ, leverage, risk profile |
| 2 | **Universe outlets статичен** | Число точек канала не растёт — X5 открывает ~500/год, Wildberries растёт 30%/год |
| 3 | **CA&M / Marketing = % от NR** | В реальности — фиксированный бюджет, не пропорциональный выручке |
| 4 | **WC = 12% от NR** | Не учитывает DSO/DPO/DIO (дни оплаты, запасов). FMCG типично: DSO 30-45 дней, DPO 60-90 дней, DIO 20-40 дней → WC = 5-15% от NR в зависимости от условий |
| 5 | ~~**Copacking = 0**~~ | ✅ **Закрыто LOGIC-01 (2026-04-13):** `production_mode` (own/copacking) + `copacking_rate` на ProjectSKU, `s03_cogs` учитывает |
| 6 | **Tax base = Contribution** | Не taxable income: нет амортизации, R&D вычетов, процентов по кредитам |
| 7 | **Scenario deltas только на ND/offtake** | Нет price/COGS/logistics дельт — нельзя моделировать "рост сырья +15%" |
| 8 | ~~**Go/No-Go: CM ≥ 25% захардкожен**~~ | ✅ **Закрыто LOGIC-02 (2026-04-13):** `cm_threshold` на Project (default 0.25), используется в `s12_gonogo.py` |

### 3.3 Низкие — косметические

| # | Ограничение |
|---|---|
| 1 | ~~D-12: Y1-Y5 scope = 6 лет вместо 5 (Excel-тайпо, сохранён намеренно)~~ | ✅ **Закрыто D-12 fix (2026-04-13):** SCOPE_BOUNDS Y1-Y5 = 5 лет, решение по бизнес-смыслу |
| 2 | Payback = целые годы, нет дробного (3.7 → 4) |
| 3 | Нет валидации вводных (отрицательная цена, нулевой universe — не проверяются) |
| 4 | Terminal Value чувствителен к последним 2 годам FCF |

---

## 4. Что ЛЕГКО улучшить (Low effort, High impact)

### 4.1 Перенос налоговых убытков

**Сложность:** 🟢 Низкая (1-2 часа)
**Влияние:** Корректный налог для проектов с убыточным запуском

Добавить в `s08_tax.py` cumulative loss tracker:
```python
cumulative_loss = 0.0
for t in range(n):
    taxable = contribution[t] + cumulative_loss  # offset by carryforward
    if taxable > 0:
        # Cap carryforward usage at 50% of current profit (RF tax code art.283)
        usable_loss = min(-cumulative_loss, taxable * 0.5)
        tax[t] = -(taxable + usable_loss) * tax_rate  # reduced tax
        cumulative_loss += usable_loss  # reduce remaining loss
    else:
        tax[t] = 0
        cumulative_loss += contribution[t]  # accumulate loss
```

### 4.2 Настраиваемый порог Go/No-Go

**Сложность:** 🟢 Низкая (30 минут)
**Влияние:** Разные пороги для разных категорий

Добавить поле `cm_threshold` в модель Project (default 0.25), использовать
в `s12_gonogo.py` вместо хардкода.

### 4.3 Валидация вводных на границе service → pipeline

**Сложность:** 🟢 Низкая (1-2 часа)
**Влияние:** Раннее обнаружение ошибок ввода

В `calculation_service._build_line_input()` добавить:
- shelf_price_reg > 0 (предупреждение если ≤ 0)
- universe_outlets > 0 (предупреждение если = 0)
- channel_margin < 1.0 (ошибка если = 1.0 → ex_factory = 0)
- bom_unit_cost > 0 (предупреждение)

### 4.4 Дробный Payback (с линейной интерполяцией)

**Сложность:** 🟢 Низкая (1 час)
**Влияние:** Payback 3.7 лет вместо 4

### 4.5 Scenario deltas на price/COGS/logistics

**Сложность:** 🟡 Средняя (4-6 часов)
**Влияние:** "Что если сырьё подорожает на 15%?" — ключевой
сценарий для risk assessment

Расширить `ScenarioChannelDelta` моделью с полями:
`delta_shelf_price`, `delta_bom_cost`, `delta_logistics`.
В `_build_line_input` применять аналогично `delta_nd/delta_offtake`.

---

## 5. Что СЛОЖНО улучшить (High effort)

### 5.1 Ценовая эластичность спроса

**Сложность:** 🔴 Высокая (2-4 недели)
**Почему сложно:**
- Нужны **исторические данные** продаж для калибровки коэффициентов
- Или **экспертные оценки** эластичности per-category
- Меняет фундаментальную модель: volume перестаёт быть input,
  становится f(price, ND, elasticity)
- Нужен UI для ввода кривых эластичности

**Минимальная реализация:**
Добавить `price_elasticity` коэффициент (default −2.0) на уровне
ProjectSKUChannel. В `s01_volume` модифицировать:
```python
# Если цена отклоняется от baseline, объём корректируется
price_change_pct = (shelf_price[t] - shelf_price[0]) / shelf_price[0]
volume_adj = 1.0 + elasticity * price_change_pct
volume_units[t] *= max(volume_adj, 0)
```

### 5.2 Промо-лифт и post-promotion decay

**Сложность:** 🔴 Высокая (2-3 недели)
**Почему сложно:**
- Нужна **кривая лифта** (volume uplift = f(discount_depth, duration))
- Нужен **decay curve** (post-promo velocity drop 40-60% → recovery за 4 недели)
- Это per-period модификация volume, не цены
- По данным Nielsen, 59-60% trade promotions не окупаются — без этого
  модуля невозможно правильно оценить trade spend ROI

### 5.3 Каннибализация между SKU

**Сложность:** 🔴 Высокая (2-4 недели)
**Почему сложно:**
- Нужна **матрица переключений** (switching matrix) между SKU
- Требует данных о поведении покупателей
- Меняет архитектуру: расчёт перестаёт быть per-line independent,
  появляется cross-line зависимость

### 5.4 Monte Carlo / стохастический анализ

**Сложность:** 🔴 Высокая (1-2 недели)
**Почему сложно:**
- Нужно определить **распределения** для каждого input parameter
- Запуск pipeline 1000-10000 раз с random samples
- UI для отображения NPV-гистограмм и confidence intervals
- Celery-задача станет тяжёлой (сейчас ~50ms → 50-500 секунд)

### 5.5 Баланс и P&L как полноценные финансовые отчёты

**Сложность:** 🔴 Высокая (3-4 недели)
**Почему сложно:**
- Текущая модель считает **cash flow**, не accounting P&L
- Нет balance sheet (активы, обязательства, капитал)
- Нет depreciation, amortization
- Нет accounts payable/receivable с timing
- Полноценные financial statements — это уровень SAP/Oracle

---

## 6. Сравнение с индустриальными стандартами

### 6.1 Что есть у enterprise-решений, чего нет у нас

| Возможность | SAP IBP (~$30K/мес) | Anaplan (~$100K/год) | o9 Solutions | Наша модель |
|---|---|---|---|---|
| NPV/IRR/ROI расчёт | ✅ | ✅ | ✅ | ✅ |
| 3 сценария (Base/Cons/Aggr) | ✅ | ✅ | ✅ | ✅ |
| Per-SKU × Channel P&L | ✅ | ✅ | ✅ | ✅ |
| Инфляция per-period | ✅ | ✅ | ✅ | ✅ |
| Сезонность | ✅ | ✅ | ✅ | ✅ |
| Ценовая эластичность | ✅ | ✅ | ✅ | ❌ |
| Промо-лифт и decay | ✅ | ✅ | ✅ | ❌ |
| Каннибализация | ⚠️ Базовая | ⚠️ Базовая | ✅ | ❌ |
| Monte Carlo / risk | ⚠️ | ✅ | ✅ | ❌ |
| ML demand forecasting | ⚠️ | ✅ | ✅ | ❌ |
| Real-time market data | ⚠️ | ⚠️ | ✅ | ❌ |
| Portfolio optimization | ⚠️ | ✅ | ✅ | ❌ |
| Balance Sheet / P&L | ✅ | ✅ | ✅ | ❌ |

### 6.2 Что есть у стандартных FMCG Excel-моделей

Типичный Excel-шаблон CPG financial model ([eFinancialModels](https://www.efinancialmodels.com/downloads/category/financial-model/fmcg/),
[ModelOptic](https://www.modeloptic.com/financial-model-templates/consumer-products))
включает:

| Возможность | Типичный Excel | Наша модель |
|---|---|---|
| Revenue по каналам | ✅ | ✅ |
| COGS breakdown | ✅ | ✅ |
| Multi-SKU | ⚠️ (обычно 1-3) | ✅ (неограниченно) |
| NPV/IRR/Payback | ✅ | ✅ |
| Sensitivity analysis | ✅ (ручная) | ✅ (автоматическая, 4 param × 5 delta) |
| Горизонт 10 лет | ✅ | ✅ |
| Income Statement | ✅ | ⚠️ (P&L waterfall, не full IS) |
| Balance Sheet | ✅ | ❌ |
| Cash Flow Statement | ✅ | ✅ (FCF) |
| Инфляция | ⚠️ (простая) | ✅ (ступенчатая per-period) |
| Export PPT/PDF | ❌ | ✅ |
| Collaborative editing | ❌ | ✅ (web-based) |
| History / audit trail | ❌ | ✅ (append-only versioning) |

**Вывод:** Наша модель **превосходит типичный FMCG Excel** по автоматизации,
collaborative features, export'ам. **Уступает** по наличию Balance Sheet
и Income Statement.

---

## 7. Roadmap улучшений (рекомендация)

### Phase 2 — Quick wins (1-2 недели)

| # | Что | Effort | Impact |
|---|---|---|---|
| 1 | Loss carryforward в налогах | 2 часа | Корректный NPV для launch-проектов |
| 2 | Настраиваемый CM порог Go/No-Go | 30 мин | Гибкость по категориям |
| 3 | Валидация вводных (границы) | 2 часа | Защита от ошибок ввода |
| 4 | Дробный Payback | 1 час | Точнее отображение |
| 5 | Scenario deltas на price/COGS | 6 часов | Моделирование "рост сырья +15%" |
| 6 | Copacking field в схеме | 2 часа | Для контрактного производства |

### Phase 3 — Серьёзные доработки (1-2 месяца)

| # | Что | Effort | Impact |
|---|---|---|---|
| 7 | Ценовая эластичность (базовая) | 2-4 недели | Ответ на "какая цена оптимальна" |
| 8 | Промо-лифт + decay | 2-3 недели | Корректный trade spend ROI |
| 9 | Dynamic universe (рост точек) | 1 неделя | Точнее прогноз по каналам |
| 10 | WC через DSO/DPO/DIO | 1 неделя | Реалистичный working capital |

### Phase 4 — Enterprise-level (3-6 месяцев)

| # | Что | Effort | Impact |
|---|---|---|---|
| 11 | Каннибализация между SKU | 2-4 недели | Корректный portfolio NPV |
| 12 | Monte Carlo стохастический анализ | 1-2 недели | NPV-диапазоны вместо точки |
| 13 | Full Income Statement + Balance Sheet | 3-4 недели | Полноценная фин. отчётность |
| 14 | ML demand forecasting | 1-2 месяца | Замена ручного Predict layer |

---

## 8. Заключение

### Модель корректна для своего уровня

Расчётное ядро **правильно реализует** стандартную FMCG financial model:
volume → revenue → COGS → GP → CM → EBITDA → FCF → NPV/IRR → Go/No-Go.
Все формулы верифицированы против Excel-эталона. Архитектура чистая,
нет двойного учёта, нет циклических зависимостей.

### Модель подходит для Gate Review

Для стандартной процедуры Gate Review (G0-G5) в FMCG-компании модель
предоставляет **все необходимые KPI**: NPV по 3 горизонтам, IRR, ROI,
Payback, Go/No-Go flag, sensitivity analysis, сравнение сценариев.
Экспорт в PPT/PDF готов к презентации.

### Ключевые ограничения — это ограничения класса продукта

Отсутствие эластичности, каннибализации, промо-лифта — это не баги,
а **границы scope** MVP. Аналогичные ограничения имеют **все** FMCG
Excel-модели. Разница с enterprise-инструментами (SAP IBP $30K/мес,
Anaplan $100K/год, o9 Solutions custom pricing) — в объёме данных
и ML-моделировании, которое требует исторических данных продаж
и специалистов по data science.

### Что делать дальше

**Если продукт для Gate Review** (текущий use case) — модель готова.
Рекомендуется добавить quick wins из Phase 2 (loss carryforward,
валидация, scenario deltas на price/COGS) — это повысит точность
на 5-15% при минимальных усилиях.

**Если продукт для Revenue Growth Management** — нужна Phase 3
(эластичность + промо-лифт). Это переведёт продукт на уровень выше
стандартного Excel и приблизит к enterprise-решениям.

**Если продукт для Portfolio Planning** — нужна Phase 4
(каннибализация + Monte Carlo + full financial statements). Это уровень
конкуренции с SAP/Anaplan/o9.

---

## Sources

- [Capital Budgeting: NPV, IRR — Financial Modeling Prep](https://site.financialmodelingprep.com/education/other/Capital-Budgeting-Techniques-NPV-IRR-and-More--A-Comprehensive-Guide)
- [NPV vs IRR — Corporate Finance Institute](https://corporatefinanceinstitute.com/resources/valuation/npv-vs-irr/)
- [FMCG Financial Model Templates — eFinancialModels](https://www.efinancialmodels.com/downloads/category/financial-model/fmcg/)
- [Consumer Products Financial Model — ModelOptic](https://www.modeloptic.com/financial-model-templates/consumer-products)
- [CPG Financial Model and Valuation — Apollo Financial Models](https://apollofinancialmodels.com/products/consumer-company-financial-model-and-valuation)
- [Price Elasticity in CPG — CPG Data Insights](https://www.cpgdatainsights.com/answer-business-questions/how-to-apply-price-elasticity/)
- [Predictive Analytics in CPG — LatentView](https://www.latentview.com/blog/predictive-analytics-in-cpg/)
- [Trade Promotion ROI in FMCG — RapidPricer / Nielsen data](https://www.rapidpricer.com/post/are-your-promotions-really-profitable-measuring-true-roi-in-fmcg-trade-promotions)
- [Trade Promotion Effectiveness Metrics — SoftServe](https://softservebs.com/en/resources/trade-promotion-analysis/)
- [Trade Spend ROI Model for CPG — CFO Pro Analytics](https://cfoproanalytics.com/cfo-wiki/cpg/how-to-build-a-trade-spend-roi-model-a-cfo-playbook-for-optimizing-cpg-promotions-profitability-growth/)
- [SAP IBP — Integrated Business Planning](https://www.sap.com/products/scm/integrated-business-planning.html)
- [o9 Solutions vs SAP IBP](https://o9solutions.com/articles/sap-ibp-isnt-the-best-path-for-an-integrated-business-planning-evolution)
- [Anaplan Supply Chain Planning](https://supplychaindigital.com/top10/top-10-demand-planning-platforms)
- [Working Capital Cycle — Corporate Finance Institute](https://corporatefinanceinstitute.com/resources/accounting/working-capital-cycle/)
- [Demand Forecasting for CPG — Dynamic DIS](https://www.dynamicdis.com/post/cpg-demand-forecasting-guide)
