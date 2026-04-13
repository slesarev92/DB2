"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";
import {
  deleteMedia,
  getMediaBlobUrl,
  uploadMedia,
} from "@/lib/media";
import { updateProjectSku } from "@/lib/skus";

interface SkuImageUploadProps {
  projectId: number;
  pskId: number;
  /** Текущий `package_image_id` (может быть null, если ещё не загружен). */
  currentImageId: number | null;
  /**
   * Вызывается после успешного upload/delete, чтобы parent обновил state
   * (и заново отобразил новый `package_image_id`).
   */
  onChange: (newImageId: number | null) => void;
}

const ALLOWED_MIME = ["image/png", "image/jpeg", "image/webp"];
const MAX_SIZE_MB = 10;

/**
 * Загрузка изображения упаковки для ProjectSKU.
 *
 * Flow:
 *  1. Клик / drag → POST /api/projects/{id}/media (multipart) → MediaAssetRead
 *  2. PATCH /api/project-skus/{pskId} с package_image_id
 *  3. Parent обновляется через onChange
 *
 * При уже загруженном изображении — показываем preview через Blob URL +
 * кнопки «Заменить» и «Удалить». Delete = DELETE media asset + PATCH PSK
 * со сбросом package_image_id в null (ON DELETE SET NULL в FK — backend
 * тоже сбросит, но делаем явный PATCH чтобы UI state был консистентен
 * без повторного fetch'а PSK).
 */
export function SkuImageUpload({
  projectId,
  pskId,
  currentImageId,
  onChange,
}: SkuImageUploadProps) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Загружаем preview через Blob URL. Revoke в cleanup чтобы не копить
  // blob'ы в памяти браузера.
  useEffect(() => {
    let cancelled = false;
    let urlToRevoke: string | null = null;

    if (currentImageId === null) {
      setPreviewUrl(null);
      return;
    }

    getMediaBlobUrl(currentImageId)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        urlToRevoke = url;
        setPreviewUrl(url);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof ApiError
            ? err.detail ?? err.message
            : "Не удалось загрузить превью",
        );
      });

    return () => {
      cancelled = true;
      if (urlToRevoke !== null) URL.revokeObjectURL(urlToRevoke);
    };
  }, [currentImageId]);

  async function handleFile(file: File) {
    setError(null);
    if (!ALLOWED_MIME.includes(file.type)) {
      setError(`Разрешены только ${ALLOWED_MIME.join(", ")}`);
      return;
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      setError(`Файл больше ${MAX_SIZE_MB} MB`);
      return;
    }

    setUploading(true);
    try {
      const asset = await uploadMedia(projectId, file, "package_image");
      await updateProjectSku(pskId, { package_image_id: asset.id });
      onChange(asset.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка загрузки");
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete() {
    if (currentImageId === null) return;
    setError(null);
    setUploading(true);
    try {
      await updateProjectSku(pskId, { package_image_id: null });
      await deleteMedia(currentImageId);
      onChange(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка удаления");
    } finally {
      setUploading(false);
    }
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) void handleFile(file);
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) void handleFile(file);
    // reset чтобы тот же файл можно было перезагрузить
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  return (
    <div className="space-y-2">
      <Label>Изображение упаковки</Label>
      <p className="text-[11px] text-muted-foreground">
        Загрузите фото/рендер упаковки (PNG/JPG до 10 МБ) или сгенерируйте AI-мокап ниже.
      </p>

      {previewUrl ? (
        <div className="flex items-start gap-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={previewUrl}
            alt="package preview"
            className="h-32 w-32 rounded-md border border-border object-cover"
          />
          <div className="flex flex-col gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              Заменить
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleDelete}
              disabled={uploading}
            >
              Удалить
            </Button>
          </div>
        </div>
      ) : (
        <div
          onClick={() => fileInputRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
          className="flex h-32 cursor-pointer items-center justify-center rounded-md border-2 border-dashed border-border text-sm text-muted-foreground hover:border-ring hover:bg-accent/40"
        >
          {uploading
            ? "Загрузка..."
            : "Перетащите файл или нажмите (PNG/JPEG/WebP, ≤10 MB)"}
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept={ALLOWED_MIME.join(",")}
        onChange={handleChange}
        className="hidden"
      />

      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
