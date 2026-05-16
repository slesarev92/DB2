"use client";

import { useCallback, useEffect, useState } from "react";

import { ChevronsDownUp, ChevronsUpDown } from "lucide-react";
import { ExplainSensitivityInline } from "@/components/ai-panel/explain-sensitivity-inline";
import { TornadoChart } from "@/components/projects/tornado-chart";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";
import { CollapsibleSection } from "@/components/ui/collapsible";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError } from "@/lib/api";
import { SENSITIVITY_SECTIONS } from "@/lib/analysis-sections";
import { formatMoney, formatPercent } from "@/lib/format";
import { getProject } from "@/lib/projects";
import { listProjectScenarios } from "@/lib/scenarios";
import { computeSensitivity } from "@/lib/sensitivity";
import {
  classifyNpv,
  loadSensitivityThresholds,
  saveSensitivityThresholds,
  type SensitivityThresholds,
} from "@/lib/sensitivity-thresholds";
import { useCollapseState } from "@/lib/use-collapse-state";
import { SensitivityThresholdsControls } from "./sensitivity-thresholds-controls";

import type { ProjectRead, SensitivityCell, SensitivityResponse } from "@/types/api";

interface SensitivityTabProps {
  projectId: number;
}

const PARAM_LABELS: Record<SensitivityCell["parameter"], string> = {
  nd: "Числ. дистр.",
  offtake: "Офтейк",
  shelf_price: "Цена полки",
  cogs: "Себестоимость",
};

const PARAM_ORDER: SensitivityCell["parameter"][] = [
  "nd",
  "offtake",
  "shelf_price",
  "cogs",
];

/** Форматирует delta -0.20 → "−20%", 0 → "Base", +0.20 → "+20%". */
function formatDeltaLabel(delta: number): string {
  if (delta === 0) return "Базовый";
  const sign = delta > 0 ? "+" : "−";
  return `${sign}${Math.abs(delta * 100).toFixed(0)}%`;
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
const SCOPE_OPTIONS = [
  { value: "y1y3", label: "Y1-Y3" },
  { value: "y1y5", label: "Y1-Y5" },
  { value: "y1y10", label: "Y1-Y10" },
];

export function SensitivityTab({ projectId }: SensitivityTabProps) {
  const [data, setData] = useState<SensitivityResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasFetched, setHasFetched] = useState(false);
  const [baseScenarioId, setBaseScenarioId] = useState<number | null>(null);
  const [project, setProject] = useState<ProjectRead | null>(null);
  const [scope, setScope] = useState<string>("y1y10");
  const [thresholds, setThresholds] = useState<SensitivityThresholds>(
    loadSensitivityThresholds,
  );

  function handleThresholdsChange(next: SensitivityThresholds) {
    setThresholds(next);
    saveSensitivityThresholds(next);
  }

  const collapse = useCollapseState(projectId, "sensitivity", SENSITIVITY_SECTIONS);

  // Load project for saved AI commentary
  useEffect(() => {
    getProject(projectId).then(setProject).catch(() => {});
  }, [projectId]);

  // Fetch base scenario ID for AI inline
  useEffect(() => {
    listProjectScenarios(projectId)
      .then((scenarios) => {
        const base = scenarios.find((s) => s.type === "base");
        if (base) setBaseScenarioId(base.id);
      })
      .catch(() => {});
  }, [projectId]);

  const handleCompute = useCallback(async (selectedScope?: string) => {
    const s = selectedScope ?? scope;
    setLoading(true);
    setError(null);
    try {
      const response = await computeSensitivity(projectId, s);
      setData(response);
      setHasFetched(true);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка",
      );
    } finally {
      setLoading(false);
    }
  }, [projectId, scope]);

  // Авто-запуск при монтировании (для UX — пользователь сразу видит данные)
  useEffect(() => {
    void handleCompute();
  }, [handleCompute]);

  return (
    <div className="space-y-6">
      {/* Header + scope selector + кнопка перерасчёта */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-lg font-semibold">Анализ чувствительности</h2>
          <p className="text-sm text-muted-foreground">
            NPV и Contribution Margin при изменении ключевых
            параметров на ±10% и ±20% от Base сценария.
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <SensitivityThresholdsControls
            value={thresholds}
            onChange={handleThresholdsChange}
          />
          {collapse.allOpen ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={collapse.collapseAll}
              disabled={loading}
            >
              <ChevronsDownUp className="mr-1.5 size-3.5" />
              Свернуть всё
            </Button>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              onClick={collapse.expandAll}
              disabled={loading}
            >
              <ChevronsUpDown className="mr-1.5 size-3.5" />
              Развернуть всё
            </Button>
          )}
          <Select
            value={scope}
            onValueChange={(v) => {
              const val = v ?? "y1y10";
              setScope(val);
              void handleCompute(val);
            }}
            items={SCOPE_OPTIONS}
          >
            <SelectTrigger className="w-28">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SCOPE_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button onClick={() => handleCompute()} disabled={loading}>
            {loading ? "Считаем..." : "Пересчитать"}
          </Button>
        </div>
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
          <CollapsibleSection
            sectionId="base-values"
            title="Базовые значения"
            isOpen={collapse.isOpen("base-values")}
            onToggle={() => collapse.toggle("base-values")}
          >
            <Card>
              <CardHeader>
                <CardDescription>
                  Точка отсчёта для всех ячеек ниже (базовый сценарий).
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div>
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">
                      NPV {SCOPE_OPTIONS.find((o) => o.value === scope)?.label ?? scope}
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
          </CollapsibleSection>

          {/* AI interpretation (Phase 7.3) */}
          {baseScenarioId !== null && (
            <CollapsibleSection
              sectionId="ai-interpretation"
              title="AI интерпретация чувствительности"
              isOpen={collapse.isOpen("ai-interpretation")}
              onToggle={() => collapse.toggle("ai-interpretation")}
            >
              <ExplainSensitivityInline
                projectId={projectId}
                projectName={project?.name ?? "Проект"}
                scenarioId={baseScenarioId}
                savedCommentary={project?.ai_sensitivity_commentary as Record<string, unknown> | null}
              />
            </CollapsibleSection>
          )}

          <CollapsibleSection
            sectionId="tornado"
            title="Tornado-диаграмма"
            isOpen={collapse.isOpen("tornado")}
            onToggle={() => collapse.toggle("tornado")}
          >
            <TornadoChart data={data} thresholds={thresholds} />
          </CollapsibleSection>

          <CollapsibleSection
            sectionId="matrix"
            title="Матрица 5 × 4 (NPV / CM%)"
            isOpen={collapse.isOpen("matrix")}
            onToggle={() => collapse.toggle("matrix")}
          >
            <Card>
              <CardHeader>
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
                                className={`font-semibold ${classifyNpv(
                                  cell.npv_y1y10,
                                  data.base_npv_y1y10,
                                  thresholds,
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
                <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
                  <span>Раскраска:</span>
                  <span className="text-green-600 font-semibold">
                    NPV ≥ +{thresholds.greenPct}% от base
                  </span>
                  <span>—</span>
                  <span className="text-red-600 font-semibold">
                    NPV ≤ −{thresholds.redPct}% от base
                  </span>
                  <span>—</span>
                  <span>Нейтральный (в пределах порогов)</span>
                </div>
              </CardContent>
            </Card>
          </CollapsibleSection>
        </>
      )}
    </div>
  );
}
