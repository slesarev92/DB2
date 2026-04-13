"use client";

/**
 * P&L tab — per-period P&L с переключателем месяцы/кварталы/годы (Phase 8.5).
 *
 * Fetches 43 per-period P&L metrics from GET /api/projects/{id}/pnl
 * and aggregates client-side based on selected mode.
 */

import { useEffect, useMemo, useState } from "react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ApiError, apiGet } from "@/lib/api";

/* ── Types ── */

interface PnlPeriod {
  period_label: string;
  period_type: "monthly" | "annual";
  model_year: number;
  month_num: number | null;
  quarter: number | null;
  volume_units: number;
  volume_liters: number;
  net_revenue: number;
  cogs_material: number;
  cogs_production: number;
  cogs_copacking: number;
  cogs_total: number;
  gross_profit: number;
  logistics_cost: number;
  contribution: number;
  ca_m_cost: number;
  marketing_cost: number;
  ebitda: number;
  working_capital: number;
  delta_working_capital: number;
  tax: number;
  operating_cash_flow: number;
  investing_cash_flow: number;
  free_cash_flow: number;
}

interface PnlData {
  scenario_type: string;
  periods: PnlPeriod[];
}

type ViewMode = "monthly" | "quarterly" | "annual";

/* ── Helpers ── */

function fmt(val: number, decimals = 0): string {
  return val.toLocaleString("ru-RU", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

const METRIC_ROWS: { key: keyof PnlPeriod; label: string; bold?: boolean; indent?: boolean }[] = [
  { key: "volume_units", label: "Объём (шт)" },
  { key: "volume_liters", label: "Объём (л)" },
  { key: "net_revenue", label: "Выручка (NR)", bold: true },
  { key: "cogs_material", label: "Сырьё и материалы", indent: true },
  { key: "cogs_production", label: "Производство", indent: true },
  { key: "cogs_copacking", label: "Копакинг", indent: true },
  { key: "cogs_total", label: "COGS итого", bold: true },
  { key: "gross_profit", label: "Валовая прибыль (GP)", bold: true },
  { key: "logistics_cost", label: "Логистика" },
  { key: "contribution", label: "Contribution (CM)", bold: true },
  { key: "ca_m_cost", label: "КАиУР (CA&M)" },
  { key: "marketing_cost", label: "Маркетинг" },
  { key: "ebitda", label: "EBITDA", bold: true },
  { key: "working_capital", label: "Рабочий капитал (WC)" },
  { key: "delta_working_capital", label: "Изменение WC (ΔWC)" },
  { key: "tax", label: "Налог на прибыль" },
  { key: "operating_cash_flow", label: "OCF", bold: true },
  { key: "investing_cash_flow", label: "ICF (CAPEX)" },
  { key: "free_cash_flow", label: "FCF", bold: true },
];

/* ── Aggregation ── */

interface AggBucket {
  label: string;
  data: Record<string, number>;
}

function aggregatePeriods(periods: PnlPeriod[], mode: ViewMode): AggBucket[] {
  if (mode === "monthly") {
    // Show all 43 periods as-is
    return periods.map((p) => ({
      label: p.period_label,
      data: p as unknown as Record<string, number>,
    }));
  }

  // Group by key
  const groups = new Map<string, PnlPeriod[]>();
  for (const p of periods) {
    let key: string;
    if (mode === "quarterly") {
      if (p.period_type === "monthly" && p.quarter != null) {
        key = `Q${p.quarter} Y${p.model_year}`;
      } else {
        key = p.period_label; // Y4..Y10 stay as annual
      }
    } else {
      // annual
      key = `Y${p.model_year}`;
    }
    const arr = groups.get(key) ?? [];
    arr.push(p);
    groups.set(key, arr);
  }

  const result: AggBucket[] = [];
  for (const [label, items] of groups) {
    const summed: Record<string, number> = {};
    for (const metric of METRIC_ROWS) {
      summed[metric.key] = items.reduce((acc, p) => acc + (p[metric.key] as number), 0);
    }
    result.push({ label, data: summed });
  }
  return result;
}

/* ── Component ── */

const MODE_LABELS: Record<ViewMode, string> = {
  monthly: "Месяцы",
  quarterly: "Кварталы",
  annual: "Годы",
};

export function PnlTab({ projectId }: { projectId: number }) {
  const [data, setData] = useState<PnlData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<ViewMode>("quarterly");

  useEffect(() => {
    setLoading(true);
    apiGet<PnlData>(`/api/projects/${projectId}/pnl`)
      .then(setData)
      .catch((err) =>
        setError(err instanceof ApiError ? err.detail ?? err.message : "Ошибка"),
      )
      .finally(() => setLoading(false));
  }, [projectId]);

  const buckets = useMemo(
    () => (data ? aggregatePeriods(data.periods, mode) : []),
    [data, mode],
  );

  if (loading) return <p className="text-sm text-muted-foreground">Загрузка P&L...</p>;
  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!data || data.periods.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Нет данных для P&L. Добавьте SKU и каналы, затем пересчитайте сценарий.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {/* Mode toggle */}
      <div className="flex items-center gap-2">
        {(["monthly", "quarterly", "annual"] as ViewMode[]).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`px-3 py-1 text-xs rounded-md border transition-colors ${
              mode === m
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-background text-muted-foreground border-border hover:bg-muted"
            }`}
          >
            {MODE_LABELS[m]}
          </button>
        ))}
        <span className="text-xs text-muted-foreground ml-2">
          Base scenario &middot; {buckets.length} периодов
        </span>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">
            P&L — {MODE_LABELS[mode]}
          </CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="text-xs border-collapse">
            <thead>
              <tr className="border-b">
                <th className="px-2 py-1.5 text-left font-medium text-muted-foreground sticky left-0 bg-background z-10 min-w-[160px]">
                  Показатель
                </th>
                {buckets.map((b) => (
                  <th
                    key={b.label}
                    className="px-2 py-1.5 text-right font-medium min-w-[90px]"
                  >
                    {b.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {METRIC_ROWS.map((row) => (
                <tr key={row.key} className="border-b last:border-0 hover:bg-muted/30">
                  <td
                    className={`px-2 py-1.5 whitespace-nowrap sticky left-0 bg-background z-10 ${
                      row.bold ? "font-medium" : "text-muted-foreground"
                    } ${row.indent ? "pl-6" : ""}`}
                  >
                    {row.label}
                  </td>
                  {buckets.map((b) => (
                    <td
                      key={b.label}
                      className={`px-2 py-1.5 text-right tabular-nums ${
                        row.bold ? "font-medium" : ""
                      }`}
                    >
                      {fmt(b.data[row.key] ?? 0)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
