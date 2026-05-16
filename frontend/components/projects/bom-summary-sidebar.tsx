"use client";

import { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatMoney } from "@/lib/format";
import type { BOMItemRead } from "@/types/api";

/** Категории BOM-ингредиентов (FK Ingredient.category). */
const CATEGORY_LABELS: Record<string, string> = {
  raw_material: "Сырьё",
  packaging: "Упаковка",
  other: "Прочее",
};

/** Порядок отображения категорий в сводке (фиксированный). */
const CATEGORY_ORDER = ["raw_material", "packaging", "other"] as const;

interface CategorySummary {
  sum: number;
  count: number;
}

interface BomSummarySidebarProps {
  items: BOMItemRead[];
}

/** Русский плюрал: 1 позиция / 2-4 позиции / 5+ позиций (учёт 11-14). */
function pluralPositions(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "позиция";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20))
    return "позиции";
  return "позиций";
}

function formatPct(num: number, total: number): string {
  if (total === 0) return "—";
  return `${((num / total) * 100).toFixed(1)}%`;
}

/**
 * Сводка BOM справа от таблицы: разбивка по категориям ингредиентов
 * (Сырьё / Упаковка / Прочее) с суммой ₽, кол-вом позиций, % от итога.
 * Сумма категории = Σ qty × price × (1 + loss) per items.
 */
export function BomSummarySidebar({ items }: BomSummarySidebarProps) {
  const { byCat, total, totalCount } = useMemo(() => {
    const byCat: Record<string, CategorySummary> = {
      raw_material: { sum: 0, count: 0 },
      packaging: { sum: 0, count: 0 },
      other: { sum: 0, count: 0 },
    };
    let total = 0;
    for (const it of items) {
      const cat = it.ingredient_category ?? "other";
      const slot = byCat[cat] ?? byCat.other;
      const cost =
        Number(it.quantity_per_unit) *
        Number(it.price_per_unit) *
        (1 + Number(it.loss_pct));
      if (!Number.isNaN(cost)) {
        slot.sum += cost;
        total += cost;
        slot.count += 1;
      }
    }
    const totalCount = CATEGORY_ORDER.reduce(
      (acc, c) => acc + byCat[c].count,
      0,
    );
    return { byCat, total, totalCount };
  }, [items]);

  if (totalCount === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Сводка BOM</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Добавьте позиции BOM для расчёта.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Сводка BOM</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-2">
          {CATEGORY_ORDER.map((cat) => {
            const entry = byCat[cat];
            const empty = entry.count === 0;
            return (
              <div
                key={cat}
                className="flex items-baseline justify-between gap-2 text-sm"
              >
                <div>
                  <div className="font-medium">{CATEGORY_LABELS[cat]}</div>
                  <div className="text-xs text-muted-foreground">
                    {empty
                      ? "0 позиций"
                      : `${entry.count} поз., ${formatPct(entry.sum, total)}`}
                  </div>
                </div>
                <div className="text-right font-medium tabular-nums">
                  {empty ? (
                    <span className="text-muted-foreground">—</span>
                  ) : (
                    formatMoney(String(entry.sum))
                  )}
                </div>
              </div>
            );
          })}
        </div>
        <div className="border-t pt-3 flex items-baseline justify-between gap-2 text-sm font-semibold">
          <div>
            <div>Итого</div>
            <div className="text-xs font-normal text-muted-foreground">
              {totalCount} {pluralPositions(totalCount)}
            </div>
          </div>
          <div className="tabular-nums">{formatMoney(String(total))}</div>
        </div>
      </CardContent>
    </Card>
  );
}
