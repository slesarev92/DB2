"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";
import { formatMoney } from "@/lib/format";
import {
  classifyNpvHex,
  type SensitivityThresholds,
} from "@/lib/sensitivity-thresholds";

import type { SensitivityResponse } from "@/types/api";

interface TornadoChartProps {
  data: SensitivityResponse;
  thresholds: SensitivityThresholds;
}

// PARAM_LABELS — единый в types/api.ts (L-05).
import { SENSITIVITY_PARAM_LABELS as PARAM_LABELS } from "@/types/api";

interface TornadoBar {
  parameter: string;
  label: string;
  low: number;
  high: number;
  base: number;
  /** Signed delta from base: negative side */
  negDelta: number;
  /** Signed delta from base: positive side */
  posDelta: number;
  /** Total range width (for sorting) */
  range: number;
}

/**
 * Tornado chart (B-11).
 *
 * Горизонтальные бары показывают диапазон NPV при ±20% изменении каждого
 * параметра. Самый влиятельный параметр — наверху (sorted by range desc).
 *
 * Используем ±20% (крайний уровень) для максимального контраста.
 */
export function TornadoChart({ data, thresholds }: TornadoChartProps) {
  if (data.base_npv_y1y10 === null) return null;

  const baseNpv = data.base_npv_y1y10;
  const bars: TornadoBar[] = [];

  for (const param of data.params) {
    const neg20 = data.cells.find(
      (c) => c.parameter === param && c.delta === -0.2,
    );
    const pos20 = data.cells.find(
      (c) => c.parameter === param && c.delta === 0.2,
    );
    if (!neg20?.npv_y1y10 || !pos20?.npv_y1y10) continue;

    const low = Math.min(neg20.npv_y1y10, pos20.npv_y1y10);
    const high = Math.max(neg20.npv_y1y10, pos20.npv_y1y10);

    bars.push({
      parameter: param,
      label: PARAM_LABELS[param] ?? param,
      low,
      high,
      base: baseNpv,
      negDelta: low - baseNpv,
      posDelta: high - baseNpv,
      range: high - low,
    });
  }

  // Sort: widest range on top
  bars.sort((a, b) => b.range - a.range);

  // Recharts stacked bar approach: two bars from base
  // We render a horizontal bar chart with stacked bars
  const chartData = bars.map((b) => ({
    name: b.label,
    // Negative side: from low to base (negative delta from base)
    negative: b.negDelta,
    // Positive side: from base to high (positive delta from base)
    positive: b.posDelta,
    base: b.base,
    low: b.low,
    high: b.high,
  }));

  return (
    <Card>
      <CardHeader>
        <CardDescription>
          Диапазон NPV Y1-Y10 при ±20% изменении каждого параметра.
          Вертикальная линия — Base NPV ({formatMoney(String(baseNpv))}).
          Чем шире полоса — тем влиятельнее параметр.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={bars.length * 60 + 40}>
          <BarChart
            data={chartData}
            layout="vertical"
            margin={{ top: 5, right: 30, left: 80, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" horizontal={false} />
            <XAxis
              type="number"
              tickFormatter={(v: number) =>
                `${(v / 1_000_000).toFixed(1)}M`
              }
              domain={["auto", "auto"]}
            />
            <YAxis
              type="category"
              dataKey="name"
              width={75}
              tick={{ fontSize: 13 }}
            />
            <Tooltip
              formatter={(value, name) => {
                const label = name === "negative" ? "Снижение" : "Рост";
                return [formatMoney(String(value)), label];
              }}
              labelFormatter={(label) => `Параметр: ${String(label)}`}
            />
            <ReferenceLine x={0} stroke="#666" strokeWidth={2} />
            <Bar dataKey="negative" stackId="a" radius={[4, 0, 0, 4]}>
              {chartData.map((entry, i) => (
                <Cell
                  key={`neg-${i}`}
                  fill={classifyNpvHex(entry.low, entry.base, thresholds)}
                />
              ))}
            </Bar>
            <Bar dataKey="positive" stackId="a" radius={[0, 4, 4, 0]}>
              {chartData.map((entry, i) => (
                <Cell
                  key={`pos-${i}`}
                  fill={classifyNpvHex(entry.high, entry.base, thresholds)}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
