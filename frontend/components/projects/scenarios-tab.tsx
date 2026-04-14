"use client";

import { useCallback, useEffect, useState } from "react";

import { ChannelDeltasEditor } from "@/components/projects/channel-deltas-editor";
import { GoNoGoBadge } from "@/components/go-no-go-badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { HelpButton } from "@/components/ui/help-button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError } from "@/lib/api";
import { getTaskStatus, recalculateProject } from "@/lib/calculation";
import { formatMoney, formatPercent } from "@/lib/format";
import {
  listProjectScenarios,
  listScenarioResults,
  updateScenario,
} from "@/lib/scenarios";

import { SCENARIO_LABELS } from "@/types/api";
import type {
  PeriodScope,
  ScenarioRead,
  ScenarioResultRead,
  ScenarioType,
} from "@/types/api";

interface ScenariosTabProps {
  projectId: number;
}

// SCENARIO_LABELS теперь единый в types/api.ts — импортируется ниже.

const SCENARIO_ORDER: ScenarioType[] = ["base", "conservative", "aggressive"];

const SCOPE_LABELS: Record<PeriodScope, string> = {
  y1y3: "Y1-Y3",
  y1y5: "Y1-Y5",
  y1y10: "Y1-Y10",
};

const SCOPE_ORDER: PeriodScope[] = ["y1y3", "y1y5", "y1y10"];

/** Локальное состояние дельт сценария — храним как строки для удобства inputs. */
interface DeltaDraft {
  delta_nd: string;
  delta_offtake: string;
  delta_opex: string;
}

/** Конвертация % (UI ввод) в долю (БД хранение). "−10" → -0.10. */
function pctToFraction(s: string): string {
  const trimmed = s.trim().replace(",", ".");
  if (trimmed === "" || trimmed === "-") return "0";
  const num = Number(trimmed);
  if (Number.isNaN(num)) return "0";
  return (num / 100).toString();
}

/** Конвертация доли (БД) в % (UI). "0.10" → "10". */
function fractionToPct(s: string): string {
  const num = Number(s);
  if (Number.isNaN(num)) return "0";
  return (num * 100).toString();
}

function deltaFromScenario(s: ScenarioRead): DeltaDraft {
  return {
    delta_nd: fractionToPct(s.delta_nd),
    delta_offtake: fractionToPct(s.delta_offtake),
    delta_opex: fractionToPct(s.delta_opex),
  };
}

/** Дельта в "зелёный/красный" по знаку. */
function deltaClass(value: number | null): string {
  if (value === null || value === 0) return "";
  return value > 0 ? "text-green-600" : "text-red-600";
}

/** Форматирует absolute дельту в "+X ₽" / "−X ₽". */
function formatAbsDelta(value: number | null): string {
  if (value === null) return "—";
  const sign = value > 0 ? "+" : "";
  const fmt = new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: 0,
  }).format(value);
  return `${sign}${fmt} ₽`;
}

