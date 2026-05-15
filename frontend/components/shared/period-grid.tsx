"use client";

import React from "react";

import { periodLabel } from "@/lib/financial-plan-utils";

const PERIOD_COUNT = 43;

export interface PeriodGridRow<T = unknown> {
  id: string | number;
  label: string;
  values: (T | null)[]; // length 43
  metadata?: Record<string, unknown>;
}

export interface PeriodGridProps<T = unknown> {
  rows: PeriodGridRow<T>[];
  onCellChange?: (rowId: PeriodGridRow["id"], periodIdx: number, value: T | null) => void;
  renderCell?: (value: T | null, rowId: PeriodGridRow["id"], periodIdx: number) => React.ReactNode;
  readOnly?: boolean;
  className?: string;
}

/**
 * Generic 43-period grid (M1..M36 + Y4..Y10).
 *
 * Sticky left column with row labels; scrollable 43-column body.
 * Used as the shared scaffold for per-period editors (B.9b+).
 *
 * Pass `renderCell` for custom cell rendering (e.g. domain-specific inputs).
 * Without `renderCell`, renders a plain number input.
 */
export function PeriodGrid<T>({
  rows,
  onCellChange,
  renderCell,
  readOnly,
  className,
}: PeriodGridProps<T>) {
  return (
    <div className={className}>
      <div className="overflow-x-auto border rounded">
        <table className="min-w-full text-xs border-collapse">
          <thead>
            <tr className="bg-muted">
              <th
                className="sticky left-0 bg-muted px-2 py-1 text-left border-r"
                style={{ minWidth: 220 }}
              >
                Статья / Период
              </th>
              <th colSpan={12} className="text-center border-r">
                Y1 (M1-M12)
              </th>
              <th colSpan={12} className="text-center border-r">
                Y2 (M13-M24)
              </th>
              <th colSpan={12} className="text-center border-r">
                Y3 (M25-M36)
              </th>
              <th colSpan={7} className="text-center">
                Y4-Y10
              </th>
            </tr>
            <tr className="bg-muted/50">
              <th className="sticky left-0 bg-muted/50 border-r" />
              {Array.from({ length: PERIOD_COUNT }, (_, i) => (
                <th
                  key={i}
                  className="px-1 py-0.5 text-center border-r font-mono"
                  style={{ minWidth: 70 }}
                >
                  {periodLabel(i + 1)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td className="sticky left-0 bg-background px-2 py-1 border-r font-medium">
                  {row.label}
                </td>
                {Array.from({ length: PERIOD_COUNT }, (_, i) => (
                  <td key={i} className="border-r text-center">
                    {renderCell ? (
                      renderCell(row.values[i] ?? null, row.id, i)
                    ) : (
                      <input
                        type="number"
                        value={row.values[i] === null ? "" : String(row.values[i])}
                        disabled={readOnly}
                        onChange={(e) => {
                          const raw = e.target.value;
                          const parsed = raw === "" ? null : (raw as unknown as T);
                          onCellChange?.(row.id, i, parsed);
                        }}
                        className="h-7 w-full bg-transparent text-right text-xs"
                      />
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
