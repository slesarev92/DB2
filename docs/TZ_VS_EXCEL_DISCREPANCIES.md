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

**Статус:** Первая итерация фикса (eb8426d) поместила `launch_year/month`
на `ProjectSKU` — **архитектурно неверно**. Quick check #2 (2026-04-08)
обнаружил что Excel хранит launch_year/launch_month **в DASH per
(SKU × Channel)** — TT/E-COM каналы запускаются раньше HM/SM/MM
для одного и того же SKU.

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

**Текущий статус (требуется фикс):**
- Коммит eb8426d: `ProjectSKU.launch_year + launch_month` (НЕ ТО МЕСТО)
- Решение C принято пользователем: drop с ProjectSKU, add на
  ProjectSKUChannel
- Сделано в новой сессии после context handoff

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

**Решение (план — будет реализовано в новой сессии):**

1. **Schema rollback + перенос:**
   - Drop `project_skus.launch_year + launch_month`
   - Add `project_sku_channels.launch_year + launch_month` (Integer, NOT NULL,
     server_default 1)
   - Новая миграция (или rollback eb8426d + новая)

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

4. **API/UI:** перенести 2 поля из `bom-panel.tsx` (где они сейчас
   через `ProjectSKUUpdate`) в `channel-form.tsx` (через
   `ProjectSKUChannelUpdate`). Удалить из ProjectSKU schemas.

**Тесты** (3 теста уже написаны под PSK — нужно переписать на PSC):
- `test_launch_lag_zeros_periods_before_launch`
- `test_launch_lag_default_y1m1_no_offset`
- `test_launch_lag_yearly_y4`
Все три используют `psk.launch_year = 2` — поменять на `psc.launch_year = 2`.

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
