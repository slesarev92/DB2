"use client";

/**
 * C #14 — Fine Tuning: Copacking rate per-period (SKU-уровень).
 *
 * 1 строка на ProjectSKU. Override-cell визуально выделена (accent border).
 * Empty input = null override = fallback на скаляр `ProjectSKURead.copacking_rate`.
 * Save enabled только при наличии dirty changes.
 *
 * Decimal приходит как string ("99.5" или "99.50000000001" из-за JSONB
 * float round-trip). Для отображения парсим через `Number()`, не
 * используем string-equality. Для отправки на бэкенд — отдаём как string.
 */

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { PeriodBulkFill, type BulkFillTarget } from "@/components/shared/period-bulk-fill";
import { PeriodGrid, type PeriodGridRow } from "@/components/shared/period-grid";
import { ApiError } from "@/lib/api";
import { getSkuOverrides, putSkuOverrides } from "@/lib/fine-tuning";
import { listProjectSkus } from "@/lib/skus";

import type { ProjectSKURead } from "@/types/api";

const PERIOD_COUNT = 43;

interface Props {
  projectId: number;
}

interface SkuRowState {
  psk: ProjectSKURead;
  /** Длина 43; null = нет override (fallback на скаляр). */
  values: (string | null)[];
  /** Серверная исходная версия — для diff-проверки dirty. */
  initial: (string | null)[];
}

