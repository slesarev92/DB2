# Расхождения: ТЗ vs Excel-модель (GORJI+)

**Источники:**
- ТЗ: `TZ_Digital_Passport_V3.docx` + `Predikt-k-TZ-V3.xlsx`
- Эталонная модель: `PASSPORT_MODEL_GORJI_2025-09-05.xlsx`, листы: DATA, DASH, VOLUME, NET REVENUE, LOGISTIC COST, OPEX, Profitability
- Дата верификации: 2026-04-08

**Правило реализации:** при любом расхождении — реализовывать строго по Excel-модели.

---

## КРИТИЧЕСКИЕ расхождения (влияют на итоговые KPI)

---

### D-01 — Operating Cash Flow: формула принципиально неверна в ТЗ

**ТЗ (раздел 7.5.5):**
```
OPERATING_CASH_FLOW = CONTRIBUTION × (1 − 0.12) − PROFIT_TAX
```
Трактует оборотный капитал как постоянное удержание (12% от Contribution каждый период).

**Excel (DATA, строки 38–41):**
```
WC[t]  = NET_REVENUE[t] × WC_RATE          # WC_RATE = 0.12 (параметр уровня Project)
ΔWC[t] = WC[t-1] − WC[t]                  # изменение оборотного капитала
TAX[t] = −IF(CONTRIBUTION[t] < 0, 0, CONTRIBUTION[t] × TAX_RATE)
OCF[t] = CONTRIBUTION[t] + ΔWC[t] + TAX[t]
```
Граничный случай: `WC[t-1] = 0` в первом расчётном периоде (нет предыдущего периода).

**Численная разница (иллюстрация):**

| Год | Выручка | Contribution | ТЗ-формула OCF | Excel OCF | Разница |
|-----|---------|--------------|-----------------|-----------|---------|
| Y0  | 257 т.₽ | 108 т.₽  | 95 т.₽          | 56 т.₽    | −41 т.₽ |
| Y1  | 38,9 М.₽ | −104 т.₽ | −91 т.₽         | −4,7 М.₽  | −4,6 М.₽ |
| Y2  | 105 М.₽ | 23,2 М.₽ | 20,4 М.₽        | 10,6 М.₽  | −9,8 М.₽ |

В зрелых годах с выходом выручки на плато ΔWC → 0, и формулы сближаются. Но в период роста разница огромна и NPV/IRR рассчитываются неверно при ТЗ-формуле.

**Реализовать:** формулу Excel. `WC_RATE = 0.12` — именованный параметр уровня Project, `default = 0.12`.

---

### D-02 — VAT в формуле ex-factory цены: ×(1−VAT) vs /(1+VAT)

**ТЗ (раздел 7.5.2):**
```
EX_FACTORY_PRICE = SHELF_PRICE_WEIGHTED × (1 − CHANNEL_MARGIN) × (1 − VAT_RATE)
```

**Excel (DASH, строки 33–35):**
```
SHIPPING_REG   = (SHELF_PRICE_REG   / (1 + VAT_RATE)) × (1 − CHANNEL_MARGIN)
SHIPPING_PROMO = (SHELF_PRICE_PROMO / (1 + VAT_RATE)) × (1 − CHANNEL_MARGIN)
SHIPPING_W     = SHIPPING_REG × (1 − PROMO_SHARE) + SHIPPING_PROMO × PROMO_SHARE
```
что алгебраически эквивалентно:
```
EX_FACTORY_PRICE = SHELF_PRICE_WEIGHTED / (1 + VAT_RATE) × (1 − CHANNEL_MARGIN)
```

**Численная разница для VAT = 20%:**
- ТЗ: `× 0.80` → цена отгрузки = 80% от полки до вычета маржи
- Excel: `/ 1.20` = `× 0.8333` → цена отгрузки = 83.33%
- **Ошибка ТЗ: −4.17% от ex-factory цены**, что транслируется в −4.17% выручки и всех производных.

Математически корректная операция — делить на `(1 + VAT_RATE)`, а не умножать на `(1 − VAT_RATE)`.

**Реализовать:** `EX_FACTORY = SHELF_PRICE_WEIGHTED / (1 + VAT_RATE) × (1 − CHANNEL_MARGIN)`

---

### D-03 — База налога на прибыль

**ТЗ (раздел 7.6, шаг 11):**
```
PROFIT_TAX = TAXRATE × TAXBASE
```
TAXBASE определён как "упрощённая модель, см. Excel", формула не раскрыта.

**Excel (DATA, строка 40):**
```
PROFIT_TAX[t] = −IF(CONTRIBUTION[t] < 0, 0, CONTRIBUTION[t] × 0.20)
```
- База налога = **Contribution** (после логистики и OPEX, до CA&M и маркетинга).
- Налог = 0 при отрицательном Contribution (убыток не создаёт налоговый щит).
- Ставка: 20% (значение из DASH!C3... нет, 19% = ставка дисконтирования, 20% = налог — хардкод).

**Замечание:** ставка налога 20% захардкожена в формуле Excel. Должна быть параметром `TAX_RATE` уровня Project, `default = 0.20`.

**Реализовать:** `TAX[t] = IF(CONTRIBUTION[t] >= 0, CONTRIBUTION[t] × TAX_RATE, 0)` (знак минус в OCF уже учтён при сложении).

---

## ВЫСОКИЕ расхождения (влияют на структуру COGS)

---

### D-04 — Производственные затраты: ₽/шт vs % от выручки

**ТЗ (раздел 4.7):**
`PRODUCTIONCOSTPERUNIT` — абсолютная величина в ₽/шт, уровень ProjectSKU.

**Excel (DASH, строка 38):**
```
Production_cost% = Profitability!E26 + Profitability!E37   # % от ex-factory
Gross_Profit_per_unit = Shipping_W − Material − Package − Shipping_W × Production% − Copacker
```
Производство задаётся как **% от цены отгрузки**, взятый из бенчмарков Profitability.

**Почему это важно:** при росте цен (инфляция) производственная себестоимость в Excel растёт пропорционально цене; в ТЗ-модели — остаётся фиксированной (или индексируется отдельно). При инфляции 7%/год за 10 лет расхождение накапливается.

**Решение для реализации:** хранить как `PRODUCTION_COST_RATE` (% от EX_FACTORY_PRICE) уровня ProjectSKU. Абсолютный ₽/шт — вычислять, не хранить.

---

### D-05 — P&L иерархия: состав Contribution и EBITDA

