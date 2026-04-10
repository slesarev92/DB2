"use client";

import { Fragment, useCallback, useEffect, useState } from "react";

import { ExecutiveSummaryInline } from "@/components/ai-panel/executive-summary-inline";
import { ExplainKpiInline } from "@/components/ai-panel/explain-kpi-inline";
import { GoNoGoBadge } from "@/components/go-no-go-badge";
import { KpiCard } from "@/components/projects/kpi-card";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api";
import { getTaskStatus, recalculateProject } from "@/lib/calculation";
import {
  downloadProjectPdf,
  downloadProjectPptx,
  downloadProjectXlsx,
} from "@/lib/export";
import { formatMoney, formatMoneyPerUnit, formatPercent } from "@/lib/format";
import { getProject } from "@/lib/projects";
import {
  listProjectScenarios,
  listScenarioResults,
} from "@/lib/scenarios";

import type {
  PeriodScope,
  ProjectRead,
  ScenarioRead,
  ScenarioResultRead,
} from "@/types/api";

interface ResultsTabProps {
  projectId: number;
}

const SCENARIO_LABELS: Record<string, string> = {
  base: "Base",
  conservative: "Conservative",
  aggressive: "Aggressive",
};

const SCOPE_LABELS: Record<PeriodScope, string> = {
  y1y3: "Y1-Y3",
  y1y5: "Y1-Y5",
  y1y10: "Y1-Y10",
};

/** Порядок отображения scope'ов в grid'е */
const SCOPE_ORDER: PeriodScope[] = ["y1y3", "y1y5", "y1y10"];

/** 3-tier цветовая индикация для маржи (Phase 8.6).
 *  ≥50% green, 45-50% yellow, <45% red. CM/EBITDA используют
 *  более мягкие пороги (≥25% green, 15-25% yellow, <15% red)
 *  поскольку CM% и EBITDA% существенно ниже GP% по определению. */
function marginClass(value: string | null): string {
  if (value === null) return "";
  const num = Number(value);
  if (Number.isNaN(num)) return "";
  if (num >= 0.25) return "text-green-600";
  if (num >= 0.15) return "text-yellow-600";
  return "text-red-600";
}

/** Payback из string | null в "N лет" или "НЕ ОКУПАЕТСЯ". */
function formatPayback(value: string | null): string {
  if (value === null) return "НЕ ОКУПАЕТСЯ";
  const num = Number(value);
  if (Number.isNaN(num)) return "—";
  return `${num.toFixed(0)} лет`;
}

/** Per-unit row definitions for the table (Phase 8.3). */
interface PerUnitRow {
  key: string;
  label: string;
  unitField: keyof ScenarioResultRead;
  literField: keyof ScenarioResultRead;
  kgField: keyof ScenarioResultRead;
  bold?: boolean;
}

const PER_UNIT_ROWS: PerUnitRow[] = [
  { key: "nr", label: "Выручка (NR)", unitField: "nr_per_unit", literField: "nr_per_liter", kgField: "nr_per_kg", bold: true },
  { key: "gp", label: "Валовая прибыль (GP)", unitField: "gp_per_unit", literField: "gp_per_liter", kgField: "gp_per_kg" },
  { key: "cm", label: "Contribution (CM)", unitField: "cm_per_unit", literField: "cm_per_liter", kgField: "cm_per_kg" },
  { key: "ebitda", label: "EBITDA", unitField: "ebitda_per_unit", literField: "ebitda_per_liter", kgField: "ebitda_per_kg", bold: true },
];

/**
 * Таб "Результаты" в карточке проекта.
 *
 * Показывает KPI Grid по выбранному сценарию (3 scope × NPV/IRR/ROI/
 * Payback + CM% + EBITDA% + Go/No-Go). Кнопка "Пересчитать" запускает
 * Celery task через backend и polling'ует `/api/tasks/{id}` каждую
 * секунду до завершения.
 *
 * Если расчёт ещё не выполнен (GET /scenarios/{id}/results → 404) —
 * показывается placeholder с призывом нажать "Пересчитать".
 */