export function CopackingSection({ projectId }: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const [rows, setRows] = useState<SkuRowState[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Загрузка ProjectSKUs + их overrides.
  useEffect(() => {
    let cancelled = false;
    setError(null);
    void (async () => {
      try {
        const psks = await listProjectSkus(projectId);
        const included = psks.filter((p) => p.include);
        const overrides = await Promise.all(
          included.map((p) => getSkuOverrides(projectId, p.id)),
        );
        if (cancelled) return;
        const next: SkuRowState[] = included.map((psk, idx) => {
          const arr = overrides[idx].copacking_rate_by_period;
          const values = arr ?? Array.from({ length: PERIOD_COUNT }, () => null);
          return { psk, values, initial: [...values] };
        });
        setRows(next);
      } catch (err) {
        if (cancelled) return;
        setError(
          err instanceof ApiError ? err.detail ?? err.message : "Ошибка загрузки",
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const dirty = useMemo(() => {
    if (rows === null) return false;
    return rows.some((r) =>
      r.values.some((v, i) => !sameOverride(v, r.initial[i])),
    );
  }, [rows]);

  function updateCell(
    pskId: string | number,
    periodIdx: number,
    rawValue: string | null,
  ) {
    setRows((prev) => {
      if (prev === null) return prev;
      return prev.map((r) => {
        if (r.psk.id !== Number(pskId)) return r;
        const next = [...r.values];
        next[periodIdx] = normalizeInput(rawValue);
        return { ...r, values: next };
      });
    });
  }

  function applyBulkFill(rowKey: string, updates: Array<[number, string]>) {
    const pskId = Number(rowKey.replace(/^psk\./, ""));
    setRows((prev) => {
      if (prev === null) return prev;
      return prev.map((r) => {
        if (r.psk.id !== pskId) return r;
        const next = [...r.values];
        for (const [pn, val] of updates) {
          next[pn - 1] = normalizeInput(val);
        }
        return { ...r, values: next };
      });
    });
  }

  async function handleSave() {
    if (rows === null || !dirty) return;
    setSaving(true);
    setError(null);
    try {
      const dirtyRows = rows.filter((r) =>
        r.values.some((v, i) => !sameOverride(v, r.initial[i])),
      );
      for (const r of dirtyRows) {
        // Если все значения null → шлём null целиком (убрать override).
        const allNull = r.values.every((v) => v === null);
        await putSkuOverrides(projectId, r.psk.id, {
          copacking_rate_by_period: allNull ? null : r.values,
        });
      }
      // Refresh initial = current.
      setRows((prev) =>
        prev === null
          ? prev
          : prev.map((r) => ({ ...r, initial: [...r.values] })),
      );
      toast.success("Copacking overrides сохранены");
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка сохранения";
      setError(msg);
      toast.error(`Не удалось сохранить: ${msg}`);
    } finally {
      setSaving(false);
    }
  }

  const gridRows: PeriodGridRow<string>[] = useMemo(
    () =>
      (rows ?? []).map((r) => ({
        id: r.psk.id,
        label: skuLabel(r.psk),
        values: r.values,
      })),
    [rows],
  );

  const bulkRows: BulkFillTarget[] = useMemo(
    () =>
      (rows ?? []).map((r) => ({
        rowKey: `psk.${r.psk.id}`,
        label: skuLabel(r.psk),
      })),
    [rows],
  );

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div
            className="cursor-pointer"
            onClick={() => setCollapsed((c) => !c)}
          >
            <CardTitle className="text-base">
              {collapsed ? "▶" : "▼"} Copacking rate (per-period, на SKU)
            </CardTitle>
            <CardDescription>
              Override стоимости копакинга (₽/единица) по месяцам M1..M36 и
              годам Y4..Y10. Пустая ячейка = fallback на скаляр{" "}
              <code>copacking_rate</code> в карточке SKU.
            </CardDescription>
          </div>
          {!collapsed && (
            <div className="flex items-center gap-3">
              <PeriodBulkFill
                rows={bulkRows}
                onApply={applyBulkFill}
                disabled={saving || rows === null || rows.length === 0}
              />
              <Button
                size="sm"
                onClick={handleSave}
                disabled={saving || !dirty}
              >
                {saving ? "Сохранение..." : "Сохранить"}
              </Button>
            </div>
          )}
        </div>
      </CardHeader>
      {!collapsed && (
        <CardContent>
          {rows === null && error === null && (
            <p className="text-sm text-muted-foreground">Загрузка...</p>
          )}
          {error !== null && (
            <p className="mb-3 text-sm text-destructive" role="alert">
              {error}
            </p>
          )}
          {rows !== null && rows.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Нет включённых SKU в проекте. Добавьте SKU во вкладке «SKU и BOM».
            </p>
          )}
          {rows !== null && rows.length > 0 && (
            <PeriodGrid<string>
              rows={gridRows}
              onCellChange={(rowId, periodIdx, value) =>
                updateCell(rowId, periodIdx, value)
              }
              renderCell={(value, rowId, periodIdx) => {
                const row = rows.find((r) => r.psk.id === Number(rowId));
                const initial = row?.initial[periodIdx] ?? null;
                const isOverride = value !== null;
                const isDirty = !sameOverride(value, initial);
                return (
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={value === null ? "" : String(Number(value))}
                    placeholder={
                      row !== undefined ? Number(row.psk.copacking_rate).toString() : ""
                    }
                    disabled={saving}
                    onChange={(e) =>
                      updateCell(rowId, periodIdx, e.target.value)
                    }
                    className={cellClasses(isOverride, isDirty)}
                  />
                );
              }}
              readOnly={saving}
            />
          )}
        </CardContent>
      )}
    </Card>
  );
}

// ============================================================
// Helpers
// ============================================================

function skuLabel(psk: ProjectSKURead): string {
  const sku = psk.sku;
  const fmt = sku.format ? ` · ${sku.format}` : "";
  return `${sku.brand} ${sku.name}${fmt}`;
}

/** Пустой input → null override; иначе trim. */
function normalizeInput(raw: string | null): string | null {
  if (raw === null) return null;
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  return trimmed;
}

/**
 * Сравнение override-значений по числу, не по string-equality. JSONB
 * round-trip может изменить precision ("99.5" → "99.50000000000001").
 */
function sameOverride(a: string | null, b: string | null): boolean {
  if (a === null && b === null) return true;
  if (a === null || b === null) return false;
  return Number(a) === Number(b);
}

function cellClasses(isOverride: boolean, isDirty: boolean): string {
  const base = "h-7 w-full bg-transparent text-right text-xs px-1";
  if (isDirty) {
    return `${base} ring-2 ring-amber-400 rounded`;
  }
  if (isOverride) {
    return `${base} ring-1 ring-blue-400 rounded`;
  }
  return base;
}