**ТЗ:**
```
VARIABLE_OPEX = TRADE_MARKETING + CONSUMER_MARKETING + SALES_EXPENSES
CONTRIBUTION  = NET_REVENUE − COGS − LOGISTICS − VARIABLE_OPEX
EBITDA        = CONTRIBUTION − AMC_PER_COST − MARKETING_COST
```

**Excel (DATA, строки 23–31):**
```
GROSS_PROFIT     = NET_REVENUE − (Material + Package + Production + Copacking)
CONTRIBUTION     = GROSS_PROFIT − LOGISTICS − PROJECT_OPEX      # PROJECT_OPEX = периодические затраты проекта
EBITDA           = CONTRIBUTION − КАиУР − MARKETING             # CA&M и Marketing = % от выручки из Profitability
```

**Расхождения:**
1. В Excel `PROJECT_OPEX` (строка 26 DATA) — это **периодические/дискретные** затраты проекта (например, маркетинговый бюджет запуска, листинговые сборы). В ТЗ это `VARIABLE_OPEX` = % от выручки (TM, CM, Sales). Это разные сущности.
2. `КАиУР` (CA&M = Commercial, Administrative & Management) в Excel = % от выручки из Profitability benchmark, вычитается **на уровне EBITDA**, не Contribution.
3. В ТЗ `SALES_EXPENSES` не соответствует ни одной статье Excel однозначно.

**Маппинг Excel → ТЗ:**

| Excel | ТЗ | Уровень вычета |
|-------|-----|----------------|
| PROJECT_OPEX | VARIABLE_OPEX (частично) | Contribution |
| КАиУР % | AMC_PER_COST | EBITDA |
| Marketing % | MARKETING_COST | EBITDA |

**Реализовать:** структуру Excel как эталон. Переименовать в коде согласно этому маппингу, задокументировать в ADR.

---

## СРЕДНИЕ расхождения (влияют на отдельные KPI)

---

### D-06 — Формула ROI

**ТЗ:**
```
ROI = cumulative_profit / cumulative_investment
```
Простое отношение суммарной прибыли к суммарным инвестициям.

**Excel (DATA, строка 49):**
```
ROI = (−SUM(FCF_range) / (SUMIF(FCF_range, "<0") − 1)) / COUNT(FCF_range)
```
Это аннуализированный показатель: среднегодовая доходность на единицу инвестированного капитала. `−1` в знаменателе защищает от деления на 0 (если все FCF положительные).

Для Y1-Y3: `ROI = −SUM(FCF_0..2) / (|neg_FCF| − 1) / 3`

**Реализовать:** формулу Excel. ТЗ-формулу не использовать — она даёт другие числа.

---

### D-07 — Терминальная стоимость не входит в NPV

**ТЗ:** не специфицирует наличие/отсутствие терминальной стоимости в NPV.

**Excel (DATA, строки 47–48):**
- Строка 47: `Терминальная стоимость` рассчитывается по модели Гордона:
  ```
  TV = FCF_last × (FCF_last / FCF_prev) / (DR − (1 − FCF_last / FCF_prev))
  ```
  где `FCF_last / FCF_prev` — подразумеваемый темп роста FCF.
- Строка 48: `NPV = SUM(Дисконтированные_FCF)` — терминальная стоимость **не включена** в NPV.
- TV — отдельный информационный показатель (используется в экране "Стакан себестоимости").

**Реализовать:**
- NPV = чистая сумма дисконтированных FCF, без TV.
- TV рассчитывать отдельно и отображать как справочный KPI.

---

### D-08 — Механизм применения инфляции к ценам

**ТЗ:** `INFLATION_PROFILE` — годовой профиль (параметр уровня Project). Не специфицирует, как именно применяется внутри года.

**Excel (DASH, строка 30 + Predikt Inflation sheet):**
```
SHELF_PRICE_REG[t] = SHELF_PRICE_REG[t-1] × (1 + MONTHLY_INFLATION[t])
```
- Инфляция — **ступенчатый профиль**: большинство месяцев = 0%, повышение раз или дважды в год.
- Пример профиля `Апрель/Октябрь +7%`: в апреле и октябре цена умножается на 1.07, в остальные месяцы — без изменений.
- Predikt Inflation sheet содержит матрицу профилей × месяцев.

**Следствие:** цена не растёт равномерно — она "прыгает" в конкретные месяцы. Это важно для корректного расчёта взвешенной выручки.

**Реализовать:**
- Inflation хранить как **профиль** (матрица: месяц → коэффициент) в справочнике.
- Каждый месяц: `SHELF_PRICE[t] = SHELF_PRICE[t-1] × (1 + inflation_coeff[profile][month])`.
- Для годовых периодов (Y4–Y10): применять аннуализированный коэффициент профиля.

---

### D-09 — Логистика: единица измерения

**ТЗ (раздел 4.7):** `LOGISTICSCOSTPERLITERS` — ₽/литр.

**Excel (DASH, строка 40):** `Logistic cost (₽/Kg)`.

Для водных напитков (плотность ≈ 1 кг/л) это **практически эквивалентно**. Различие возникнет если в систему добавить продукты с плотностью ≠ 1.

**Реализовать:** хранить как `LOGISTICS_COST_PER_KG` (₽/кг). Для расчёта:
```
LOGISTICS_COST = LOGISTICS_COST_PER_KG × (VOLUME_LITERS × PRODUCT_DENSITY)
```
Где `PRODUCT_DENSITY` = 1.0 для напитков (default). Это даёт совместимость и с будущими продуктами.

---

## НИЗКИЕ расхождения / уточнения

---

### D-10 — ND рамп-ап: логика роста не описана в ТЗ

**ТЗ:** `NDPLAN` — вводимый пользователем показатель за период. Алгоритм Predict-значений не описан.

**Excel (DASH, строка 25):**
- Стартовый месяц: `ND[M1] = ND_target × 20%` (20% от целевого значения)
- Рост: линейная интерполяция от `ND[M1]` до `ND_target` за заданное число месяцев:
  `ND[t] = ND[t-1] + (ND_target − ND[M1]) / ramp_months`
- После рамп-апа: `ND[t] = ND_target`

**Реализовать для слоя Predict:**
- Параметры рамп-апа: `ND_START_PCT = 0.20` (% от target), `ND_RAMP_MONTHS` (число месяцев до выхода на целевой уровень).
- Fine-tuned / Actual приоритетны над Predict — пользователь может переопределить любое значение.

---

### D-13 — Launch lag per (SKU × Channel): Excel хранит launch month per канал, не per SKU

