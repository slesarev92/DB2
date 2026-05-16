"use client";

/**
 * Pricing Summary tab — сводная таблица цен SKU × канал (Phase 8.1).
 *
 * Rows = каналы, Columns = SKU.
 * Cells: полочная цена, промо, взвешенная, ex-factory, COGS.
 * Данные из GET /api/projects/{id}/pricing-summary.
 */

import { useEffect, useState } from "react";

import { ChevronsDownUp, ChevronsUpDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { CollapsibleSection } from "@/components/ui/collapsible";
import { ApiError, apiGet } from "@/lib/api";
import { PRICING_SECTIONS } from "@/lib/analysis-sections";
import { formatVolume } from "@/lib/format";
import { useCollapseState } from "@/lib/use-collapse-state";
import type { SkuUnitOfMeasure } from "@/types/api";

interface PricingCell {
  channel_code: string;
  channel_name: string;
  shelf_price_reg: string;
  shelf_price_promo: string;
  shelf_price_weighted: string;
  ex_factory: string;
  channel_margin: string;
  promo_discount: string;
  promo_share: string;
}

interface SKUColumn {
  sku_brand: string;
  sku_name: string;
  sku_format: string | null;
  sku_volume_l: string | null;
  /** C #23: единица измерения объёма/массы SKU. */
  sku_unit_of_measure: SkuUnitOfMeasure;
  cogs_per_unit: string;
  channels: PricingCell[];
}

interface PricingSummary {
  vat_rate: string;
  skus: SKUColumn[];
}

function fmt(val: string | number, decimals = 2): string {
  const n = typeof val === "string" ? parseFloat(val) : val;
  if (Number.isNaN(n)) return "—";
  return n.toLocaleString("ru-RU", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function pct(val: string | number): string {
  const n = typeof val === "string" ? parseFloat(val) : val;
  if (Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

export function PricingTab({ projectId }: { projectId: number }) {
  const [data, setData] = useState<PricingSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const collapse = useCollapseState(projectId, "pricing", PRICING_SECTIONS);

  useEffect(() => {
    setLoading(true);
    apiGet<PricingSummary>(`/api/projects/${projectId}/pricing-summary`)
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
        Нет SKU с привязанными каналами. Добавьте каналы в разделе «Каналы».
      </p>
    );
  }

  // Collect unique channel codes across all SKUs (union)
  const channelMap = new Map<string, string>();
  for (const sku of data.skus) {
    for (const ch of sku.channels) {
      channelMap.set(ch.channel_code, ch.channel_name);
    }
  }
  const channelCodes = [...channelMap.keys()];

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        {collapse.allOpen ? (
          <Button variant="ghost" size="sm" onClick={collapse.collapseAll}>
            <ChevronsDownUp className="mr-1.5 size-3.5" />
            Свернуть всё
          </Button>
        ) : (
          <Button variant="ghost" size="sm" onClick={collapse.expandAll}>
            <ChevronsUpDown className="mr-1.5 size-3.5" />
            Развернуть всё
          </Button>
        )}
      </div>

      {/* Shelf Prices Table */}
      <CollapsibleSection
        sectionId="shelf-price"
        title="Цена полки (₽/шт)"
        isOpen={collapse.isOpen("shelf-price")}
        onToggle={() => collapse.toggle("shelf-price")}
      >
        <Card>
          <CardContent className="overflow-x-auto pt-6">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b">
                  <th className="px-2 py-1.5 text-left font-medium text-muted-foreground">Канал</th>
                  {data.skus.map((s, i) => (
                    <th key={i} className="px-2 py-1.5 text-right font-medium" colSpan={1}>
                      <div>{s.sku_brand}</div>
                      <div className="text-[10px] text-muted-foreground font-normal">
                        {s.sku_name}
                        {s.sku_volume_l ? ` ${formatVolume(s.sku_volume_l, s.sku_unit_of_measure)}` : ""}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {channelCodes.map((code) => (
                  <tr key={code} className="border-b last:border-0 hover:bg-muted/30">
                    <td className="px-2 py-1.5 font-medium">
                      {channelMap.get(code)} <span className="text-muted-foreground">({code})</span>
                    </td>
                    {data.skus.map((s, i) => {
                      const cell = s.channels.find((c) => c.channel_code === code);
                      return (
                        <td key={i} className="px-2 py-1.5 text-right tabular-nums">
                          {cell ? fmt(cell.shelf_price_reg) : "—"}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </CollapsibleSection>

      {/* Ex-Factory Table */}
      <CollapsibleSection
        sectionId="ex-factory"
        title={
          <>
            Цена отгрузки / Ex-Factory (₽/шт)
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              НДС {pct(data.vat_rate)}
            </span>
          </>
        }
        isOpen={collapse.isOpen("ex-factory")}
        onToggle={() => collapse.toggle("ex-factory")}
      >
        <Card>
          <CardContent className="overflow-x-auto pt-6">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b">
                  <th className="px-2 py-1.5 text-left font-medium text-muted-foreground">Канал</th>
                  {data.skus.map((s, i) => (
                    <th key={i} className="px-2 py-1.5 text-right font-medium">
                      {s.sku_brand} {s.sku_name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {channelCodes.map((code) => (
                  <tr key={code} className="border-b last:border-0 hover:bg-muted/30">
                    <td className="px-2 py-1.5 font-medium">{code}</td>
                    {data.skus.map((s, i) => {
                      const cell = s.channels.find((c) => c.channel_code === code);
                      return (
                        <td key={i} className="px-2 py-1.5 text-right tabular-nums">
                          {cell ? fmt(cell.ex_factory) : "—"}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </CollapsibleSection>

      {/* Margins & COGS */}
      <CollapsibleSection
        sectionId="costs-margins"
        title="Себестоимость и маржи"
        isOpen={collapse.isOpen("costs-margins")}
        onToggle={() => collapse.toggle("costs-margins")}
      >
        <Card>
          <CardContent className="overflow-x-auto pt-6">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b">
                  <th className="px-2 py-1.5 text-left font-medium text-muted-foreground">Показатель</th>
                  {data.skus.map((s, i) => (
                    <th key={i} className="px-2 py-1.5 text-right font-medium">
                      {s.sku_brand} {s.sku_name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr className="border-b hover:bg-muted/30">
                  <td className="px-2 py-1.5 font-medium">COGS / шт (BOM)</td>
                  {data.skus.map((s, i) => (
                    <td key={i} className="px-2 py-1.5 text-right tabular-nums">
                      {fmt(s.cogs_per_unit)}
                    </td>
                  ))}
                </tr>
                {channelCodes.map((code) => (
                  <tr key={code} className="border-b last:border-0 hover:bg-muted/30">
                    <td className="px-2 py-1.5 text-muted-foreground pl-4">{code} — маржа канала</td>
                    {data.skus.map((s, i) => {
                      const cell = s.channels.find((c) => c.channel_code === code);
                      return (
                        <td key={i} className="px-2 py-1.5 text-right tabular-nums">
                          {cell ? pct(cell.channel_margin) : "—"}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </CollapsibleSection>
    </div>
  );
}
