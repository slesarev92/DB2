"use client";

/**
 * Marketing Research секция в content tab (Phase 7.7).
 *
 * Topic cards: generate / edit / delete / regenerate.
 * Warning badge если >7 дней. Confirmation dialog для дорогих вызовов.
 */

import { useCallback, useState } from "react";

import { useAIPanel } from "@/components/ai-panel/ai-panel-context";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api";
import {
  deleteMarketingResearch,
  editMarketingResearch,
  formatCostRub,
  generateMarketingResearch,
} from "@/lib/ai";

import type { ResearchTopic } from "@/types/api";

interface MarketingResearchSectionProps {
  projectId: number;
  /** Current marketing_research JSONB from project. */
  research: Record<string, ResearchTopicData> | null;
  onUpdate: () => void;
}

interface ResearchTopicData {
  text: string;
  sources: Array<{ url: string; title: string; snippet: string }>;
  key_findings?: string[];
  confidence_notes?: string;
  generated_at: string;
  cost_rub: string;
  model: string;
}

const TOPICS: Array<{ key: ResearchTopic; label: string }> = [
  { key: "competitive_analysis", label: "Конкурентный анализ" },
  { key: "market_size", label: "Размер рынка" },
  { key: "consumer_trends", label: "Потребительские тренды" },
  { key: "category_benchmarks", label: "Бенчмарки категории" },
  { key: "custom", label: "Своя тема" },
];

function daysSince(isoDate: string): number {
  const diff = Date.now() - new Date(isoDate).getTime();
  return Math.floor(diff / (1000 * 60 * 60 * 24));
}

export function MarketingResearchSection({
  projectId,
  research,
  onUpdate,
}: MarketingResearchSectionProps) {
  const { refreshUsage } = useAIPanel();
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [customQuery, setCustomQuery] = useState("");

  const handleGenerate = useCallback(
    async (topic: ResearchTopic) => {
      if (topic === "custom" && !customQuery.trim()) return;

      const cost = "~15-25R (opus)";
      if (!window.confirm(`Запустить исследование «${topic}»? Стоимость ${cost}, ~30 сек.`)) {
        return;
      }

      setError(null);
      setLoading(topic);
      try {
        await generateMarketingResearch(
          projectId,
          topic,
          topic === "custom" ? customQuery : null,
        );
        refreshUsage();
        onUpdate();
      } catch (err) {
        setError(
          err instanceof ApiError ? err.detail ?? err.message : "Ошибка генерации",
        );
      } finally {
        setLoading(null);
      }
    },
    [projectId, customQuery, refreshUsage, onUpdate],
  );

  const handleDelete = useCallback(
    async (topic: string) => {
      if (!window.confirm(`Удалить исследование «${topic}»?`)) return;
      try {
        await deleteMarketingResearch(projectId, topic);
        onUpdate();
      } catch (err) {
        setError(err instanceof ApiError ? err.detail ?? err.message : "Ошибка удаления");
      }
    },
    [projectId, onUpdate],
  );

  const handleStartEdit = useCallback((topic: string, text: string) => {
    setEditing(topic);
    setEditText(text);
  }, []);

  const handleSaveEdit = useCallback(
    async (topic: ResearchTopic) => {
      try {
        await editMarketingResearch(projectId, topic, editText);
        setEditing(null);
        onUpdate();
      } catch (err) {
        setError(err instanceof ApiError ? err.detail ?? err.message : "Ошибка сохранения");
      }
    },
    [projectId, editText, onUpdate],
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">8. Marketing Research (AI)</CardTitle>
        <CardDescription>
          Маркетинговые исследования через AI. ~15-25₽ за тему.
          AI использует данные проекта (SKU, категория, ЦА, концепция)
          для генерации контекстных исследований.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && <p className="text-xs text-destructive">{error}</p>}

        {TOPICS.map(({ key, label }) => {
          const data = research?.[key] as ResearchTopicData | undefined;
          const isLoading = loading === key;
          const isEditing = editing === key;
          const days = data ? daysSince(data.generated_at) : 0;

          return (
            <div key={key} className="rounded-md border p-3 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{label}</span>
                <div className="flex items-center gap-2">
                  {data && days > 7 && (
                    <span className="rounded bg-yellow-100 px-1.5 py-0.5 text-[10px] text-yellow-700">
                      {days}д назад
                    </span>
                  )}
                  {data && (
                    <span className="text-[10px] text-muted-foreground">
                      {formatCostRub(data.cost_rub)} | {data.model.split("/").pop()}
                    </span>
                  )}
                </div>
              </div>

              {/* Custom query input */}
              {key === "custom" && !data && (
                <Input
                  value={customQuery}
                  onChange={(e) => setCustomQuery(e.target.value)}
                  placeholder="Введите тему исследования..."
                  className="text-sm"
                />
              )}

              {/* Empty state — generate button */}
              {!data && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleGenerate(key)}
                  disabled={isLoading || (key === "custom" && !customQuery.trim())}
                >
                  {isLoading ? "Генерация..." : "Запустить исследование"}
                </Button>
              )}

              {/* Filled state */}
              {data && !isEditing && (
                <>
                  <p className="text-sm whitespace-pre-line leading-relaxed">
                    {data.text.length > 500
                      ? data.text.slice(0, 500) + "..."
                      : data.text}
                  </p>
                  {data.key_findings && data.key_findings.length > 0 && (
                    <div className="text-xs text-muted-foreground">
                      <span className="font-medium">Key findings: </span>
                      {data.key_findings.join(" | ")}
                    </div>
                  )}
                  {data.confidence_notes && (
                    <p className="text-[10px] text-muted-foreground italic">
                      {data.confidence_notes}
                    </p>
                  )}
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleStartEdit(key, data.text)}
                    >
                      Edit
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleGenerate(key)}
                      disabled={isLoading}
                    >
                      {isLoading ? "..." : "Regenerate"}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleDelete(key)}
                    >
                      Delete
                    </Button>
                  </div>
                </>
              )}

              {/* Edit mode */}
              {data && isEditing && (
                <>
                  <Textarea
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    rows={6}
                    className="text-sm"
                  />
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => handleSaveEdit(key)}>
                      Save
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setEditing(null)}
                    >
                      Cancel
                    </Button>
                  </div>
                </>
              )}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