**Статус:** ✅ Исправлено в коммите 34aad4c7c120 (rollback миграция,
2026-04-09). Поля `launch_year/launch_month` живут на
`ProjectSKUChannel`, а не на `ProjectSKU`. Первая итерация (eb8426d)
поместила их на ProjectSKU — это было архитектурно неверно. Quick check
#2 (2026-04-08) показал что Excel хранит launch_year/launch_month
**в DASH per (SKU × Channel)** — TT/E-COM каналы запускаются раньше
HM/SM/MM для одного и того же SKU.

**Доказательство (DASH блок 1, SKU "Gorji Цитрус Газ Пэт 0,5"):**
```
HM              year=2025 month=2  ← Y2 Feb (modern trade)
SM              year=2025 month=2
MM              year=2025 month=2
TT              year=2024 month=11 ← Y1 Nov (раньше HM на 3 мес)
E-COM_OZ        year=2024 month=11
E-COM_OZ_Fresh  year=2024 month=11
```

**Бизнес-логика:** классические каналы (TT, e-com) дают первичную
дистрибуцию для тестирования рынка, modern trade (HM/SM/MM) подключаются
позже после доказательства спроса. **Launch — это свойство ВЫХОДА в
канал, не свойство SKU.**

**История и финальное решение:**
- Коммит eb8426d: `ProjectSKU.launch_year + launch_month` (НЕ ТО МЕСТО)
- Вариант C одобрен пользователем: drop с ProjectSKU, add на
  ProjectSKUChannel
- Реализовано: миграция `34aad4c7c120_rollback_launch_year_month_from_psk_to_`
  drop'нула колонки на PSK и добавила на PSC с тем же `server_default=1`,
  service `_build_line_input` теперь читает `psc.launch_year/month`,
  schemas/types/UI перенесены с PSK на PSC. 207/207 pytest, 0 tsc.

**Контекст:** Discovery V1 для SKU_1/HM показал что наш pipeline на
**per-unit** уровне совпадает с DASH (GP/unit = 14.43 ₽ M1-M3, 13.74
₽ M4-M6 после инфляции), но при попытке пройти полный recalculate
обнаружилось что **total volume / NR / FCF** будут завышены. Причина
ниже.

**Excel поведение:**
- DASH SKU_1 row 25 col D = ND 0.0384 (это **первый месяц жизни SKU**,
  не M1 проекта). Cols D..AT — 43 значения ND ramp **относительно
  launch month** SKU.
- DASH row 8/9 каждого SKU блока = launch_year + launch_month
  (например, SKU_1: launch Y2 Feb = M14 проекта).
- NET REVENUE/RETAIL/VOLUME/etc применяют absolute lag — обнуляют
  периоды M1..M(launch_month−1) и сдвигают DASH cols в правильные
  absolute periods.

**Было в нашей модели до фикса:**
- `ProjectSKU` не имел launch_year/launch_month полей
- `_build_line_input` принимал nd[t]/offtake[t] напрямую из PeriodValue
  без обнуления
- Все SKU считались активными с M1 проекта
- Если SKU реально launches в Y2 Feb, наш pipeline считал бы выручку
  за M1..M13 на основании ramp values из DASH cols D-O, тогда как
  Excel в эти периоды имеет ноль.

**Pipeline-уровневое последствие:** для multi-SKU GORJI reference
(SKU 1-8, launches в Y2 Feb..Y3+), наши NPV/IRR/ROI получились бы
**завышенными** на сумму "выручки до launch периодов".

**Финальная реализация (коммит 34aad4c7c120):**

1. **Schema:**
   - Drop `project_skus.launch_year + launch_month`
   - Add `project_sku_channels.launch_year + launch_month` (Integer,
     NOT NULL, server_default 1)
   - Миграция автогенерирована, проверена upgrade/downgrade up/down

2. **Service layer (`calculation_service._build_line_input`):**
   ```python
   if psc.launch_year > 3:
       launch_period_number = 36 + (psc.launch_year - 3)
   else:
       launch_period_number = (psc.launch_year - 1) * 12 + psc.launch_month
   for i, period in enumerate(sorted_periods):
       if period.period_number < launch_period_number:
           nd_arr[i] = 0.0
           offtake_arr[i] = 0.0
   ```
   Для launch_year ≥ 4 (yearly periods Y4..Y10) launch_month
   игнорируется — yearly periods не имеют месяцев.

3. **Pipeline:** **не изменён**. Pure functions s01..s12 не знают про
   launch lag. Обнуление nd/offtake в service layer достаточно: при
   `volume = active × offtake × seasonality`, если `offtake[t] = 0`
   → `volume[t] = 0` → весь downstream автоматически = 0 на этих
   периодах. Чистое разделение pipeline ↔ business logic.

4. **API/UI:**
   - Удалены 2 поля из `ProjectSKUBase/Update/Read` (Pydantic) и
     `ProjectSKURead/Update/Create` (TS types).
   - Добавлены в `ProjectSKUChannelBase/Update/Read` и
     `ProjectSKUChannelRead/Update/Create`.
   - UI: убраны 2 input'а из `bom-panel.tsx`, добавлены в
     `channel-form.tsx` (используется в `AddChannelDialog` и
     `EditChannelDialog`). `pscToFormState` подхватывает значения.

**Тесты** (3 launch-lag теста переписаны с PSK на PSC):
- `test_launch_lag_zeros_periods_before_launch` → теперь меняет
  `psc.launch_year = 2`
- `test_launch_lag_default_y1m1_no_offset` → без изменений (default)
- `test_launch_lag_yearly_y4` → теперь меняет `psc.launch_year = 4`
207/207 pytest зелёные. tsc 0 ошибок.

**Обратная совместимость:** Existing project_skus.launch_year = 1
(default), значит ничего не теряется при drop колонок (все = default).
existing project_sku_channels.launch_year получают server_default 1
после миграции → backward-compat сохранён.

**Что это означает для GORJI reference (4.2.1):**
Импорт-скрипт после rollback сможет читать DASH **row 8/9 col_base+1**
для каждого канала каждого SKU блока (6 каналов × 8 SKU = 48 значений
launch_year/month) и сохранять per ProjectSKUChannel. Discovery V2
(полный 8 SKU × 6 каналов) даст реалистичные NPV/IRR/ROI учитывая
что каждый канал launches в свой месяц.

