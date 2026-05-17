"use client";

/**
 * Reusable Waterfall (cascade) chart component based on Recharts.
 * Used in value-chain-tab to visualise per-unit P&L decomposition.
 */

import {
  Bar,
  BarChart,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface WaterfallStep {
  /** Имя ступеньки. */
  name: string;
  /** Дельта: положительная (доход/start) или отрицательная (расход). Для isTotal = 0. */
  delta: number;
  /** Если true — итоговая ступенька (total bar от 0 до running, синий). */
  isTotal?: boolean;
}

interface WaterfallChartProps {
  steps: WaterfallStep[];
  /** Подпись единицы измерения, например "₽/л". */
  unit?: string;
  /** Высота контейнера в px. */
  height?: number;
}

interface ChartEntry {
  name: string;
  base: number;
  value: number;
  total: boolean;
  delta: number;
}

export function WaterfallChart({ steps, unit = "₽", height = 400 }: WaterfallChartProps) {
  // Compute baseline + visible for each bar
  let running = 0;
  const chartData: ChartEntry[] = steps.map((step) => {
    if (step.isTotal) {
      // Total: bar from 0 to running — full visible, blue
      const snapshot = running;
      return { name: step.name, base: 0, value: snapshot, total: true, delta: 0 };
    }
    const start = running;
    const end = running + step.delta;
    running = end;
    if (step.delta >= 0) {
      // Positive delta: bar from start upwards
      return { name: step.name, base: start, value: step.delta, total: false, delta: step.delta };
    } else {
      // Negative delta: bar from end upwards (|delta| height)
      return {
        name: step.name,
        base: end,
        value: Math.abs(step.delta),
        total: false,
        delta: step.delta,
      };
    }
  });

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={chartData} margin={{ top: 10, right: 10, left: 10, bottom: 60 }}>
        <XAxis
          dataKey="name"
          angle={-30}
          textAnchor="end"
          interval={0}
          height={80}
          tick={{ fontSize: 11 }}
        />
        <YAxis
          tickFormatter={(v: number) => `${v.toFixed(1)} ${unit}`}
          tick={{ fontSize: 11 }}
          width={80}
        />
        <Tooltip
          formatter={(_value, _name, item) => {
            // item.payload is the raw ChartEntry from chartData
            const d = item.payload as ChartEntry;
            if (d.total) return [`${d.value.toFixed(2)} ${unit}`, "Итого"];
            const sign = d.delta >= 0 ? "+" : "−";
            return [`${sign}${Math.abs(d.delta).toFixed(2)} ${unit}`, ""];
          }}
        />
        <ReferenceLine y={0} stroke="#666" strokeWidth={1} />
        {/* Invisible base — positions the visible bar */}
        <Bar dataKey="base" stackId="a" fill="transparent" isAnimationActive={false} />
        {/* Visible colored value */}
        <Bar dataKey="value" stackId="a" isAnimationActive={false}>
          {chartData.map((entry, i) => {
            const color = entry.total
              ? "#3b82f6"
              : entry.delta >= 0
                ? "#22c55e"
                : "#ef4444";
            return <Cell key={i} fill={color} />;
          })}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
