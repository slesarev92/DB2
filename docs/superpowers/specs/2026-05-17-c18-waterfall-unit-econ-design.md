# C #18 — Waterfall в Unit-эконмике (design)

> **Brainstorm session:** 2026-05-17 (compressed)
> **Источник:** MEMO 1.4 / Block 6.3 / BL-#18.
> **Scope:** Frontend-only. Waterfall recharts component + integration в `value-chain-tab`. Backend данные уже есть в `ValueChainCell`.

---

## §1. Цель

Дать визуальный waterfall (каскадный) chart для unit-эконмики на выбранной паре `(SKU, Channel)`. Показывает как из shelf price вычитается всё (VAT → channel margin → COGS → logistics → CA&M → marketing) до EBITDA.

### §1.1 User story

«Я смотрю стакан в табличном виде — циферки. Хочу диаграмму чтоб видеть какие статьи 'съедают' больше всего. Должно быть похоже на классический P&L waterfall».

---

## §2. Out of scope

| Что | Почему |
|---|---|
| Waterfall на агрегированный (sum по всем SKU × channel) P&L | Это #15 P&L pivot — отдельный эпик. |
| Drill-down (click ступеньку → детали) | YAGNI. |
| Export waterfall в PPTX/PDF | Отдельная задача если попросят. |
| Per-period waterfall (12 месяцев) | Per-unit стационарный (Y1 base). |
| Custom цвета зон CM / EBITDA per MEMO 6.3 | Минимум: положительные/отрицательные/итоговые. |

---

## §3. Текущее состояние

`frontend/components/projects/value-chain-tab.tsx` рендерит таблицу `ValueChainCell` per SKU × Channel. Данные: shelf_price_reg, shelf_price_weighted, ex_factory, cogs_material, cogs_production, cogs_total, gross_profit, logistics, contribution, ca_m, marketing, ebitda + margins.

Recharts уже используется (tornado, gantt). Pattern для waterfall — `ComposedChart` или `BarChart` с invisible `base` для positioning.

---

## §4. Дизайн

### §4.1 WaterfallChart component

```typescript
// frontend/components/projects/waterfall-chart.tsx
"use client";

import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ReferenceLine,
} from "recharts";

interface WaterfallStep {
  /** Имя ступеньки. */
  name: string;
  /** Дельта: положительная (доход/start) или отрицательная (расход). */
  delta: number;
  /** Если true — это итоговая ступенька (total bar от 0 до running, синий). */
  isTotal?: boolean;
}

interface WaterfallChartProps {
  steps: WaterfallStep[];
  /** Подпись оси Y, например "₽/л". */
  unit?: string;
  /** Высота. */
  height?: number;
}

export function WaterfallChart({ steps, unit = "₽", height = 400 }: WaterfallChartProps) {
  // Compute baseline + visible for each bar
  let running = 0;
  const chartData = steps.map((step) => {
    if (step.isTotal) {
      // Total: bar from 0 to running, full visible
      return { name: step.name, base: 0, value: running, total: true, delta: 0 };
    }
    const start = running;
    const end = running + step.delta;
    running = end;
    if (step.delta >= 0) {
      // Positive: bar from start to end (base=start, value=delta)
      return { name: step.name, base: start, value: step.delta, total: false, delta: step.delta };
    } else {
      // Negative: bar from end to start (base=end, value=|delta|)
      return { name: step.name, base: end, value: Math.abs(step.delta), total: false, delta: step.delta };
    }
  });

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={chartData} margin={{ top: 10, right: 10, left: 10, bottom: 60 }}>
        <XAxis dataKey="name" angle={-30} textAnchor="end" interval={0} height={80} tick={{ fontSize: 11 }} />
        <YAxis tickFormatter={(v: number) => `${v.toFixed(1)} ${unit}`} />
        <Tooltip
          formatter={(_, _name, props) => {
            const d = props.payload;
            if (d.total) return [`${d.value.toFixed(2)} ${unit}`, "Итого"];
            const sign = d.delta >= 0 ? "+" : "−";
            return [`${sign}${Math.abs(d.delta).toFixed(2)} ${unit}`, ""];
          }}
        />
        <ReferenceLine y={0} stroke="#666" />
        {/* Invisible base */}
        <Bar dataKey="base" stackId="a" fill="transparent" />
        {/* Visible value */}
        <Bar dataKey="value" stackId="a">
          {chartData.map((entry, i) => {
            const color = entry.total ? "#3b82f6" : entry.delta >= 0 ? "#22c55e" : "#ef4444";
            return <Cell key={i} fill={color} />;
          })}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
```