export function ResultsTab({ projectId }: ResultsTabProps) {
  const [scenarios, setScenarios] = useState<ScenarioRead[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState<number | null>(
    null,
  );
  const [results, setResults] = useState<ScenarioResultRead[] | null>(null);
  const [notCalculated, setNotCalculated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [project, setProject] = useState<ProjectRead | null>(null);

  // Load project for saved AI commentary
  useEffect(() => {
    getProject(projectId).then(setProject).catch(() => {});
  }, [projectId]);

  // Recalculate state
  const [recalculating, setRecalculating] = useState(false);
  const [recalcStatus, setRecalcStatus] = useState<string>("");
  const [recalcError, setRecalcError] = useState<string | null>(null);

  // Export state
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  // Загружаем сценарии
  useEffect(() => {
    let cancelled = false;
    listProjectScenarios(projectId)
      .then((data) => {
        if (cancelled) return;
        setScenarios(data);
        const base = data.find((s) => s.type === "base");
        if (base) setSelectedScenarioId(base.id);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof ApiError ? err.detail ?? err.message : "Ошибка",
        );
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  // Загружаем результаты выбранного сценария
  const loadResults = useCallback(
    async (scenarioId: number) => {
      setLoading(true);
      setNotCalculated(false);
      setResults(null);
      setError(null);
      try {
        const data = await listScenarioResults(scenarioId);
        setResults(data);
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          setNotCalculated(true);
        } else {
          setError(
            err instanceof ApiError ? err.detail ?? err.message : "Ошибка",
          );
        }
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    if (selectedScenarioId === null) return;
    void loadResults(selectedScenarioId);
  }, [selectedScenarioId, loadResults]);

  // Polling helper для task status
  async function pollTaskStatus(
    taskId: string,
    onStatus: (status: string) => void,
  ): Promise<{ ok: boolean; error?: string }> {
    const POLL_INTERVAL = 1000;
    const TIMEOUT_MS = 60_000;
    const start = Date.now();
    while (Date.now() - start < TIMEOUT_MS) {
      const resp = await getTaskStatus(taskId);
      onStatus(resp.status);
      if (resp.status === "SUCCESS") {
        return { ok: true };
      }
      if (resp.status === "FAILURE") {
        return {
          ok: false,
          error: resp.error ?? "Расчёт упал без указания причины",
        };
      }
      await new Promise((r) => setTimeout(r, POLL_INTERVAL));
    }
    return { ok: false, error: "Timeout: расчёт не завершился за 60 секунд" };
  }

  async function handleRecalculate() {
    setRecalcError(null);
    setRecalculating(true);
    setRecalcStatus("PENDING");
    try {
      const { task_id } = await recalculateProject(projectId);
      const result = await pollTaskStatus(task_id, (s) => setRecalcStatus(s));
      if (!result.ok) {
        setRecalcError(result.error ?? "Неизвестная ошибка");
      } else if (selectedScenarioId !== null) {
        // Refetch результаты после успешного расчёта
        await loadResults(selectedScenarioId);
      }
    } catch (err) {
      setRecalcError(
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка",
      );
    } finally {
      setRecalculating(false);
    }
  }

  async function handleExportXlsx() {
    setExportError(null);
    setExporting(true);
    try {
      await downloadProjectXlsx(projectId);
    } catch (err) {
      setExportError(
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка экспорта",
      );
    } finally {
      setExporting(false);
    }
  }

  async function handleExportPptx() {
    setExportError(null);
    setExporting(true);
    try {
      await downloadProjectPptx(projectId);
    } catch (err) {
      setExportError(
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка экспорта",
      );
    } finally {
      setExporting(false);
    }
  }

  async function handleExportPdf() {
    setExportError(null);
    setExporting(true);
    try {
      await downloadProjectPdf(projectId);
    } catch (err) {
      setExportError(
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка экспорта",
      );
    } finally {
      setExporting(false);
    }
  }

  // --- Рендеринг ---

  if (error !== null) {
    return (
      <Card className="border-destructive">
        <CardContent className="pt-6 text-sm text-destructive">
          {error}
        </CardContent>
      </Card>
    );
  }

  // resultsByScope: ключ → ScenarioResult для этого скоупа
  const resultsByScope: Partial<Record<PeriodScope, ScenarioResultRead>> = {};
  if (results !== null) {
    for (const r of results) {
      resultsByScope[r.period_scope] = r;
    }
  }

  // Overall ratios — берём из любого скоупа (contribution_margin и
  // ebitda_margin одинаковые, считаются по всему проекту)
  const anyResult = results !== null && results.length > 0 ? results[0] : null;
  const cmRatio = anyResult?.contribution_margin ?? null;
  const ebitdaMargin = anyResult?.ebitda_margin ?? null;
  const goNoGoY1Y10 = resultsByScope.y1y10?.go_no_go ?? null;

  return (
    <div className="space-y-6">
      {/* Header: scenario selector + Recalculate button */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-2">
          <Label htmlFor="result-scenario">Сценарий</Label>
          <Select
            value={
              selectedScenarioId === null ? "" : String(selectedScenarioId)
            }
            onValueChange={(v) => setSelectedScenarioId(v ? Number(v) : null)}
          >
            <SelectTrigger id="result-scenario" className="w-48">
              <SelectValue placeholder="Сценарий" />
            </SelectTrigger>
            <SelectContent>
              {scenarios.map((s) => (
                <SelectItem key={s.id} value={String(s.id)}>
                  {SCENARIO_LABELS[s.type] ?? s.type}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-3">
          {recalculating && (
            <span className="text-sm text-muted-foreground">
              {recalcStatus === "PENDING" && "В очереди..."}
              {recalcStatus === "STARTED" && "Считаем..."}
              {recalcStatus === "SUCCESS" && "Обновляем..."}
            </span>
          )}
          <Button
            onClick={handleExportXlsx}
            disabled={exporting || recalculating}
            variant="outline"
          >
            {exporting ? "Экспорт..." : "Скачать XLSX"}
          </Button>
          <Button
            onClick={handleExportPptx}
            disabled={exporting || recalculating}
            variant="outline"
          >
            {exporting ? "Экспорт..." : "Скачать PPTX"}
          </Button>
          <Button
            onClick={handleExportPdf}
            disabled={exporting || recalculating}
            variant="outline"
          >
            {exporting ? "Экспорт..." : "Скачать PDF"}
          </Button>
          <Button onClick={handleRecalculate} disabled={recalculating}>
            {recalculating ? "Пересчитываем..." : "Пересчитать"}
          </Button>
        </div>
      </div>

      {recalcError !== null && (
        <Card className="border-destructive">
          <CardContent className="pt-6 text-sm text-destructive">
            Ошибка расчёта: {recalcError}
          </CardContent>
        </Card>
      )}

      {exportError !== null && (
        <Card className="border-destructive">
          <CardContent className="pt-6 text-sm text-destructive">
            {exportError}
          </CardContent>
        </Card>
      )}

      {/* Content */}
      {loading && (
        <p className="text-sm text-muted-foreground">Загрузка...</p>
      )}

      {!loading && notCalculated && (
        <Card>
          <CardContent className="pt-6 space-y-2">
            <p className="text-sm text-muted-foreground">
              Расчёт для этого сценария ещё не выполнен. Нажмите
              «Пересчитать» чтобы запустить pipeline.
            </p>
            <p className="text-xs text-muted-foreground">
              Backend: POST /api/projects/{projectId}/recalculate → Celery
              task → 3 ScenarioResult на каждый сценарий × 3 scope.
            </p>
          </CardContent>
        </Card>
      )}

      {!loading && !notCalculated && results !== null && (
        <>
          {/* Go/No-Go hero */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base">
                    Go/No-Go решение (Y1-Y10)
                  </CardTitle>
                  <CardDescription>
                    NPV ≥ 0 AND Contribution Margin ≥ 25%
                  </CardDescription>
                </div>
                <div className="scale-150 origin-right">
                  <GoNoGoBadge value={goNoGoY1Y10} />
                </div>
              </div>
            </CardHeader>
          </Card>

          {/* AI Explain KPI (Phase 7.2) — под Go/No-Go hero */}
          {selectedScenarioId !== null && (
            <ExplainKpiInline
              projectId={projectId}
              projectName={project?.name ?? "Проект"}
              scenarioId={selectedScenarioId}
              scope="y1y5"
              savedCommentary={project?.ai_kpi_commentary as Record<string, unknown> | null}
            />
          )}

          {/* AI Executive Summary (Phase 7.4) */}
          <ExecutiveSummaryInline
            projectId={projectId}
            projectName="Проект"
            savedSummary={null}
            onSaved={() => {
              /* В 7.5 — refresh project data */
            }}
          />

          {/* NPV row */}
          <div>
            <h3 className="mb-2 text-sm font-semibold text-muted-foreground">
              NPV (чистая приведённая стоимость)
            </h3>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              {SCOPE_ORDER.map((scope) => {
                const r = resultsByScope[scope];
                return (
                  <KpiCard
                    key={scope}
                    label={SCOPE_LABELS[scope]}
                    value={formatMoney(r?.npv ?? null)}
                    valueClassName={
                      r?.npv !== undefined &&
                      r.npv !== null &&
                      Number(r.npv) >= 0
                        ? "text-green-600"
                        : "text-red-600"
                    }
                  />
                );
              })}
            </div>
          </div>

          {/* IRR row */}
          <div>
            <h3 className="mb-2 text-sm font-semibold text-muted-foreground">
              IRR (внутренняя норма доходности)
            </h3>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              {SCOPE_ORDER.map((scope) => {
                const r = resultsByScope[scope];
                return (
                  <KpiCard
                    key={scope}
                    label={SCOPE_LABELS[scope]}
                    value={formatPercent(r?.irr ?? null)}
                  />
                );
              })}
            </div>
          </div>

          {/* ROI row */}
          <div>
            <h3 className="mb-2 text-sm font-semibold text-muted-foreground">
              ROI (возврат на инвестиции)
            </h3>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              {SCOPE_ORDER.map((scope) => {
                const r = resultsByScope[scope];
                return (
                  <KpiCard
                    key={scope}
                    label={SCOPE_LABELS[scope]}
                    value={formatPercent(r?.roi ?? null)}
                  />
                );
              })}
            </div>
          </div>

          {/* Payback row */}
          <div>
            <h3 className="mb-2 text-sm font-semibold text-muted-foreground">
              Payback (срок окупаемости, Y1-Y10)
            </h3>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <KpiCard
                label="Простой"
                value={formatPayback(
                  resultsByScope.y1y10?.payback_simple ?? null,
                )}
              />
              <KpiCard
                label="Дисконтированный"
                value={formatPayback(
                  resultsByScope.y1y10?.payback_discounted ?? null,
                )}
              />
            </div>
          </div>

          {/* Margins row */}
          <div>
            <h3 className="mb-2 text-sm font-semibold text-muted-foreground">
              Маржинальность (overall)
            </h3>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <KpiCard
                label="Contribution Margin"
                value={formatPercent(cmRatio)}
                valueClassName={marginClass(cmRatio)}
                subtitle="Порог Go/No-Go: ≥ 25%"
              />
              <KpiCard
                label="EBITDA Margin"
                value={formatPercent(ebitdaMargin)}
                valueClassName={marginClass(ebitdaMargin)}
              />
            </div>
          </div>

          {/* Per-unit metrics (Phase 8.3) */}
          <div>
            <h3 className="mb-2 text-sm font-semibold text-muted-foreground">
              Per-unit экономика (средняя за период)
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-xs border-collapse">
                <thead>
                  <tr className="border-b">
                    <th className="px-2 py-1.5 text-left font-medium text-muted-foreground">
                      Показатель
                    </th>
                    {SCOPE_ORDER.map((scope) => (
                      <th key={scope} className="px-2 py-1.5 text-right font-medium" colSpan={3}>
                        {SCOPE_LABELS[scope]}
                      </th>
                    ))}
                  </tr>
                  <tr className="border-b">
                    <th />
                    {SCOPE_ORDER.map((scope) => (
                      <Fragment key={scope}>
                        <th className="px-2 py-1 text-right text-[10px] font-medium text-muted-foreground">
                          ₽/шт
                        </th>
                        <th className="px-2 py-1 text-right text-[10px] font-medium text-muted-foreground">
                          ₽/л
                        </th>
                        <th className="px-2 py-1 text-right text-[10px] font-medium text-muted-foreground">
                          ₽/кг
                        </th>
                      </Fragment>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {PER_UNIT_ROWS.map((row) => (
                    <tr key={row.key} className="border-b last:border-0 hover:bg-muted/30">
                      <td className={`px-2 py-1.5 whitespace-nowrap ${row.bold ? "font-medium" : ""}`}>
                        {row.label}
                      </td>
                      {SCOPE_ORDER.map((scope) => {
                        const r = resultsByScope[scope];
                        const u = (r?.[row.unitField] as string | null) ?? null;
                        const l = (r?.[row.literField] as string | null) ?? null;
                        const k = (r?.[row.kgField] as string | null) ?? null;
                        return (
                          <Fragment key={scope}>
                            <td className="px-2 py-1.5 text-right tabular-nums">
                              {formatMoneyPerUnit(u)}
                            </td>
                            <td className="px-2 py-1.5 text-right tabular-nums">
                              {formatMoneyPerUnit(l)}
                            </td>
                            <td className="px-2 py-1.5 text-right tabular-nums">
                              {formatMoneyPerUnit(k)}
                            </td>
                          </Fragment>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          {/* Color legend (Phase 8.6) */}
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span>Цветовая индикация:</span>
            <span className="text-green-600 font-semibold">NPV &ge; 0 / маржа &ge; 25%</span>
            <span className="text-yellow-600 font-semibold">маржа 15-25%</span>
            <span className="text-red-600 font-semibold">NPV &lt; 0 / маржа &lt; 15%</span>
          </div>
        </>
      )}
    </div>
  );
}
