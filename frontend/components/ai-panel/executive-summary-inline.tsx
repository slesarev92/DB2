"use client";

/**
 * Executive Summary inline block на ResultsTab (Phase 7.4).
 *
 * Flow: generate (с confirmation >5₽) → preview → edit textarea →
 * save to DB → PPT/PDF экспорт подхватывает автоматически.
 */

import { useCallback, useRef, useState } from "react";

import { useAIPanel } from "./ai-panel-context";

import { ApiError, apiPatch, apiPost } from "@/lib/api";
import { formatCostRub } from "@/lib/ai";
import { cn } from "@/lib/utils";

import type { AIModelTier } from "@/types/api";

interface KeyNumber {
  label: string;
  value: string;
}

interface ExecSummaryData {
  title: string;
  bullets: string[];
  key_numbers: KeyNumber[];
  risks_section: string[];
  one_line_summary: string;
  recommendation: "go" | "no-go" | "review";
  confidence: number;
  cost_rub: string;
  model: string;
  cached: boolean;
}

interface Props {
  projectId: number;
  projectName: string;
  /** Текущий сохранённый executive summary из Project (для display). */
  savedSummary: string | null;
  onSaved: () => void;
}

export function ExecutiveSummaryInline({
  projectId,
  projectName,
  savedSummary,
  onSaved,
}: Props) {
  const { pushHistory, refreshUsage } = useAIPanel();
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<ExecSummaryData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [saving, setSaving] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const handleGenerate = useCallback(async () => {
    // Confirmation for >5₽ (Phase 7 решение #6 L4)
    if (
      !window.confirm(
        "Генерация Executive Summary стоит ~10-15₽ (opus). Продолжить?",
      )
    ) {
      return;
    }

    setError(null);
    setData(null);
    setLoading(true);
    const startedAt = Date.now();

    try {
      const resp = await apiPost<ExecSummaryData>(
        `/api/projects/${projectId}/ai/generate-executive-summary`,
        {},
      );
      setData(resp);
      setEditText(resp.one_line_summary + "\n\n" + resp.bullets.join("\n"));
      pushHistory({
        timestamp: new Date().toISOString(),
        feature: "executive_summary",
        model: resp.model,
        cost_rub: resp.cost_rub,
        latency_ms: Date.now() - startedAt,
        project_id: projectId,
        project_name: projectName,
        cached: resp.cached,
      });
      refreshUsage();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка",
      );
    } finally {
      setLoading(false);
    }
  }, [projectId, projectName, pushHistory, refreshUsage]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      await apiPatch(`/api/projects/${projectId}/ai/executive-summary`, {
        ai_executive_summary: editText,
      });
      onSaved();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка сохранения",
      );
    } finally {
      setSaving(false);
    }
  }, [projectId, editText, onSaved]);

  const recBadge = data
    ? data.recommendation === "go"
      ? "🟢 GO"
      : data.recommendation === "no-go"
        ? "🔴 NO-GO"
        : "🟡 REVIEW"
    : null;

  return (
    <div className="rounded-lg border bg-card p-4">
      {/* Title comes from outer CollapsibleSection; only badge remains here */}
      {savedSummary && !data && (
        <div className="flex items-center justify-end">
          <span className="rounded bg-green-100 px-2 py-0.5 text-[10px] text-green-700">
            Сохранён в паспорт
          </span>
        </div>
      )}

      {/* Saved summary preview */}
      {savedSummary && !data && (
        <p className="mt-2 text-xs text-muted-foreground line-clamp-3">
          {savedSummary}
        </p>
      )}

      {/* Generate button */}
      {!data && !loading && (
        <button
          type="button"
          onClick={handleGenerate}
          className="mt-3 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground"
        >
          ✨ {savedSummary ? "Regenerate" : "Сгенерировать"} (~12₽, ~8 сек)
        </button>
      )}

      {loading && (
        <p className="mt-3 text-xs text-muted-foreground">
          Генерируем executive summary через opus... обычно 5-10 секунд.
        </p>
      )}

      {error && (
        <div className="mt-3 rounded-md border border-destructive bg-destructive/5 p-3 text-xs text-destructive">
          {error}
        </div>
      )}

      {/* Generated result */}
      {data && (
        <div className="mt-3 space-y-3">
          {/* Title + recommendation */}
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold">{data.title}</h4>
            <span className="text-xs">{recBadge} ({(data.confidence * 100).toFixed(0)}%)</span>
          </div>

          {/* Key numbers */}
          <div className="flex gap-3">
            {data.key_numbers.map((kn, i) => (
              <div key={i} className="rounded-md bg-muted/50 p-2 text-center text-xs">
                <div className="font-semibold">{kn.value}</div>
                <div className="text-muted-foreground">{kn.label}</div>
              </div>
            ))}
          </div>

          {/* Bullets */}
          <ul className="list-disc space-y-0.5 pl-5 text-xs">
            {data.bullets.map((b, i) => <li key={i}>{b}</li>)}
          </ul>

          {/* Risks */}
          {data.risks_section.length > 0 && (
            <ul className="list-disc space-y-0.5 pl-5 text-xs text-red-700">
              {data.risks_section.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          )}

          {/* Editable textarea */}
          <div>
            <label className="text-xs font-semibold text-muted-foreground">
              Текст для паспорта (редактируйте при необходимости):
            </label>
            <textarea
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              rows={5}
              className="mt-1 w-full rounded-md border bg-background p-2 text-xs"
            />
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleSave}
              disabled={saving || !editText.trim()}
              className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
            >
              {saving ? "Сохраняем..." : "💾 Сохранить в паспорт"}
            </button>
            <button
              type="button"
              onClick={handleGenerate}
              disabled={loading}
              className="rounded-md border px-3 py-1.5 text-xs"
            >
              ♻ Regenerate
            </button>
            <button
              type="button"
              onClick={() => { setData(null); setError(null); }}
              className="rounded-md border px-3 py-1.5 text-xs"
            >
              Закрыть
            </button>
          </div>

          {/* Meta */}
          <div className="text-[10px] text-muted-foreground">
            {data.model} · {formatCostRub(data.cost_rub)}{data.cached ? " · cached" : ""}
          </div>
        </div>
      )}
    </div>
  );
}