**Структура DASH (выяснено в Quick check #2 после первой итерации D-13):**
- Каждый SKU блок занимает 46 rows (rows 6, 52, 98, ..., 328 для 8 SKU)
- Внутри блока — 6 каналов через col_base offset:
  - HM: col_base=2, SM=50, MM=98, TT=146, E-COM_OZ=194, E-COM_OZ_Fresh=242
- Каждый канал занимает 48 cols (label col_base + value cols col_base+1 +
  43 period cols col_base+2..col_base+44)
- Per-channel параметры: launch_year (menu+2), launch_month (menu+3),
  channel margin (menu+21), promo discount (menu+22), promo share (menu+23),
  shelf_price_reg (menu+24), logistic (menu+34)
- Per-channel per-period: nd (row menu+19, cols col_base+2..+44),
  offtake (row menu+20), shelf_price (row menu+24)
- Material/Package cost: row menu+30/31 col_base+2..+44 (per period с инфляцией)
- ProjectSKU rates (production_cost_rate, ca_m_rate, marketing_rate) тоже
  per канал в DASH! (rows menu+32, 35, 36 col_base+2). Нужно проверить —
  возможно одинаковы, но архитектурно могут отличаться

---

### D-12 — Excel typo: NPV/ROI/IRR scope "Y1-Y5" формула включает 6 столбцов

**Статус:** ✅ Подтверждено повторной проверкой через openpyxl 2026-04-08
(перед задачей 2.4). Это **typo автора Excel** в одной формуле, не
дизайн-решение. Подтверждение детально документировано ниже.

#### Точные ячейки и формулы (verified)

`PASSPORT_MODEL_GORJI_2025-09-05.xlsx`, лист `DATA`:

| Ячейка | Label | Формула | Размер диапазона |
|--------|-------|---------|------------------|
| `B48` | NPV Y1-Y3 | `=SUM(B44:D44)` | **3 столбца** (B,C,D) ✓ |
| `C48` | NPV Y1-Y5 | `=SUM(B44:G44)` | **6 столбцов** (B,C,D,E,F,G) ❌ |
| `D48` | NPV Y1-Y10 | `=SUM(B44:K44)` | **10 столбцов** (B..K) ✓ |
| `B49` | ROI Y1-Y3 | `=(-SUM(B43:D43)/(SUMIF(B43:D43,"<0")-1))/COUNT(B43:D43)` | 3 ✓ |
| `C49` | ROI Y1-Y5 | `=(-SUM(B43:G43)/(SUMIF(B43:G43,"<0")-1))/COUNT(B43:G43)` | 6 ❌ |
| `D49` | ROI Y1-Y10 | `=(-SUM(B43:K43)/(SUMIF(B43:K43,"<0")-1))/COUNT(B43:K43)` | 10 ✓ |
| `B50` | IRR Y1-Y3 | `=IRR(B43:D43)` | 3 ✓ |
| `C50` | IRR Y1-Y5 | `=IRR(B43:G43)` | 6 ❌ |
| `D50` | IRR Y1-Y10 | `=IRR(B43:K43)` | 10 ✓ |

#### Структура времени в модели GORJI

`DATA!37` (Year row), формулы из openpyxl:
```
B37 = 0   (calendar 2024 = Y0/setup год)
C37 = 1   (2025 = Launch Year по DASH row 8 col C)
D37 = 2   (2026)
E37 = 3   (2027)
F37 = 4   (2028)
G37 = 5   (2029) ← Y5 в календарных годах
...
K37 = 9   (2033)
```

10 столбцов всего = 10 календарных лет (2024-2033). Launch Year = 2025
(2025-2033 = 9 операционных лет + 1 setup год).

#### Анализ pattern

Pattern формул NPV/ROI/IRR должен быть **последовательным**: количество
столбцов в `B:X` = число лет в label scope.

| Scope | Ожидание (по pattern Y3, Y10) | Excel формула | Расхождение |
|-------|-------------------------------|---------------|-------------|
| Y1-Y3 | 3 столбца (`B:D`) | `B:D` ✓ | нет |
| Y1-Y5 | 5 столбцов (`B:F`) | `B:G` ❌ | **+1 столбец** |
| Y1-Y10 | 10 столбцов (`B:K`) | `B:K` ✓ | нет |

Альтернативные интерпретации (все провалены):
- *"Y1-Y5 = 5 операционных + setup = 6 cols"*: тогда Y1-Y3 должно было быть
  3+1=4 cols (`B:E`), но Excel `B:D` = 3.
- *"Y_n использует exactly n calendar years начиная с Y0"*: тогда Y1-Y5
  должно быть `B:F` = 5 cols, но Excel `B:G` = 6.
- *"Y_n использует n+1 cols (включая Y0)"*: тогда Y1-Y3 = 4 cols, Y1-Y10 =
  11 cols. Не работает.

**Вывод:** Excel формулы Y3 и Y10 консистентны (`n` cols для `Y1-Yn`).
Формулы для Y5 нарушают этот pattern на +1 столбец. Это **typo автора
Excel в одной формуле NPV** (NPV row 48 col C), которая была скопирована
в формулы ROI и IRR той же колонки (rows 49, 50).

#### Решение для реализации

По ADR-CE-01 (Excel = источник истины) реализуем как в Excel — 6 элементов
для scope Y1-Y5. Цифры в KPI sheet GORJI, презентациях и бизнес-документации
рассчитаны и отражают именно 6-элементный диапазон. Если мы изменим — наши
acceptance тесты разойдутся с эталоном Excel, что нарушит правило "источник
истины".

Зафиксировано в `backend/app/engine/steps/s11_kpi.py`:
```python
SCOPE_BOUNDS = {
    "y1y3":  (3,  3),
    "y1y5":  (6,  5),    # ← D-12: Excel typo, slice 6 элементов, threshold 5 лет
    "y1y10": (10, 10),
}
```

Если позже бизнес явно скажет "это была опечатка, исправить" — правка
в одной строке `SCOPE_BOUNDS` (`(6, 5) → (5, 5)`). Все KPI (NPV/IRR/ROI/payback)
для scope Y1-Y5 при этом изменятся, и acceptance тесты придётся обновить
(реалистично — пересчитать через openpyxl на скорректированных формулах).

#### Численная разница для GORJI

| Вариант | NPV Y1-Y5 | IRR Y1-Y5 | ROI Y1-Y5 |
|---------|-----------|-----------|-----------|
| Excel as-is (6 cols) | 27 251 350 ₽ | 64.12% | 67.40% |
| Если исправить (5 cols) | 13 591 449 ₽ | ≈47% | ≈72% |
| Разница | -50% | -17pp | +5pp |

Расхождение значительное — для бизнес-решения "Y5 vs Y3" критично.

---

### D-11 — Offtake рамп-ап: аналогично ND

**Excel (DASH, строка 26):** стартовый offtake = `OFFTAKE_target × 20%`, аналогичная интерполяция.

**Реализовать:** `OFFTAKE_START_PCT = 0.20` по умолчанию. Параметр уровня ProjectSKUChannel.

---

## Расхождения, обнаруженные в Discovery V2 (4.2.1, 2026-04-09)

Discovery V2 — полный GORJI импорт через `scripts/import_gorji_full.py`
обнаружил **6 расхождений** между Excel и нашим pipeline. Per-line acceptance
(test_gorji_reference) проверял только M1-M6 per-unit GP/CM — не покрывал
yearly periods и absolute aggregates. Из-за этого Discovery V1 (только SKU 1
HM, per-unit) дал точное совпадение, но full GORJI выявил систематические
проблемы.

---

### D-14 — Yearly volume × 12 multiplier (✅ исправлено)

**Статус:** ✅ Исправлено в коммите [s01_volume × 12 fix]
(2026-04-09).

**Проблема:** `s01_volume.step()` для yearly periods (Y4..Y10) считал
`volume_units = active × offtake × seasonality` без множителя × 12.
Excel в DASH yearly cols (AN..AT) хранит **monthly average** offtake,
а в листах VOLUME / NET REVENUE применяет годовой aggregate (× 12).
Это давало 12-кратное занижение нашего volume_units для yearly periods,
и катастрофически отрицательный NPV в полном GORJI импорте (Y1Y10 = -34M
против эталона +80M).

**Доказательство:**
- DASH SKU 1 HM offtake col M36 (col 39) = 16.8 (monthly)
- DASH SKU 1 HM offtake col Y4 (col 40) = 17.0625 (monthly average)
- ratio Y4/M36 = 1.016 (только годовой рост, **не × 12**)
- Excel VOLUME лист SKU 1 HM Y4 col 47 = **13,127 литров** (annual)
- VOLUME M36 col 46 = **949 литров** (monthly)
- ratio = 13.83 ≈ 14 (× 12 + рост)

**Реализация:**
```python
# s01_volume.py
period_units = 1.0 if inp.period_is_monthly[t] else 12.0
vol_u = active * inp.offtake[t] * inp.seasonality[t] * period_units
```

После fix volume_units Y4 для project = 3,694,359 = exactly Excel
DATA r15 col E. test_gorji_reference (per-unit M1-M6) не сломан.

**Тесты:** 207/207 зелёные после fix.

---

### D-15 — DASH относительная ось (relative-to-launch month канала)

**Статус:** Обнаружено 2026-04-09. Исправляется в импорт-скрипте через shift.

**Проблема:** DASH cols D..AT для каждой (SKU × Channel) комбинации
хранят значения **относительно launch month канала**, не absolute periods
проекта. Excel в листах NET REVENUE / VOLUME / RETAIL **сдвигает** DASH
cols в absolute periods через формулы.

**Доказательство:**
- SKU 1 HM launch = 2025-02 (Y2 Feb = M14 absolute)
- DASH col D (M1 канала) ND = 0.0384 (start ramp value)
- NET REVENUE row 2 (SKU 1 HM) col K (M1 absolute = 2024-01) NR = **0**
- Volume_M1 absolute = 0 (нет продаж в pre-launch period)
- Если бы DASH absolute, ND_M1 × offtake_M1 × shelf_M1 = NR > 0
- Но NR_M1 = 0 → DASH cells **относительные**

**Маппинг:**
- DASH col 4 (M1 канала) → absolute period N (где N = launch_period_number)
- DASH col 5 (M2 канала) → absolute period N+1
- DASH col 39 (M36 канала) → absolute period N+35
- DASH col 40..46 (Y4..Y10 канала) → absolute period N+36..N+42

Если N + 42 > 43 (за horizon проекта), последние DASH cols игнорируются.

**Реализация:** в `scripts/import_gorji_full.py` при копировании DASH
cols в PeriodValue применять shift по launch_period_number. Periods до
launch остаются 0 (предусмотрено существующим launch lag механизмом D-13).

**Pipeline не изменяется** — обнуление до launch period делает уже
существующий механизм D-13 в `calculation_service._build_line_input`.

---

### D-16 — Material/Package per-period custom inflation в DASH

**Статус:** Обнаружено 2026-04-09. Требует расширения pipeline для приёма
per-period BOM значений из БД.

**Проблема:** Excel хранит material и package cost per period в DASH
rows 36/37 cols D..AT с **custom inflation logic**, которая **НЕ
соответствует** ни одному стандартному профилю инфляции из seed.

**Доказательство (SKU 1 HM material row 36):**
```
M1 = 3.6994        (база)
M4 +7% = 3.958     (Apr 2024 — стандартно)
M10 +7% = 4.235    (Oct 2024 — стандартно)
M16 +7% = 4.532    (Apr 2025 — стандартно)
M17 ×0.7876 = 3.569   ❌ (-21%, нестандартный reset!)
M22 +7% = 3.819
M28 +7% = 4.087
M34 +7% = 4.373
Y4..Y10 ×1.0712 каждый
```

Аномалия в M17 (× 0.7876) — это **бизнес-логика Excel** (возможно
переход на нового поставщика, переоценка, или замена formula). Не может
быть воспроизведена через generic `inflate_series` в pipeline.

**Реализация:**
1. Импорт-скрипт **читает per-period material+package values напрямую
   из DASH** (rows 36/37 cols 4..46 после shift D-15)
2. Сохраняет их в `PeriodValue.values["bom_unit_cost"]` per period
3. `calculation_service._build_line_input` использует эти values если
   они есть в effective values, иначе fallback на `inflate_series` от
   BOMItem (для проектов где Excel custom logic не применяется)
4. BOMItem остаётся в импорте для сохранения "базового" значения M1 — но
   pipeline его игнорирует если в PeriodValue есть bom_unit_cost

**Это архитектурное изменение pipeline** — расширение PipelineInput
семантики (bom_unit_cost берётся из эффективных PeriodValues, не только
из BOMItem). Согласовано с пользователем 2026-04-09.

---

### D-17 — Shelf price per-period custom inflation в DASH

**Статус:** Обнаружено 2026-04-09. **Уже работает** через существующий
механизм PeriodValue.values["shelf_price"]. Требует только D-15 shift.

**Проблема:** Excel хранит shelf price per period в DASH row 30 с
**custom inflation logic** — первый год константа, потом +7% Apr/Oct.

**Доказательство (SKU 1 HM shelf_price row 30):**
```
M1..M27 absolute = 74.99   (константа в Y0, Y1, Y2 — никакой инфляции)
M28 +7% = 80.24            (первый Apr inflation в Y3)
M34 +7% = 85.86            (Oct Y3)
Y4..Y10 ×1.0712 каждый
```

Это противоречит профилю "Апрель/Октябрь +7%" из seed (который
применяет +7% **с первого Apr**, M4 absolute).

Для SKU 1 HM (launch = M14 absolute) первая Apr inflation в shelf
происходит в M28 = relative M15 канала (Apr второго года канала).
Excel применяет shelf inflation **со второго года канала**, не с
первого.

**Реализация:** Pipeline **уже** использует `PeriodValue.values["shelf_price"]`
напрямую (см. `calculation_service._build_line_input:241`). Не нужно
ничего менять в pipeline. Достаточно чтобы **импорт** копировал DASH
shelf values per period (после shift D-15) в PeriodValue.

**После D-15 shift D-17 решается автоматически.**

---

### D-18 — Logistics per-period inflation в pipeline

**Статус:** Обнаружено 2026-04-09. Требует расширения PipelineInput.

**Проблема:** Excel хранит logistics_cost_per_kg per period в DASH row
40 с inflation. Наш `PipelineInput.logistics_cost_per_kg` — `float`
константа, применяется одинаково на все 43 периода в `s07_logistics_cost`.

**Доказательство (SKU 1 HM logistics row 40):**
```
M1..M3 = 8.00      (база)
M4..M9 = 8.56      (Apr 2024 +7%)
...
```

При константе 8.00 на все periods и Excel инфлирующем к ~14.69 в Y10,
наш logistics в Y10 на ~45% меньше Excel.

**Реализация:**
1. `PipelineInput.logistics_cost_per_kg`: `float → tuple[float, ...]`
2. `s07_logistics_cost.step()`: `logistics[t] = logistics_per_kg[t] × volume_kg[t]`
3. `_build_line_input`: формирует tuple через одно из:
   - per-period values из `PeriodValue.values["logistic_per_kg"]` (если есть)
   - `inflate_series` от `psc.logistics_cost_per_kg` (M1 базовое) с
     project inflation profile (для проектов где Excel custom logic
     не применяется)

**Это архитектурное изменение pipeline** — расширение PipelineInput.
Аналогично D-16, согласовано с пользователем 2026-04-09.

---

### D-19 — Per-period production_cost_rate (revised)

**Статус:** ✅ Исправлено финально 2026-04-09. Расширение pipeline.

**Проблема (углублённая после Y1Y3 investigation):** Excel хранит
`production_cost_rate` **per period** в DASH row 38 cols D..AT. Для
SKU 1 HM rate = 0.0778 в M1..M16 и M25..Y10, но **0 в M17..M24** —
**copacking window** (own production downtime). Для SKU 7-8 rate = 0
до M24, потом 0.08 от M25.

Наш `PipelineInput.production_cost_rate` был `float` константа,
прочитанный один раз из M1 col HM. Эффект:
- SKU 1-6: применяли 0.0778 в periods M17-M24 (где Excel = 0) → переплата
- SKU 7-8: применяли 0 на все periods (где Excel = 0.08 от M25) → недоплата
- Net эффект: Y2 production у нас 2.94M vs Excel 0.246M (наш в 12x больше),
  Y3-Y10 production у нас стабильно -10% от Excel

**Доказательство (DASH SKU 1 HM row 38):**
```
M1..M16  = 0.0778  (own production)
M17..M24 = 0       (copacking window — внешнее производство)
M25..Y10 = 0.0778  (own production resumed)
```

**Реализация:**
1. `PipelineInput.production_cost_rate`: `float → tuple[float, ...]`
2. `s03_cogs.step()`: использует `inp.production_cost_rate[t]` per period
3. `_build_line_input` читает из `PeriodValue.values["production_cost_rate"]`,
   fallback на `psk.production_cost_rate` scalar
4. Импорт-скрипт читает DASH row 38 cells per период per канал и пишет
   в `PeriodValue.values`. Static `psk.production_cost_rate` = max из ряда
   (для UI/fallback)
5. Тестовый helper `make_input` обновлён — scalar/tuple конвертация
6. test_gorji_reference обновлён на tuple

**Эффект на NPV:**
- До D-19 (revised): Y1Y10 NPV = 79.43M (drift -0.7%, но Y3-Y10 production
  understated)
- После D-19 (revised): Y3-Y10 production = exactly Excel
- Y3 GP exact match: 42,380,591 vs Excel 42,380,597
- Y10 GP exact match: 146,504,177 vs Excel 146,504,177

---

### D-22 — Working Capital на годовом уровне (Excel D-01)

**Статус:** ✅ Исправлено финально 2026-04-09. Refactor s10_discount.

**Проблема (КРИТИЧЕСКАЯ для Y1Y3):** Excel формула WC[year] = annual_NR[year]
× wc_rate. Наш `s07_working_capital` использует ту же формулу, но **на
per-period основе**: WC[t] = NR[t] × wc_rate. Для monthly periods это
даёт 1/12 от annual scale.

Sum of monthly ΔWC ≠ annual ΔWC, потому что:
- Monthly ΔWC[t] = WC[t-1] - WC[t] = (NR[t-1] - NR[t]) × wc_rate (monthly NR diff)
- Annual ΔWC[year] = WC[year-1] - WC[year] = (NR[year-1] - NR[year]) × wc_rate
  (annual NR diff = sum_monthly_NR_prev - sum_monthly_NR_curr)

Эти **несопоставимы по scale** (annual ≈ 12x monthly).

**Доказательство (Excel DATA r38 WC vs r18 NR):**
```
Y0: WC=30,892   / NR=257,429    = 0.1200 ✓
Y1: WC=4,669,923 / NR=38,916,021 = 0.1200 ✓
...
Y10: WC=41,801,843 / NR=348,348,693 = 0.1200 ✓
```

Все ratios = 0.12. Excel WC = annual_NR × wc_rate ровно.

**Эффект до fix:** Y1Y3 NPV drift +43-55% (большая часть из-за неправильного
WC/Tax/OCF/FCF на annual level). После fix → drift **−0.00%** (exact match).

**Реализация:** В `s10_discount.step()`, после аннуализации NR/CM, **пересчитываем**
annual WC/ΔWC/Tax/OCF/FCF на годовом уровне:

```python
# D-22: Annual WC/ΔWC/Tax/OCF/FCF (Excel D-01 formula)
annual_wc = [nr * wc_rate for nr in annual_nr]
annual_delta_wc = []
for i, wc in enumerate(annual_wc):
    prev_wc = annual_wc[i - 1] if i > 0 else 0.0
    annual_delta_wc.append(prev_wc - wc)  # WC[t-1] - WC[t]
annual_tax = [-(cm * tax_rate) if cm > 0 else 0.0 for cm in annual_cm]
annual_ocf = [annual_cm[i] + annual_delta_wc[i] + annual_tax[i] for i in range(N)]
annual_fcf = [annual_ocf[i] - annual_capex[i] for i in range(N)]
```

`annual_capex` собирается из `ctx.investing_cash_flow` (sum по году = -CAPEX).

**Per-period s07/s08/s09 НЕ удалены** — они продолжают работать для
intermediate values (debugging, UI). Но финальные annual values для KPI
вычисляются в s10 на годовом уровне.

**Тесты обновлены:** `test_steps_10_12.py:_build_gorji_ctx` теперь передаёт
`investing_cash_flow = [-x for x in GORJI_ANNUAL_CAPEX]`. `test_monthly_periods_aggregated_into_yearly`
обновлён с явными вычислениями WC/ΔWC/Tax/OCF/FCF expectations.

**Эффект на NPV (финальный):**

| Scope | Excel | Наш | Drift |
|---|---|---|---|
| **NPV Y1Y3** | -11,593,312 | -11,593,314 | **-0.00%** |
| **NPV Y1Y5** | 27,251,350 | 27,278,267 | **+0.10%** |
| **NPV Y1Y10** | 79,983,059 | 80,009,976 | **+0.03%** |
| **IRR Y1Y3** | -60.97% | -60.97% | **+0.00%** |
| **IRR Y1Y5** | 64.12% | 64.16% | **+0.06%** |
| **IRR Y1Y10** | 78.63% | 78.66% | **+0.04%** |
| **ROI Y1Y10** | 158.26% | 158.29% | **+0.02%** |
| Payback simple | 3/3/3 | 3/3/3 | exact |
| Payback discounted | НЕ ОК/4/4 | НЕ ОК/4/4 | exact |

**Pipeline = Excel parity достигнут.**

---

### D-20 — Per-period channel_margin / promo_discount / promo_share

**Статус:** ✅ Исправлено в той же сессии 2026-04-09. Расширение pipeline.

**Проблема:** Excel хранит channel_margin / promo_discount / promo_share
**per period** в DASH (rows offset 21/22/23 × 43 cols D..AT). GORJI снижает
**promo_share с 1.0 (M1..M27) до 0.8 (Y4..Y10)** для всех каналов, что
влияет на ex_factory price на 6-8% в зрелые годы.

**Доказательство (SKU 1 HM promo_share row 29):**
```
M1..M27 = 1.0      (100% promo, ramp-up phase)
M27..M36 = ?
Y4..Y10 = 0.8      (80% promo, mature phase)
```

В нашей model промо_share был **scalar**, читался один раз из M1 col
(= 1.0). Pipeline применял 1.0 для всех periods, что давало больший
discount → меньший ex_factory → меньший NR (расхождение -6% vs Excel).

**Реализация:**
1. `PipelineInput.channel_margin/promo_discount/promo_share`:
   `float → tuple[float, ...]` (длины period_count)
2. `s02_price.step()`: использует per-period values per t
3. `_build_line_input` читает из effective values:
   `vals.get("channel_margin", static_cm)`. Fallback на PSC scalar если
   PeriodValue не содержит ключа.
4. Импорт-скрипт читает per-period значения из DASH rows offset 21/22/23
   для каждой (SKU × Channel) × 43 col и пишет в `PeriodValue.values`
5. Тестовый helper `make_input` обновлён — принимает scalar или tuple
6. Tests `test_calculation.py` проверяют tuple вместо scalar

**Эффект на NPV полного GORJI импорта:**
- До D-20: Y1Y10 NPV = 59.14M (drift -26%)
- После D-20: Y1Y10 NPV = 85.27M (drift +6.61%)
- **Volume и NR теперь точно совпадают с Excel**

---

### D-21 — Copacking launch costs (Y1=2025 only)

**Статус:** ✅ Исправлено в той же сессии 2026-04-09. Импорт-only fix.

**Проблема:** Excel DATA r22 "Копакинг, ₽" показывает:
- Y0 (2024) = 0
- **Y1 (2025) = 6,958,489** ← single year, launch year
- Y2..Y9 = 0

Excel применяет copacking как **одноразовую launch затрату** в год запуска
(собственное производство ещё не готово, продукт co-packed внешним
производителем). После Y2 переход на own production → copacking = 0.

В нашей модели `PipelineInput.copacking_per_unit` = 0 константа. Pipeline
никогда не применяет copacking.

**Реализация:** В импорт-скрипте `extract_project_capex_opex()`:
- Читаем DATA r22 (copacking) для каждого года
- Добавляем к OPEX того же года (effect на Contribution = effect на GP
  в Excel; FCF результат идентичен)

```python
copacking = _float(data.cell(DATA_ROW_COPACKING, excel_col).value)
opex += copacking
```

**Эффект на NPV:**
- До D-21: Y1Y10 NPV = 85.27M (drift +6.61% — overshoot)
- После D-21: Y1Y10 NPV = **79.43M (drift -0.70%)** — almost exact match
- IRR Y1Y10: было 99.5% → стало **80.0%** (Excel 78.6%, +1.73%)
- NPV Y1Y5: drift -4.77% (within 5%)

**Это финальный fix для Y1Y10 parity с GORJI Excel.** Y1Y3 drift всё ещё
+43% (наш -6.57M vs Excel -11.59M, абс. gap ~5M в early launch periods),
но в долгосрочном NPV не критично.

---

# D-24: Loss carryforward (4.1 engine audit, ст.283 НК РФ)

**Опциональное поведение. Default False сохраняет Excel-compat.**

## Excel-реализация

`tax[t] = −CM[t] × tax_rate`, если `CM[t] > 0`, иначе 0 (D-03).
Нет переноса убытков прошлых лет — убыточный Y1 не уменьшает tax Y3.

## Наша реализация (после 4.1)

Новое поле `Project.tax_loss_carryforward: bool`, default `False`.
Когда `True`:
```python
cumulative_loss = 0.0
for cm in annual_cm:
    if cm < 0:
        tax = 0; cumulative_loss += |cm|
    else:
        usable = min(cumulative_loss, 0.5 × cm)  # cap 50% (ст.283 НК РФ)
        tax = −(cm − usable) × tax_rate
        cumulative_loss −= usable
```

## Эффект

Для пусковых FMCG-проектов с убыточными Y0-Y2 налог в Y3-Y5
уменьшается на 10-20% → NPV выше. Тестовый пример:
- CM = [-100, -50, +200, +200], rate = 0.20
- Default tax = [0, 0, -40, -40], total -80
- С carryforward tax = [0, 0, -20, -30], total -50 (экономия 30)

## Обоснование opt-in (а не default on)

GORJI acceptance эталон и 8 engine unit-тестов рассчитаны под Excel
формулу. Включение carryforward default сломало бы baseline (NPV drift
~3-5%). User сам выбирает: для gate-review приближение к реальности,
для compare-с-Excel — default off.

## UI

Checkbox в настройках проекта: "Применять перенос налоговых убытков
(ст.283 НК РФ)". HelpButton объясняет бизнес-смысл.

---

# D-23: Дробный Payback (4.4 engine audit)

**Наша реализация точнее Excel — сознательный upgrade.**

## Excel-реализация

Row 51/52 в Excel-модели:
```
=COUNTIF(cumulative_range, "<0")
```
Возвращает **целое число** — сколько лет cumulative FCF/DCF было отрицательным.
Например: если cumulative отрицателен в Y1, Y2, Y3, и положителен в Y4 → payback=3.

## Наша реализация (после 4.4)

Линейная интерполяция в пределах года выхода в плюс:
```python
# i — индекс первого года где cumulative >= 0
# fraction = |cumulative[i-1]| / fcf[i]
payback_years = i + fraction
```

Пример: cumulative[2]=-30 (Y3 концовка), cumulative[3]=+50 (Y4 концовка),
fcf[3]=+80 → fraction = 30/80 = 0.375. Payback = 3 + 0.375 = **3.375 лет**
(вместо Excel 3). Более точная метрика для Gate-reviews.

## GORJI эталон (после 4.4)

| Scope | Excel integer | Наш float | Отличие |
|-------|---------------|-----------|---------|
| Simple Y1-Y3   | 3     | None (4.6 > 3 threshold)    | Был 3 (ошибка Excel: threshold игнорировался) |
| Simple Y1-Y5   | 3     | 3.606 лет                    | +0.6 года точности |
| Simple Y1-Y10  | 3     | 3.606 лет                    | +0.6 года точности |
| Discounted Y1-Y3   | None | None                      | совпадает |
| Discounted Y1-Y5   | 4    | 4.003 лет                    | +0.003 года точности |
| Discounted Y1-Y10  | 4    | 4.003 лет                    | +0.003 года точности |

## Обоснование

- **Бизнес-смысл:** Gate review "payback 3.6 vs 4 лет" — разница 6 месяцев,
  что материально для сравнения проектов (порог 3 vs 4 лет определяет
  Go/No-Go).
- **ДБ изменение:** Numeric(8,4) уже был (для discounted payback) — изменение
  типа возвращаемого значения совместимо.
- **Acceptance:** GORJI эталон пересчитан, drift NPV Y1-Y10 остаётся 0.03%.

Если бизнес скажет "вернуть integer" — правка в одной функции
`_scope_payback` в `backend/app/engine/steps/s11_kpi.py`.

---

## Верифицированные совпадения (ТЗ ≡ Excel)

Следующие формулы ТЗ проверены против Excel и **расхождений нет**:

| Формула | ТЗ | Excel | Статус |
|---------|-----|-------|--------|
| Shelf Price Promo | `SHELF_REG × (1 − PROMO_DISCOUNT)` | `D30×(1−D28)` | ✓ |
| Shelf Price Weighted | `REG×(1−PS) + PROMO×PS` | `D30×(1−D29)+D31×D29` | ✓ |
| Volume Units | `ACTIVE_OUTLETS × OFFTAKE × SEASONALITY` | VOLUME sheet | ✓ |
| Net Revenue | `VOLUME_UNITS × EX_FACTORY_PRICE` | DASH×VOLUME | ✓ |
| Gross Profit | `NET_REVENUE − COGS_TOTAL` | DATA row 23 | ✓ |
| FCF | `OCF + ICF` | DATA row 43 | ✓ |
| Discounted CF | `FCF / (1 + DR)^year` | DATA row 44 | ✓ |
| IRR | `IRR(FCF_range)` | DATA row 50 | ✓ |
| Payback | первый период где cumFCF ≥ 0 | DATA rows 54–57 | ✓ |
| Go/No-Go | NPV≥0 AND CM≥25% | KPI sheet | ✓ |
| Seasonality | только M1–M36, Y4–Y10 без | Predikt + DASH | ✓ |

---

## Итоговая таблица параметров с уточнёнными значениями

| Параметр | Уровень | Default | Источник |
|----------|---------|---------|---------|
| `WC_RATE` | Project | 0.12 | Excel DATA row 38 |
| `TAX_RATE` | Project | 0.20 | Excel DATA row 40 |
| `DISCOUNT_RATE` (WACC) | Project | 0.19 | Excel DASH C3 |
| `VAT_RATE` | Project (или справочник) | 0.20 | Excel DASH C22 |
| `PRODUCTION_COST_RATE` | ProjectSKU | из Profitability | Excel DASH row 38 |
| `CA_M_RATE` | ProjectSKUChannel | из Profitability | Profitability row 80 |
| `MARKETING_RATE` | ProjectSKUChannel | из Profitability | Profitability row 86 |
| `ND_START_PCT` | ProjectSKUChannel | 0.20 | Excel DASH row 25 |
| `OFFTAKE_START_PCT` | ProjectSKUChannel | 0.20 | Excel DASH row 26 |
| `LOGISTICS_COST_PER_KG` | ProjectSKUChannel | из Profitability | LOGISTIC COST sheet |

---

## Что делать дальше

1. Этот документ — основа для имплементации расчётного ядра.
2. Перед написанием любой формулы — ссылаться на раздел этого документа.
3. Если обнаружится новое расхождение в процессе реализации — добавить как D-12+.
4. Финальная верификация: после реализации прогнать тест с входными данными GORJI+ и сравнить результаты с эталонными значениями из KPI-листа (NPV, IRR, ROI, Payback).