### §4.2 Integration в value-chain-tab.tsx

Добавить:
1. State: `selectedSkuIdx` и `selectedChannelIdx` для выбора пары.
2. New CollapsibleSection «Waterfall: разбивка unit-экономики» перед существующей таблицей.
3. Внутри — selectors (SKU + Channel) + WaterfallChart.

12 steps из ValueChainCell:
```typescript
function buildWaterfallSteps(cell: ValueChainCell, vatRate: number): WaterfallStep[] {
  const shelfReg = Number(cell.shelf_price_reg);
  const shelfWeighted = Number(cell.shelf_price_weighted);
  const exFactory = Number(cell.ex_factory);
  const cogsMat = Number(cell.cogs_material);
  const cogsProd = Number(cell.cogs_production);
  const gp = Number(cell.gross_profit);
  const logistics = Number(cell.logistics);
  const cm = Number(cell.contribution);
  const caM = Number(cell.ca_m);
  const marketing = Number(cell.marketing);
  const ebitda = Number(cell.ebitda);

  // VAT = shelf_weighted - shelf_weighted/(1+vat) (with promo discount adjustment)
  // Channel margin = shelf_weighted/(1+vat) - ex_factory
  const promoLoss = shelfReg - shelfWeighted;
  const shelfExclVat = shelfWeighted / (1 + vatRate);
  const vatAmount = shelfWeighted - shelfExclVat;
  const channelMargin = shelfExclVat - exFactory;

  return [
    { name: "Цена полки", delta: shelfReg },
    { name: "Промо", delta: -promoLoss },
    { name: "НДС", delta: -vatAmount },
    { name: "Маржа канала", delta: -channelMargin },
    { name: "Ex-factory", isTotal: true, delta: 0 },
    { name: "COGS сырьё", delta: -cogsMat },
    { name: "COGS произв.", delta: -cogsProd },
    { name: "Gross Profit", isTotal: true, delta: 0 },
    { name: "Логистика", delta: -logistics },
    { name: "Contribution", isTotal: true, delta: 0 },
    { name: "CA&M", delta: -caM },
    { name: "Маркетинг", delta: -marketing },
    { name: "EBITDA", isTotal: true, delta: 0 },
  ];
}
```

Selectors:
```tsx
<Select value={String(selectedSkuIdx)} onValueChange={...}>
  {data.skus.map((sku, i) => <SelectItem value={String(i)}>{sku.sku_brand} / {sku.sku_name}</SelectItem>)}
</Select>
<Select value={String(selectedChannelIdx)} onValueChange={...}>
  {selectedSku.channels.map((ch, i) => <SelectItem value={String(i)}>{ch.channel_code} — {ch.channel_name}</SelectItem>)}
</Select>
```

Empty/loading states.

### §4.3 Tests

Только tsc clean. Manual visual smoke рекомендован, но не блокирующий.

---

## §5. Plan skeleton (2 задачи)

| # | Задача | Файлы |
|---|---|---|
| T1 | Frontend: WaterfallChart component + integration в value-chain-tab | components/projects/waterfall-chart.tsx (new), value-chain-tab.tsx (modify) |
| T2 | docs + merge | CHANGELOG, GO5 |

Branch: `feat/c18-waterfall-unit-econ`. Tag: `v2.6.9`.