/** Форматирует % дельту в "+X%" / "−X%". */
function formatPctDelta(value: number | null): string {
  if (value === null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%`;
}

/**
 * Таб "Сценарии" в карточке проекта.
 *
 * Показывает 3 сценария (Base / Conservative / Aggressive) с их дельтами
 * и compare-таблицей KPI по 3 scope. Позволяет редактировать дельты
 * Conservative и Aggressive (Base всегда 0). Кнопка "Применить и
 * пересчитать" PATCH'ит дельты и запускает recalculate с polling.
 *
 * Backend готов из задач 1.6 (Scenarios API) и 2.4 (recalculate task).
 */
export function ScenariosTab({ projectId }: ScenariosTabProps) {
  const [scenarios, setScenarios] = useState<ScenarioRead[]>([]);
  // Map scenario_id → результаты по 3 scope
  const [resultsByScenario, setResultsByScenario] = useState<
    Record<number, ScenarioResultRead[]>
  >({});
  const [notCalculated, setNotCalculated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Локальные draft'ы дельт (Conservative/Aggressive)
  const [drafts, setDrafts] = useState<Record<number, DeltaDraft>>({});

  // Recalculate state
  const [recalculating, setRecalculating] = useState(false);
  const [recalcStatus, setRecalcStatus] = useState<string>("");
  const [recalcError, setRecalcError] = useState<string | null>(null);

  // Загрузка сценариев + всех результатов
  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    setNotCalculated(false);
    try {
      const sList = await listProjectScenarios(projectId);
      setScenarios(sList);
      // Заполняем drafts дельтами из БД
      const newDrafts: Record<number, DeltaDraft> = {};
      for (const s of sList) {
        newDrafts[s.id] = deltaFromScenario(s);
      }
      setDrafts(newDrafts);

      // Подгружаем результаты для каждого сценария
      const resultsMap: Record<number, ScenarioResultRead[]> = {};
      let anyMissing = false;
      for (const s of sList) {
        try {
          const res = await listScenarioResults(s.id);
          resultsMap[s.id] = res;
        } catch (err) {
          // 404 = не рассчитан; другие ошибки — тоже пропускаем
          // чтобы не блокировать UI из-за одного сбойного сценария
          anyMissing = true;
        }
      }
      setResultsByScenario(resultsMap);
      setNotCalculated(anyMissing);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка",
      );
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  // Polling helper
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
      if (resp.status === "SUCCESS") return { ok: true };
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

  /** Применяет drafts → PATCH дельт → recalculate → poll → reload. */
  async function handleApplyAndRecalc() {
    setRecalcError(null);
    setRecalculating(true);
    setRecalcStatus("PENDING");
    try {
      // PATCH дельты для всех scenarios (только conservative/aggressive)
      for (const s of scenarios) {
        if (s.type === "base") continue;
        const draft = drafts[s.id];
        if (draft === undefined) continue;
        await updateScenario(s.id, {
          delta_nd: pctToFraction(draft.delta_nd),
          delta_offtake: pctToFraction(draft.delta_offtake),
          delta_opex: pctToFraction(draft.delta_opex),
        });
      }
      // Recalculate
      const { task_id } = await recalculateProject(projectId);
      const result = await pollTaskStatus(task_id, (s) => setRecalcStatus(s));
      if (!result.ok) {
        setRecalcError(result.error ?? "Неизвестная ошибка");
      } else {
        await loadAll();
      }
    } catch (err) {
      setRecalcError(
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка",
      );
    } finally {
      setRecalculating(false);
    }
  }

  function updateDraft(
    scenarioId: number,
    key: keyof DeltaDraft,
    value: string,
  ) {
    setDrafts((prev) => ({
      ...prev,
      [scenarioId]: {
        ...(prev[scenarioId] ?? { delta_nd: "0", delta_offtake: "0", delta_opex: "0" }),
        [key]: value,
      },
    }));
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

  if (loading) {
    return <p className="text-sm text-muted-foreground">Загрузка...</p>;
  }

  // Сортированные сценарии по типу
  const sortedScenarios = [...scenarios].sort(
    (a, b) =>
      SCENARIO_ORDER.indexOf(a.type) - SCENARIO_ORDER.indexOf(b.type),
  );

  // base scenario для расчёта дельт KPI
  const baseScenario = sortedScenarios.find((s) => s.type === "base");
  const baseResults =
    baseScenario !== undefined ? resultsByScenario[baseScenario.id] ?? null : null;

  /** Helper: result для (scenario × scope) или null. */
  function getResult(
    scenarioId: number,
    scope: PeriodScope,
  ): ScenarioResultRead | null {
    const list = resultsByScenario[scenarioId];
    if (!list) return null;
    return list.find((r) => r.period_scope === scope) ?? null;
  }

  /** Helper: дельта значения относительно Base в абсолюте + %. */
  function deltaVsBase(
    scenarioId: number,
    scope: PeriodScope,
    field: "npv" | "irr" | "roi",
  ): { abs: number | null; pct: number | null } {
    const r = getResult(scenarioId, scope);
    if (r === null || baseScenario === undefined) {
      return { abs: null, pct: null };
    }
    if (scenarioId === baseScenario.id) {
      return { abs: 0, pct: 0 };
    }
    const baseR = getResult(baseScenario.id, scope);
    if (baseR === null) return { abs: null, pct: null };
    const v = r[field];
    const bv = baseR[field];
    if (v === null || bv === null) return { abs: null, pct: null };
    const vNum = Number(v);
    const bNum = Number(bv);
    if (Number.isNaN(vNum) || Number.isNaN(bNum)) {
      return { abs: null, pct: null };
    }
    const abs = vNum - bNum;
    const pct = bNum !== 0 ? (abs / Math.abs(bNum)) * 100 : null;
    return { abs, pct };
  }

  return (
    <div className="space-y-6">
      {/* === Header: action button === */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Сценарии и сравнение</h2>
          <p className="text-sm text-muted-foreground">
            Conservative и Aggressive — отклонения от Base в % по ND, offtake
            и OPEX. Применяются runtime в pipeline.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {recalculating && (
            <span className="text-sm text-muted-foreground">
              {recalcStatus === "PENDING" && "В очереди..."}
              {recalcStatus === "STARTED" && "Считаем..."}
              {recalcStatus === "SUCCESS" && "Обновляем..."}
            </span>
          )}
          <Button onClick={handleApplyAndRecalc} disabled={recalculating}>
            {recalculating ? "Пересчитываем..." : "Применить и пересчитать"}
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

      {/* === Editor дельт сценариев === */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Дельты сценариев (% к Base)</CardTitle>
          <CardDescription>
            Дельты применяются к показателям базового (Base) сценария.
            Например, +10% ND означает что все значения числовой дистрибуции
            увеличиваются на 10%. Conservative обычно отрицательные дельты,
            Aggressive — положительные.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {sortedScenarios.map((s) => {
              const isBase = s.type === "base";
              const draft = drafts[s.id];
              return (
                <div
                  key={s.id}
                  className="space-y-3 rounded-md border p-3"
                >
                  <p className="text-sm font-semibold">
                    {SCENARIO_LABELS[s.type]}
                  </p>
                  <div className="space-y-2">
                    <Label
                      htmlFor={`delta-nd-${s.id}`}
                      className="flex items-center gap-1.5 text-xs text-muted-foreground"
                    >
                      ND, %
                      <HelpButton help="scenario.delta_nd" />
                    </Label>
                    <Input
                      id={`delta-nd-${s.id}`}
                      type="number"
                      step="0.1"
                      value={draft?.delta_nd ?? "0"}
                      onChange={(e) =>
                        updateDraft(s.id, "delta_nd", e.target.value)
                      }
                      disabled={isBase || recalculating}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label
                      htmlFor={`delta-off-${s.id}`}
                      className="flex items-center gap-1.5 text-xs text-muted-foreground"
                    >
                      Off-take, %
                      <HelpButton help="scenario.delta_offtake" />
                    </Label>
                    <Input
                      id={`delta-off-${s.id}`}
                      type="number"
                      step="0.1"
                      value={draft?.delta_offtake ?? "0"}
                      onChange={(e) =>
                        updateDraft(s.id, "delta_offtake", e.target.value)
                      }
                      disabled={isBase || recalculating}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label
                      htmlFor={`delta-opex-${s.id}`}
                      className="flex items-center gap-1.5 text-xs text-muted-foreground"
                    >
                      OPEX, %
                      <HelpButton help="scenario.delta_opex" />
                    </Label>
                    <Input
                      id={`delta-opex-${s.id}`}
                      type="number"
                      step="0.1"
                      value={draft?.delta_opex ?? "0"}
                      onChange={(e) =>
                        updateDraft(s.id, "delta_opex", e.target.value)
                      }
                      disabled={isBase || recalculating}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* === B-06: Per-channel delta overrides === */}
      <ChannelDeltasEditor projectId={projectId} />

      {/* === Compare таблица: KPI × scenarios для каждого scope === */}
      {notCalculated && baseResults === null ? (
        <Card>
          <CardContent className="pt-6 space-y-2">
            <p className="text-sm text-muted-foreground">
              Расчёт ещё не выполнен. Нажмите «Применить и пересчитать»
              чтобы запустить pipeline для всех 3 сценариев.
            </p>
          </CardContent>
        </Card>
      ) : (
        SCOPE_ORDER.map((scope) => (
          <Card key={scope}>
            <CardHeader>
              <CardTitle className="text-base">
                Сравнение KPI · {SCOPE_LABELS[scope]}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>KPI</TableHead>
                    {sortedScenarios.map((s) => (
                      <TableHead
                        key={s.id}
                        className="text-right"
                        colSpan={s.type === "base" ? 1 : 2}
                      >
                        {SCENARIO_LABELS[s.type]}
                        {s.type !== "base" && (
                          <span className="ml-1 text-xs font-normal text-muted-foreground">
                            (Δ к Base)
                          </span>
                        )}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {/* NPV */}
                  <TableRow>
                    <TableCell className="font-medium">NPV</TableCell>
                    {sortedScenarios.map((s) => {
                      const r = getResult(s.id, scope);
                      const d = deltaVsBase(s.id, scope, "npv");
                      const npvNum = r?.npv != null ? Number(r.npv) : NaN;
                      return (
                        <TableValuePair
                          key={s.id}
                          formattedValue={formatMoney(r?.npv ?? null)}
                          isBase={s.type === "base"}
                          deltaAbs={d.abs}
                          deltaPct={d.pct}
                          formatDeltaAbs={formatAbsDelta}
                          valueClassName={!Number.isNaN(npvNum) ? (npvNum >= 0 ? "text-green-600" : "text-red-600") : ""}
                        />
                      );
                    })}
                  </TableRow>

                  {/* IRR */}
                  <TableRow>
                    <TableCell className="font-medium">IRR</TableCell>
                    {sortedScenarios.map((s) => {
                      const r = getResult(s.id, scope);
                      const d = deltaVsBase(s.id, scope, "irr");
                      // Для IRR delta_abs показываем в pp (процентных пунктах)
                      return (
                        <TableValuePair
                          key={s.id}
                          formattedValue={formatPercent(r?.irr ?? null)}
                          isBase={s.type === "base"}
                          deltaAbs={d.abs !== null ? d.abs * 100 : null}
                          deltaPct={d.pct}
                          formatDeltaAbs={(v) =>
                            v === null
                              ? "—"
                              : `${v > 0 ? "+" : ""}${v.toFixed(2)}pp`
                          }
                        />
                      );
                    })}
                  </TableRow>

                  {/* ROI */}
                  <TableRow>
                    <TableCell className="font-medium">ROI</TableCell>
                    {sortedScenarios.map((s) => {
                      const r = getResult(s.id, scope);
                      const d = deltaVsBase(s.id, scope, "roi");
                      return (
                        <TableValuePair
                          key={s.id}
                          formattedValue={formatPercent(r?.roi ?? null)}
                          isBase={s.type === "base"}
                          deltaAbs={d.abs !== null ? d.abs * 100 : null}
                          deltaPct={d.pct}
                          formatDeltaAbs={(v) =>
                            v === null
                              ? "—"
                              : `${v > 0 ? "+" : ""}${v.toFixed(2)}pp`
                          }
                        />
                      );
                    })}
                  </TableRow>

                  {/* Go/No-Go (только для y1y10 — финальное решение) */}
                  {scope === "y1y10" && (
                    <TableRow>
                      <TableCell className="font-medium">Go/No-Go</TableCell>
                      {sortedScenarios.map((s) => {
                        const r = getResult(s.id, scope);
                        return (
                          <TableCell
                            key={s.id}
                            className="text-right"
                            colSpan={s.type === "base" ? 1 : 2}
                          >
                            <GoNoGoBadge value={r?.go_no_go ?? null} />
                          </TableCell>
                        );
                      })}
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        ))
      )}

      {/* Color legend (Phase 8.6) */}
      {!loading && Object.keys(resultsByScenario).length > 0 && (
        <div className="flex items-center gap-4 text-xs text-muted-foreground mt-2">
          <span>Цвет:</span>
          <span className="text-green-600 font-semibold">NPV &ge; 0 / дельта положительная</span>
          <span className="text-red-600 font-semibold">NPV &lt; 0 / дельта отрицательная</span>
        </div>
      )}
    </div>
  );
}

/**
 * Helper-компонент: рисует одну ячейку (или две для не-Base сценариев) —
 * абсолютное значение и дельту к Base.
 */
function TableValuePair({
  formattedValue,
  isBase,
  deltaAbs,
  deltaPct,
  formatDeltaAbs,
  valueClassName,
}: {
  formattedValue: string;
  isBase: boolean;
  deltaAbs: number | null;
  deltaPct: number | null;
  formatDeltaAbs: (v: number | null) => string;
  valueClassName?: string;
}) {
  if (isBase) {
    return <TableCell className={`text-right ${valueClassName ?? ""}`}>{formattedValue}</TableCell>;
  }
  return (
    <>
      <TableCell className={`text-right ${valueClassName ?? ""}`}>{formattedValue}</TableCell>
      <TableCell className={`text-right text-xs ${deltaClass(deltaAbs)}`}>
        <div>{formatDeltaAbs(deltaAbs)}</div>
        <div className="text-muted-foreground">
          {formatPctDelta(deltaPct)}
        </div>
      </TableCell>
    </>
  );
}
