"use client";

import {
  AllCommunityModule,
  ModuleRegistry,
  type CellClassParams,
  type CellValueChangedEvent,
  type ColDef,
  type ICellRendererParams,
} from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { ValueHistoryDialog } from "@/components/projects/value-history-dialog";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import {
  batchPatchPeriodValues,
  listPeriodValuesHybrid,
  patchPeriodValue,
  resetPeriodOverride,
} from "@/lib/period-values";
import type { BatchPeriodValueItem } from "@/lib/period-values";
import { listPeriods } from "@/lib/reference";

import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-quartz.css";

import type {
  Period,
  PeriodHybridItem,
  SourceType,
} from "@/types/api";

// AG Grid v33+ требует явной регистрации модулей.
ModuleRegistry.registerModules([AllCommunityModule]);

interface PeriodsGridProps {
  projectId: number;
  pskChannelId: number;
  scenarioId: number;
  /** monthly | yearly | all — фильтр периодов на показ. */
  periodFilter: "monthly" | "yearly" | "all";
}

/** Метрики (rows). Соответствуют ключам в `values` JSONB PeriodValue. */
const METRICS: Array<{ key: string; label: string; precision: number }> = [
  { key: "nd", label: "ND (доля)", precision: 4 },
  { key: "offtake", label: "Off-take (ед./точка)", precision: 2 },
  { key: "shelf_price", label: "Shelf price, ₽", precision: 2 },
];

interface PivotRow {
  metric_key: string;
  metric_label: string;
  /** [period_id]: значение */
  [periodColKey: string]: string | number | null;
}

/** Хранит source_type и period_id отдельно для каждой ячейки. */
interface CellMeta {
  source_type: SourceType;
  period_id: number;
}

/**
 * AG Grid pivot таблица: rows = метрики (ND/Offtake/Shelf), columns = периоды.
 *
 * Подсветка ячеек по source_type:
 *   predict   — нейтральный фон
 *   finetuned — синий (ag-cell-finetuned)
 *   actual    — зелёный (ag-cell-actual)
 *
 * Inline edit включён только для метрик с numeric значениями. На
 * `cellValueChanged` → PATCH `/api/project-sku-channels/{id}/values/{period_id}`,
 * после успеха — refetch (простое решение, без optimistic update).
 *
 * Reset to predict — через клик правой кнопкой не сделан, но есть
 * кнопка "Сбросить overrides" в шапке если selectedRow выбран.
 */
