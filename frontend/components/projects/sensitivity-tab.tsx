"use client";

import { useCallback, useEffect, useState } from "react";

import { ExplainSensitivityInline } from "@/components/ai-panel/explain-sensitivity-inline";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError } from "@/lib/api";
import { formatMoney, formatPercent } from "@/lib/format";
import { listProjectScenarios } from "@/lib/scenarios";
import { computeSensitivity } from "@/lib/sensitivity";

import type { SensitivityCell, SensitivityResponse } from "@/types/api";

interface SensitivityTabProps {
  projectId: number;
}

const PARAM_LABELS: Record<SensitivityCell["parameter"], string> = {
  nd: "ND",
  offtake: "Off-take",
  shelf_price: "Shelf price",
  cogs: "COGS (BOM)",
};

const PARAM_ORDER: SensitivityCell["parameter"][] = [
  "nd",
  "offtake",
  "shelf_price",
  "cogs",
];

/** Форматирует delta -0.20 → "−20%", 0 → "Base", +0.20 → "+20%". */
function formatDeltaLabel(delta: number): string {
  if (delta === 0) return "Base";
  const sign = delta > 0 ? "+" : "−";
  return `${sign}${Math.abs(delta * 100).toFixed(0)}%`;
}

/** Цвет для NPV: positive зелёный, negative красный, base нейтральный. */
function npvClass(value: number | null, baseValue: number | null): string {
  if (value === null || baseValue === null) return "";
  if (value > baseValue) return "text-green-600";
  if (value < baseValue) return "text-red-600";
  return "";
}

/**
 * Таб "Чувствительность" в карточке проекта.
 *
 * Показывает матрицу 5 уровней × 4 параметров. Каждая ячейка содержит
 * NPV Y1-Y10 (большой шрифт) и CM% ratio (маленьким серым). Base строка
 * (delta=0) — одинакова для всех 4 параметров.
 *
 * Backend `POST /api/projects/{id}/sensitivity` запускается синхронно
 * (20 in-memory pipeline runs ~50-100ms). Без Celery polling.
 *
 * Кнопка "Рассчитать" триггерит запрос. До первого запуска показывается
 * placeholder с описанием.
 */
export function SensitivityTab({ projectId }: SensitivityTabProps) {
  const [data, setData] = useState<SensitivityResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasFetched, setHasFetched] = useState(false);
  const [baseScenarioId, setBaseScenarioId] = useState<number | null>(null);

  // Fetch base scenario ID for AI inline
  useEffect(() => {
    listProjectScenarios(projectId)
      .then((scenarios) => {
        const base = scenarios.find((s) => s.type === "base");
        if (base) setBaseScenarioId(base.id);
      })
      .catch(() => {});
  }, [projectId]);

  const handleCompute = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await computeSensitivity(projectId);
      setData(response);
      setHasFetched(true);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка",
      );
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  // Авто-запуск при монтировании (для UX — пользователь сразу видит данные)
  useEffect(() => {
    void handleCompute();
  }, [handleCompute]);

  return (
    <div className="space-y-6">
      {/* Header + кнопка перерасчёта */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Анализ чувствительности</h2>
          <p className="text-sm text-muted-foreground">
            NPV Y1-Y10 и Contribution Margin при изменении ключевых
            параметров на ±10% и ±20% от Base сценария.
          </p>
        </div>
        <Button onClick={handleCompute} disabled={loading}>
          {loading ? "Считаем..." : "Пересчитать"}
        </Button>
      </div>

      {error !== null && (
        <Card className="border-destructive">
          <CardContent className="pt-6 text-sm text-destructive">
            {error}
          </CardContent>
        </Card>
      )}

      {!hasFetched && loading && (
        <p className="text-sm text-muted-foreground">Расчёт...</p>
      )}

      {data !== null && (
        <>
          {/* Base reference card */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Base reference</CardTitle>
              <CardDescription>
                Значения Base сценария — точка отсчёта для всех ячеек ниже.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <p className="text-xs uppercase tracking-wide text-muted-foreground">
                    NPV Y1-Y10
                  </p>
                  <p className="mt-1 text-xl font-semibold">
                    {data.base_npv_y1y10 === null
                      ? "—"
                      : formatMoney(String(data.base_npv_y1y10))}
                  </p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-muted-foreground">
                    Contribution Margin
                  </p>
                  <p className="mt-1 text-xl font-semibold">
                    {data.base_cm_ratio === null
                      ? "—"
                      : formatPercent(String(data.base_cm_ratio))}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* AI interpretation (Phase 7.3) */}
          {baseScenarioId !== null && (
            <ExplainSensitivityInline
              projectId={projectId}
              projectName="Проект"
              scenarioId={baseScenarioId}
            />
          )}

          {/* Sensitivity table */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Матрица 5 × 4 (NPV / CM%)
              </CardTitle>
              <CardDescription>
                Строки = уровни изменения (−20%..+20%). Колонки = параметры.
                Каждая ячейка: NPV Y1-Y10 (главное) и Contribution Margin
                (мелким серым).
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Изменение</TableHead>
                    {PARAM_ORDER.map((p) => (
                      <TableHead key={p} className="text-right">
                        {PARAM_LABELS[p]}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.deltas.map((delta) => (
                    <TableRow
                      key={delta}
                      className={delta === 0 ? "bg-muted/30" : ""}
                    >
                      <TableCell className="font-medium">
                        {formatDeltaLabel(delta)}
                      </TableCell>
                      {PARAM_ORDER.map((param) => {
                        const cell = data.cells.find(
                          (c) =>
                            c.parameter === param && c.delta === delta,
                        );
                        if (cell === undefined) {
                          return (
                            <TableCell
                              key={param}
                              className="text-right text-muted-foreground"
                            >
                              —
                            </TableCell>
                          );
                        }
                        return (
                          <TableCell key={param} className="text-right">
                            <div
                              className={`font-semibold ${npvClass(
                                cell.npv_y1y10,
                                data.base_npv_y1y10,
                              )}`}
                            >
                              {cell.npv_y1y10 === null
                                ? "—"
                                : formatMoney(String(cell.npv_y1y10))}
                            </div>
                            <div className="text-xs text-muted-foreground">
                              CM:{" "}
                              {cell.cm_ratio === null
                                ? "—"
                                : formatPercent(String(cell.cm_ratio))}
                            </div>
                          </TableCell>
                        );
                      })}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
