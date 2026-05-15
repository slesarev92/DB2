"use client";

/**
 * C #14 — Fine Tuning: Channel-level per-period overrides.
 *
 * Generic секция для одного из 3 полей `ProjectSKUChannel`:
 *  - logistics_cost_per_kg  (₽/кг)
 *  - ca_m_rate              (доля Net Revenue, 0..1)
 *  - marketing_rate         (доля Net Revenue, 0..1)
 *
 * 1 строка = SKU × Channel пара. На save секция меняет ровно своё поле,
 * GET-ит текущие 3 поля канала и PUT-ит все три (чтобы не перезаписать
 * чужие изменения двух других секций).
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
import { listProjectSkuChannels } from "@/lib/channels";
import {
  getChannelOverrides,
  putChannelOverrides,
} from "@/lib/fine-tuning";
import { listProjectSkus } from "@/lib/skus";

import type {
  ChannelOverridesResponse,
  ProjectSKUChannelRead,
  ProjectSKURead,
} from "@/types/api";

const PERIOD_COUNT = 43;

export type ChannelField =
  | "logistics_cost_per_kg"
  | "ca_m_rate"
  | "marketing_rate";

const FIELD_TO_KEY: Record<ChannelField, keyof ChannelOverridesResponse> = {
  logistics_cost_per_kg: "logistics_cost_per_kg_by_period",
  ca_m_rate: "ca_m_rate_by_period",
  marketing_rate: "marketing_rate_by_period",
};

interface Props {
  projectId: number;
  field: ChannelField;
  label: string;
}

interface ChannelRowState {
  psk: ProjectSKURead;
  channel: ProjectSKUChannelRead;
  /** Длина 43; null = нет override этого поля. */
  values: (string | null)[];
  /** Серверная исходная версия — для diff. */
  initial: (string | null)[];
}

export function ChannelSection({ projectId, field, label }: Props) {
  const [collapsed, setCollapsed] = useState(true);
  const [rows, setRows] = useState<ChannelRowState[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Кэш «других двух полей» для каждого канала, чтобы PUT не затирал их
  // (при save GET-аем актуальное состояние перед PUT — см. handleSave).

  const fieldKey = FIELD_TO_KEY[field];

  useEffect(() => {
    if (collapsed) return; // ленивая загрузка при раскрытии секции
    let cancelled = false;
    setError(null);
    void (async () => {
      try {
        const psks = await listProjectSkus(projectId);
        const included = psks.filter((p) => p.include);
        // Параллельно тянем каналы для каждого PSK.
        const channelsPerPsk = await Promise.all(
          included.map((p) => listProjectSkuChannels(p.id)),
        );
        const flat: { psk: ProjectSKURead; channel: ProjectSKUChannelRead }[] = [];
        for (let i = 0; i < included.length; i++) {
          for (const ch of channelsPerPsk[i]) {
            flat.push({ psk: included[i], channel: ch });
          }
        }
        const overrides = await Promise.all(
          flat.map((p) => getChannelOverrides(projectId, p.channel.id)),
        );
        if (cancelled) return;
        const next: ChannelRowState[] = flat.map((p, idx) => {
          const arr = overrides[idx][fieldKey] ?? null;
          const values = arr ?? Array.from({ length: PERIOD_COUNT }, () => null);
          return { ...p, values, initial: [...values] };
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
  }, [projectId, fieldKey, collapsed]);

  const dirty = useMemo(() => {
    if (rows === null) return false;
    return rows.some((r) =>
      r.values.some((v, i) => !sameOverride(v, r.initial[i])),
    );
  }, [rows]);

  function updateCell(
    pscId: string | number,
    periodIdx: number,
    rawValue: string | null,
  ) {
    setRows((prev) => {
      if (prev === null) return prev;
      return prev.map((r) => {
        if (r.channel.id !== Number(pscId)) return r;
        const next = [...r.values];
        next[periodIdx] = normalizeInput(rawValue);
        return { ...r, values: next };
      });
    });
  }

  function applyBulkFill(rowKey: string, updates: Array<[number, string]>) {
    const pscId = Number(rowKey.replace(/^psc\./, ""));
    setRows((prev) => {
      if (prev === null) return prev;
      return prev.map((r) => {
        if (r.channel.id !== pscId) return r;
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
        // GET актуальное состояние всех 3 полей, переопределяем только
        // своё, PUT весь объект — иначе затрём изменения других секций.
        const current = await getChannelOverrides(projectId, r.channel.id);
        const allNull = r.values.every((v) => v === null);
        const newValue: (string | null)[] | null = allNull ? null : r.values;
        await putChannelOverrides(projectId, r.channel.id, {
          logistics_cost_per_kg_by_period:
            field === "logistics_cost_per_kg"
              ? newValue
              : current.logistics_cost_per_kg_by_period,
          ca_m_rate_by_period:
            field === "ca_m_rate"
              ? newValue
              : current.ca_m_rate_by_period,
          marketing_rate_by_period:
            field === "marketing_rate"
              ? newValue
              : current.marketing_rate_by_period,
        });
      }
      // Обновляем initial = current (только для нашего поля).
      setRows((prev) =>
        prev === null
          ? prev
          : prev.map((r) => ({ ...r, initial: [...r.values] })),
      );
      toast.success(`${label} — overrides сохранены`);
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
        id: r.channel.id,
        label: rowLabel(r.psk, r.channel),
        values: r.values,
      })),
    [rows],
  );

  const bulkRows: BulkFillTarget[] = useMemo(
    () =>
      (rows ?? []).map((r) => ({
        rowKey: `psc.${r.channel.id}`,
        label: rowLabel(r.psk, r.channel),
      })),
    [rows],
  );

  const scalarKey = field as keyof ProjectSKUChannelRead;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div
            className="cursor-pointer"
            onClick={() => setCollapsed((c) => !c)}
          >
            <CardTitle className="text-base">
              {collapsed ? "▶" : "▼"} {label} (per-period, на канал)
            </CardTitle>
            <CardDescription>
              Override по месяцам M1..M36 и годам Y4..Y10. Пустая ячейка =
              fallback на скаляр <code>{field}</code> в карточке канала.
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
              Нет SKU с каналами в проекте. Добавьте каналы во вкладке «Каналы».
            </p>
          )}
          {rows !== null && rows.length > 0 && (
            <PeriodGrid<string>
              rows={gridRows}
              onCellChange={(rowId, periodIdx, value) =>
                updateCell(rowId, periodIdx, value)
              }
              renderCell={(value, rowId, periodIdx) => {
                const row = rows.find((r) => r.channel.id === Number(rowId));
                const initial = row?.initial[periodIdx] ?? null;
                const isOverride = value !== null;
                const isDirty = !sameOverride(value, initial);
                const placeholder =
                  row !== undefined
                    ? Number(row.channel[scalarKey] as string).toString()
                    : "";
                return (
                  <input
                    type="number"
                    min="0"
                    step="0.0001"
                    value={value === null ? "" : String(Number(value))}
                    placeholder={placeholder}
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

function rowLabel(psk: ProjectSKURead, ch: ProjectSKUChannelRead): string {
  const sku = psk.sku;
  return `${sku.brand} ${sku.name} · ${ch.channel.code}`;
}

function normalizeInput(raw: string | null): string | null {
  if (raw === null) return null;
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  return trimmed;
}

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
