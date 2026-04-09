"use client";

import { useCallback, useEffect, useState } from "react";

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
import { downloadProjectXlsx } from "@/lib/export";
import { formatMoney, formatPercent } from "@/lib/format";
import {
  listProjectScenarios,
  listScenarioResults,
} from "@/lib/scenarios";

import type {
  PeriodScope,
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

/** Цветовая индикация для маржи: >25% → зелёный, <25% → красный */
function marginClass(value: string | null): string {
  if (value === null) return "";
  const num = Number(value);
  if (Number.isNaN(num)) return "";
  return num >= 0.25 ? "text-green-600" : "text-red-600";
}

/** Payback из string | null в "N лет" или "НЕ ОКУПАЕТСЯ". */
function formatPayback(value: string | null): string {
  if (value === null) return "НЕ ОКУПАЕТСЯ";
  const num = Number(value);
  if (Number.isNaN(num)) return "—";
  return `${num.toFixed(0)} лет`;
}

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
        </>
      )}
    </div>
  );
}
