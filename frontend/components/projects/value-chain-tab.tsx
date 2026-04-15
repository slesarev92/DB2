"use client";

/**
 * Value Chain / Стакан tab — per-unit waterfall экономика по SKU × канал (Phase 8.2).
 *
 * Rows = waterfall steps (Shelf → Ex-Factory → COGS → GP → Logistics → CM → EBITDA).
 * Columns = SKU (sub-columns = channels).
 * Margins with color coding: green >= 50%, yellow 45-50%, red < 45%.
 * Data from GET /api/projects/{id}/value-chain.
 */

import { useEffect, useState } from "react";

import { StalenessBadge } from "@/components/projects/staleness-badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ApiError, apiGet } from "@/lib/api";
import { listProjectScenarios, listScenarioResults } from "@/lib/scenarios";

/* ── Types ── */

interface ValueChainCell {
  channel_code: string;
  channel_name: string;
  shelf_price_reg: string;
  shelf_price_weighted: string;
  ex_factory: string;
  cogs_material: string;
  cogs_production: string;
  cogs_total: string;
  gross_profit: string;
  logistics: string;
  contribution: string;
  ca_m: string;
  marketing: string;
  ebitda: string;
  gp_margin: string;
  cm_margin: string;
  ebitda_margin: string;
}

interface ValueChainSKU {
  sku_brand: string;
  sku_name: string;
  sku_format: string | null;
  sku_volume_l: string | null;
  channels: ValueChainCell[];
}

interface ValueChainData {
  vat_rate: string;
  skus: ValueChainSKU[];
}

/* ── Helpers ── */

