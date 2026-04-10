"use client";

/**
 * Inline AI generation for content fields (Phase 7.6).
 *
 * Small button next to each text field → collapsible panel:
 * user_hint input, tier toggle, generate → editable preview →
 * Apply/Regenerate/Cancel.
 */

import { useCallback, useRef, useState } from "react";

import { useAIPanel } from "@/components/ai-panel/ai-panel-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiPost } from "@/lib/api";
import { formatCostRub } from "@/lib/ai";

interface ContentFieldAIProps {
  projectId: number;
  field: string;
  onApply: (text: string) => void;
}

interface GenerateResult {
  field: string;
  generated_text: string;
  cost_rub: string;
  model: string;
  cached: boolean;
}

export function ContentFieldAI({
  projectId,
  field,
  onApply,
}: ContentFieldAIProps) {
  const { refreshUsage } = useAIPanel();
  const [open, setOpen] = useState(false);
  const [hint, setHint] = useState("");
  const [tier, setTier] = useState<"fast_cheap" | "balanced">("fast_cheap");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<GenerateResult | null>(null);
  const [editText, setEditText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const handleGenerate = useCallback(async () => {
    setError(null);
    setResult(null);
    setLoading(true);

    try {
      const resp = await apiPost<GenerateResult>(
        `/api/projects/${projectId}/ai/generate-content`,
        {
          field,
          user_hint: hint || null,
          tier_override: tier === "fast_cheap" ? null : tier,
        },
      );
      setResult(resp);
      setEditText(resp.generated_text);
      refreshUsage();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail ?? err.message);
      } else {
        setError("Ошибка генерации");
      }
    } finally {
      setLoading(false);
    }
  }, [projectId, field, hint, tier, refreshUsage]);

  const handleApply = useCallback(() => {
    onApply(editText);
    setOpen(false);
    setResult(null);
    setEditText("");
  }, [editText, onApply]);

  const handleCancel = useCallback(() => {
    setOpen(false);
    setResult(null);
    setEditText("");
    setError(null);
  }, []);

  if (!open) {
    return (
      <button
        type="button"
        className="ml-2 inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[11px] text-primary hover:bg-primary/10 transition-colors"
        onClick={() => setOpen(true)}
        title="Сгенерировать AI"
      >
        AI
      </button>
    );
  }

  return (
    <div className="mt-2 rounded-md border border-primary/20 bg-muted/30 p-3 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-primary">AI-генерация: {field}</span>
        <button
          type="button"
          className="text-muted-foreground hover:text-foreground"
          onClick={handleCancel}
        >
          x
        </button>
      </div>

      {/* Before generation */}
      {!result && (
        <>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">
              Подсказка (опционально)
            </label>
            <Input
              value={hint}
              onChange={(e) => setHint(e.target.value)}
              placeholder="Например: акцент на экологичность..."
              className="text-sm"
            />
          </div>

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1 text-xs">
              <button
                type="button"
                className={`rounded px-2 py-1 ${tier === "fast_cheap" ? "bg-primary text-primary-foreground" : "bg-muted"}`}
                onClick={() => setTier("fast_cheap")}
              >
                Haiku (~0.3R)
              </button>
              <button
                type="button"
                className={`rounded px-2 py-1 ${tier === "balanced" ? "bg-primary text-primary-foreground" : "bg-muted"}`}
                onClick={() => setTier("balanced")}
              >
                Sonnet (~1.5R)
              </button>
            </div>

            <Button
              size="sm"
              onClick={handleGenerate}
              disabled={loading}
            >
              {loading ? "Генерация..." : "Сгенерировать"}
            </Button>
          </div>
        </>
      )}

      {/* Error */}
      {error && (
        <p className="text-xs text-destructive">{error}</p>
      )}

      {/* After generation — editable preview */}
      {result && (
        <>
          <Textarea
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            rows={4}
            className="text-sm"
          />
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-muted-foreground">
              {result.model} | {formatCostRub(result.cost_rub)}
              {result.cached ? " | cached" : ""}
            </span>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={handleCancel}>
                Отмена
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={handleGenerate}
                disabled={loading}
              >
                {loading ? "..." : "Заново"}
              </Button>
              <Button size="sm" onClick={handleApply}>
                Применить
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