export function PeriodsGrid({
  projectId,
  pskChannelId,
  scenarioId,
  periodFilter,
}: PeriodsGridProps) {
  const [periods, setPeriods] = useState<Period[] | null>(null);
  const [items, setItems] = useState<PeriodHybridItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadCounter, setReloadCounter] = useState(0);

  // Загрузка справочника периодов (один раз)
  useEffect(() => {
    let cancelled = false;
    listPeriods()
      .then((data) => {
        if (!cancelled) setPeriods(data);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof ApiError
            ? err.detail ?? err.message
            : "Не удалось загрузить периоды",
        );
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Загрузка PeriodValue для (psc, scenario)
  useEffect(() => {
    let cancelled = false;
    setItems(null);
    listPeriodValuesHybrid(pskChannelId, scenarioId)
      .then((data) => {
        if (!cancelled) setItems(data);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof ApiError ? err.detail ?? err.message : "Ошибка загрузки",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [pskChannelId, scenarioId, reloadCounter]);

  function reload() {
    setReloadCounter((c) => c + 1);
  }

  // Фильтрованный список периодов под текущий periodFilter
  const visiblePeriods = useMemo(() => {
    if (periods === null) return [];
    if (periodFilter === "monthly") {
      return periods.filter((p) => p.type === "monthly");
    }
    if (periodFilter === "yearly") {
      return periods.filter((p) => p.type === "annual");
    }
    return periods;
  }, [periods, periodFilter]);

  // Карта period_id → PeriodHybridItem (для быстрого lookup)
  const itemByPeriodId = useMemo(() => {
    if (items === null) return new Map<number, PeriodHybridItem>();
    return new Map(items.map((it) => [it.period_id, it]));
  }, [items]);

  // Pivot rows: одна строка на метрику
  const rowData: PivotRow[] = useMemo(() => {
    return METRICS.map((metric) => {
      const row: PivotRow = {
        metric_key: metric.key,
        metric_label: metric.label,
      };
      for (const period of visiblePeriods) {
        const item = itemByPeriodId.get(period.id);
        const v = item?.values[metric.key];
        const colKey = `p_${period.id}`;
        row[colKey] = v === undefined || v === null ? null : Number(v);
      }
      return row;
    });
  }, [visiblePeriods, itemByPeriodId]);

  // Column definitions
  const columnDefs: ColDef<PivotRow>[] = useMemo(() => {
    const cols: ColDef<PivotRow>[] = [
      {
        headerName: "Показатель",
        field: "metric_label",
        pinned: "left",
        width: 200,
        editable: false,
        cellStyle: { fontWeight: 500 },
      },
    ];

    for (const period of visiblePeriods) {
      const colKey = `p_${period.id}`;
      const headerName =
        period.type === "monthly"
          ? `M${period.period_number}`
          : `Y${period.model_year}`;

      cols.push({
        headerName,
        field: colKey,
        width: 90,
        editable: true,
        type: "numericColumn",
        // Подсветка по source_type
        cellClassRules: {
          "bg-blue-100": (params: CellClassParams<PivotRow>) => {
            const row = params.data;
            if (row === undefined) return false;
            const item = itemByPeriodId.get(period.id);
            return item?.source_type === "finetuned";
          },
          "bg-green-100": (params: CellClassParams<PivotRow>) => {
            const row = params.data;
            if (row === undefined) return false;
            const item = itemByPeriodId.get(period.id);
            return item?.source_type === "actual";
          },
        },
        valueFormatter: (params) => {
          if (params.value === null || params.value === undefined) return "";
          const metric = METRICS.find((m) => m.key === params.data?.metric_key);
          const precision = metric?.precision ?? 2;
          return Number(params.value).toLocaleString("ru-RU", {
            maximumFractionDigits: precision,
            minimumFractionDigits: 0,
          });
        },
      });
    }
    return cols;
  }, [visiblePeriods, itemByPeriodId]);

  // B-17: Batch save — accumulate pending changes, flush via button or debounce
  const pendingRef = useRef<Map<string, BatchPeriodValueItem>>(new Map());
  const [pendingCount, setPendingCount] = useState(0);
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function onCellValueChanged(e: CellValueChangedEvent<PivotRow>) {
    const colId = e.colDef.field;
    if (colId === undefined || !colId.startsWith("p_")) return;
    const periodId = Number(colId.slice(2));
    const metricKey = e.data.metric_key;
    const newValueRaw = e.newValue;

    const numericValue =
      newValueRaw === "" || newValueRaw === null
        ? null
        : Number(newValueRaw);
    if (numericValue !== null && Number.isNaN(numericValue)) {
      setError("Введите число");
      reload();
      return;
    }

    // Merge into pending batch
    const key = `${pskChannelId}:${periodId}`;
    const existing = pendingRef.current.get(key);
    const baseValues = existing
      ? existing.values
      : (itemByPeriodId.get(periodId)?.values ?? {});
    const nextValues = { ...baseValues, [metricKey]: numericValue };

    pendingRef.current.set(key, {
      psk_channel_id: pskChannelId,
      period_id: periodId,
      values: nextValues,
    });
    setPendingCount(pendingRef.current.size);

    // Auto-flush after 2s of inactivity
    if (flushTimerRef.current) clearTimeout(flushTimerRef.current);
    flushTimerRef.current = setTimeout(() => flushBatch(), 2000);
  }

  async function flushBatch() {
    if (flushTimerRef.current) clearTimeout(flushTimerRef.current);
    const items = Array.from(pendingRef.current.values());
    if (items.length === 0) return;

    pendingRef.current.clear();
    setPendingCount(0);

    try {
      await batchPatchPeriodValues(projectId, scenarioId, items);
      reload();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка batch save",
      );
      reload();
    }
  }

  async function handleResetAll() {
    if (
      !window.confirm(
        "Сбросить все finetuned overrides этого канала и сценария? " +
          "Predict значения вернутся на место.",
      )
    ) {
      return;
    }
    // Backend reset работает per-period, надо пройти по тем у которых
    // is_overridden = true.
    const overridden = (items ?? []).filter((it) => it.is_overridden);
    if (overridden.length === 0) {
      window.alert("Нет finetuned overrides для сброса.");
      return;
    }
    try {
      await Promise.all(
        overridden.map((it) =>
          resetPeriodOverride(pskChannelId, it.period_id, scenarioId),
        ),
      );
      reload();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка reset",
      );
    }
  }

  if (error !== null && items === null) {
    return (
      <div className="rounded-md border border-destructive p-4 text-sm text-destructive">
        {error}
      </div>
    );
  }

  if (periods === null || items === null) {
    return <p className="text-sm text-muted-foreground">Загрузка...</p>;
  }

  const overrideCount = items.filter((it) => it.is_overridden).length;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <p className="text-xs text-muted-foreground">
          Подсветка: <span className="rounded bg-blue-100 px-1">синий</span>{" "}
          finetuned override,{" "}
          <span className="rounded bg-green-100 px-1">зелёный</span> actual,
          без подсветки — predict
        </p>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={overrideCount === 0}
            onClick={handleResetAll}
          >
            Сбросить overrides ({overrideCount})
          </Button>
          {pendingCount > 0 && (
            <Button size="sm" onClick={flushBatch}>
              Сохранить ({pendingCount})
            </Button>
          )}
        </div>
      </div>

      {error !== null && (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      )}

      <div className="ag-theme-quartz" style={{ width: "100%" }}>
        <AgGridReact<PivotRow>
          rowData={rowData}
          columnDefs={columnDefs}
          onCellValueChanged={onCellValueChanged}
          singleClickEdit
          stopEditingWhenCellsLoseFocus
          suppressMovableColumns
          domLayout="autoHeight"
        />
      </div>

      {/* B-10: Version history per-period */}
      {overrideCount > 0 && (
        <div className="flex items-center gap-1 flex-wrap">
          <span className="text-xs text-muted-foreground mr-1">
            История:
          </span>
          {items
            .filter((it) => it.is_overridden)
            .map((it) => {
              const p = periods?.find((pp) => pp.id === it.period_id);
              const label = p
                ? p.period_number <= 36
                  ? `M${p.period_number}`
                  : `Y${p.model_year}`
                : `#${it.period_id}`;
              return (
                <ValueHistoryDialog
                  key={it.period_id}
                  pskChannelId={pskChannelId}
                  periodId={it.period_id}
                  scenarioId={scenarioId}
                  periodLabel={label}
                />
              );
            })}
        </div>
      )}
    </div>
  );
}