function fmt(val: string | number, decimals = 2): string {
  const n = typeof val === "string" ? parseFloat(val) : val;
  if (Number.isNaN(n)) return "\u2014";
  return n.toLocaleString("ru-RU", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function pct(val: string | number): string {
  const n = typeof val === "string" ? parseFloat(val) : val;
  if (Number.isNaN(n)) return "\u2014";
  return `${(n * 100).toFixed(1)}%`;
}

/** Color class for margin value: green >= 50%, yellow 45-50%, red < 45%. */
function marginColor(val: string | number): string {
  const n = typeof val === "string" ? parseFloat(val) : val;
  if (Number.isNaN(n)) return "";
  if (n >= 0.5) return "text-green-600 font-semibold";
  if (n >= 0.45) return "text-yellow-600 font-semibold";
  return "text-red-600 font-semibold";
}

/* ── Waterfall row definitions ── */

interface WaterfallRow {
  key: string;
  label: string;
  getValue: (c: ValueChainCell) => string;
  indent?: boolean;
  bold?: boolean;
  /** If set, applies margin color coding to the value */
  marginField?: keyof ValueChainCell;
  separator?: boolean;
}

const WATERFALL_ROWS: WaterfallRow[] = [
  { key: "shelf", label: "Цена полки (рег.)", getValue: (c) => fmt(c.shelf_price_reg), bold: true },
  { key: "shelf_w", label: "Цена полки (взвеш.)", getValue: (c) => fmt(c.shelf_price_weighted) },
  { key: "ex_factory", label: "Ex-Factory", getValue: (c) => fmt(c.ex_factory), bold: true },
  { key: "sep1", label: "", getValue: () => "", separator: true },
  { key: "cogs_mat", label: "COGS: материалы", getValue: (c) => fmt(c.cogs_material), indent: true },
  { key: "cogs_prod", label: "COGS: производство", getValue: (c) => fmt(c.cogs_production), indent: true },
  { key: "cogs_total", label: "COGS итого", getValue: (c) => fmt(c.cogs_total), bold: true },
  { key: "sep2", label: "", getValue: () => "", separator: true },
  { key: "gp", label: "Валовая прибыль (GP)", getValue: (c) => fmt(c.gross_profit), bold: true },
  { key: "gp_margin", label: "GP маржа", getValue: (c) => pct(c.gp_margin), marginField: "gp_margin" },
  { key: "sep3", label: "", getValue: () => "", separator: true },
  { key: "logistics", label: "Логистика", getValue: (c) => fmt(c.logistics), indent: true },
  { key: "contribution", label: "Contribution (CM)", getValue: (c) => fmt(c.contribution), bold: true },
  { key: "cm_margin", label: "CM маржа", getValue: (c) => pct(c.cm_margin), marginField: "cm_margin" },
  { key: "sep4", label: "", getValue: () => "", separator: true },
  { key: "ca_m", label: "КАиУР (CA&M)", getValue: (c) => fmt(c.ca_m), indent: true },
  { key: "marketing", label: "Маркетинг", getValue: (c) => fmt(c.marketing), indent: true },
  { key: "ebitda", label: "EBITDA", getValue: (c) => fmt(c.ebitda), bold: true },
  { key: "ebitda_margin", label: "EBITDA маржа", getValue: (c) => pct(c.ebitda_margin), marginField: "ebitda_margin" },
];

/* ── Component ── */

export function ValueChainTab({ projectId }: { projectId: number }) {
  const [data, setData] = useState<ValueChainData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [isStale, setIsStale] = useState(false);

  // F-02: проверяем is_stale через Base сценария
  useEffect(() => {
    void (async () => {
      try {
        const scenarios = await listProjectScenarios(projectId);
        const base = scenarios.find((s) => s.type === "base");
        if (!base) return;
        const results = await listScenarioResults(base.id);
        setIsStale(results.some((r) => r.is_stale));
      } catch {
        // 404 если расчёт не делался
      }
    })();
  }, [projectId]);

  useEffect(() => {
    setLoading(true);
    apiGet<ValueChainData>(`/api/projects/${projectId}/value-chain`)
      .then(setData)
      .catch((err) =>
        setError(err instanceof ApiError ? err.detail ?? err.message : "Ошибка"),
      )
      .finally(() => setLoading(false));
  }, [projectId]);

  if (loading) return <p className="text-sm text-muted-foreground">Загрузка...</p>;
  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!data || data.skus.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Нет SKU с привязанными каналами. Добавьте каналы в разделе &laquo;Каналы&raquo;.
      </p>
    );
  }

  // Collect all unique channels across SKUs
  const channelMap = new Map<string, string>();
  for (const sku of data.skus) {
    for (const ch of sku.channels) {
      channelMap.set(ch.channel_code, ch.channel_name);
    }
  }
  const channelCodes = [...channelMap.keys()];

  // Total number of data columns = SKUs × channels
  const totalCols = data.skus.length * channelCodes.length;

  return (
    <div className="space-y-6">
      <StalenessBadge
        isStale={isStale}
        message="Параметры проекта изменились — unit-экономика может быть неактуальна. Пересчитайте в табе «Результаты»."
      />
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">
            Unit-экономика (&#8381;/шт)
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              НДС {pct(data.vat_rate)} &middot; per-unit экономика на базовый период
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-xs border-collapse">
            {/* Header: SKU names spanning channels */}
            <thead>
              <tr className="border-b">
                <th className="px-2 py-1.5 text-left font-medium text-muted-foreground" rowSpan={2}>
                  Показатель
                </th>
                {data.skus.map((s, i) => (
                  <th
                    key={i}
                    className="px-2 py-1.5 text-center font-medium border-l"
                    colSpan={channelCodes.length}
                  >
                    <div>{s.sku_brand}</div>
                    <div className="text-[10px] text-muted-foreground font-normal">
                      {s.sku_name}
                      {s.sku_volume_l ? ` ${s.sku_volume_l}L` : ""}
                    </div>
                  </th>
                ))}
              </tr>
              <tr className="border-b">
                {data.skus.map((_, si) =>
                  channelCodes.map((code) => (
                    <th
                      key={`${si}-${code}`}
                      className="px-2 py-1 text-right text-[10px] font-medium text-muted-foreground border-l"
                    >
                      {code}
                    </th>
                  )),
                )}
              </tr>
            </thead>

            <tbody>
              {WATERFALL_ROWS.map((row) => {
                if (row.separator) {
                  return (
                    <tr key={row.key}>
                      <td colSpan={1 + totalCols} className="h-1 bg-muted/30" />
                    </tr>
                  );
                }
                return (
                  <tr key={row.key} className="border-b last:border-0 hover:bg-muted/30">
                    <td
                      className={`px-2 py-1.5 whitespace-nowrap ${
                        row.indent ? "pl-6 text-muted-foreground" : ""
                      } ${row.bold ? "font-medium" : ""}`}
                    >
                      {row.label}
                    </td>
                    {data.skus.map((s, si) =>
                      channelCodes.map((code) => {
                        const cell = s.channels.find((c) => c.channel_code === code);
                        if (!cell) {
                          return (
                            <td
                              key={`${si}-${code}`}
                              className="px-2 py-1.5 text-right tabular-nums border-l text-muted-foreground"
                            >
                              &mdash;
                            </td>
                          );
                        }
                        const colorCls = row.marginField
                          ? marginColor(cell[row.marginField])
                          : "";
                        return (
                          <td
                            key={`${si}-${code}`}
                            className={`px-2 py-1.5 text-right tabular-nums border-l ${
                              row.bold ? "font-medium" : ""
                            } ${colorCls}`}
                          >
                            {row.getValue(cell)}
                          </td>
                        );
                      }),
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {/* Legend */}
      <div className="flex items-center gap-4 text-xs text-muted-foreground px-1">
        <span>Цветовая индикация маржей:</span>
        <span className="text-green-600 font-semibold">&ge;50% — отлично</span>
        <span className="text-yellow-600 font-semibold">45-50% — норма</span>
        <span className="text-red-600 font-semibold">&lt;45% — внимание</span>
      </div>
    </div>
  );
}
