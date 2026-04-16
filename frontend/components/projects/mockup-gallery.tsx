"use client";

/**
 * Mockup gallery per SKU (Phase 7.8).
 *
 * Upload reference image (logo) → generate mockup (~13₽) → browse gallery →
 * set as primary package image.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { useAIPanel } from "@/components/ai-panel/ai-panel-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiPost } from "@/lib/api";
import {
  formatCostRub,
  generatePackageMockup,
  listMockups,
  setMockupAsPrimary,
} from "@/lib/ai";

import type { AIGeneratedImageRead } from "@/types/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface MockupGalleryProps {
  projectId: number;
  projectSkuId: number;
  skuLabel: string;
  currentPackageImageId: number | null;
  onPrimaryChanged: (mediaAssetId: number) => void;
}

export function MockupGallery({
  projectId,
  projectSkuId,
  skuLabel,
  currentPackageImageId,
  onPrimaryChanged,
}: MockupGalleryProps) {
  const { refreshUsage } = useAIPanel();
  const [mockups, setMockups] = useState<AIGeneratedImageRead[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [referenceAssetId, setReferenceAssetId] = useState<number | null>(null);
  const [referenceUploading, setReferenceUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load gallery
  const loadGallery = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listMockups(projectId, projectSkuId);
      setMockups(data);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, [projectId, projectSkuId]);

  useEffect(() => {
    loadGallery();
  }, [loadGallery]);

  // Upload reference image
  const handleUploadReference = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;

      setReferenceUploading(true);
      setError(null);
      try {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("kind", "ai_reference");
        const resp = await apiPost<{ id: number }>(
          `/api/projects/${projectId}/media`,
          formData,
        );
        setReferenceAssetId(resp.id);
      } catch (err) {
        setError(
          err instanceof ApiError ? err.detail ?? err.message : "Ошибка загрузки",
        );
      } finally {
        setReferenceUploading(false);
      }
    },
    [projectId],
  );

  // Generate mockup
  const handleGenerate = useCallback(async () => {
    if (!prompt.trim()) return;
    if (
      !window.confirm(
        `Генерация mockup: ~13₽ (vision + flux), ~30 сек. Продолжить?`,
      )
    ) {
      return;
    }

    setGenerating(true);
    setError(null);
    try {
      await generatePackageMockup(
        projectId,
        projectSkuId,
        prompt,
        referenceAssetId,
      );
      refreshUsage();
      await loadGallery();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка генерации",
      );
    } finally {
      setGenerating(false);
    }
  }, [projectId, projectSkuId, prompt, referenceAssetId, refreshUsage, loadGallery]);

  // Set as primary
  const handleSetPrimary = useCallback(
    async (mockupId: number) => {
      try {
        const resp = await setMockupAsPrimary(projectId, mockupId);
        onPrimaryChanged(resp.package_image_id);
      } catch (err) {
        setError(err instanceof ApiError ? err.detail ?? err.message : "Ошибка");
      }
    },
    [projectId, onPrimaryChanged],
  );

  return (
    <div className="space-y-3">
      <div className="text-sm font-medium">AI Mockup: {skuLabel}</div>

      {error && <p className="text-xs text-destructive">{error}</p>}

      {/* Reference upload */}
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={() => fileInputRef.current?.click()}
          disabled={referenceUploading}
        >
          {referenceUploading
            ? "Загрузка..."
            : referenceAssetId
              ? "Reference загружен"
              : "Загрузить reference (логотип)"}
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={handleUploadReference}
        />
        {referenceAssetId && (
          <img
            src={`${API_URL}/api/media/${referenceAssetId}`}
            alt="Reference"
            className="h-8 w-8 rounded border object-cover"
          />
        )}
      </div>

      {/* Prompt + generate */}
      <div className="space-y-2">
        <Textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={2}
          placeholder="Опишите желаемый mockup упаковки..."
          className="text-sm"
        />
        <Button
          size="sm"
          onClick={handleGenerate}
          disabled={generating || !prompt.trim()}
        >
          {generating ? "Генерация (~30 сек)..." : "Сгенерировать (~13R)"}
        </Button>
      </div>

      {/* Gallery */}
      {loading && <p className="text-xs text-muted-foreground">Загрузка...</p>}

      {mockups.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {mockups.map((m) => {
            const isPrimary = m.media_asset_id === currentPackageImageId;
            return (
              <div
                key={m.id}
                className={`rounded-md border p-2 space-y-1 ${isPrimary ? "border-primary ring-1 ring-primary" : ""}`}
              >
                <img
                  src={`${API_URL}${m.media_url}`}
                  alt={m.prompt_text}
                  className="aspect-square w-full rounded object-cover bg-muted"
                />
                <div className="text-[10px] text-muted-foreground truncate">
                  {m.prompt_text}
                </div>
                <div className="text-[10px] text-muted-foreground">
                  {m.cost_rub ? formatCostRub(m.cost_rub) : "—"} |{" "}
                  {new Date(m.created_at).toLocaleDateString("ru-RU")}
                </div>
                <div className="flex gap-1">
                  {isPrimary ? (
                    <span className="text-[10px] text-primary font-medium">
                      Основное
                    </span>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-6 text-[10px] px-2"
                      onClick={() => handleSetPrimary(m.id)}
                    >
                      Сделать основным
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {!loading && mockups.length === 0 && (
        <p className="text-xs text-muted-foreground">
          Нет mockup-ов. Загрузите reference и нажмите «Сгенерировать».
        </p>
      )}
    </div>
  );
}
