"use client";

import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api";
import {
  addSkuToProject,
  createSku,
  listSkus,
} from "@/lib/skus";

import type { SKURead } from "@/types/api";

interface AddSkuDialogProps {
  projectId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAdded: () => void;
}

type Mode = "existing" | "new";

/**
 * Диалог добавления SKU к проекту с двумя режимами:
 *  - existing: выбрать SKU из глобального каталога (`GET /api/skus`)
 *  - new: создать новый SKU (POST /api/skus) и сразу привязать к проекту
 *
 * После успешного `addSkuToProject` вызывает `onAdded()` чтобы родительский
 * компонент перезагрузил список и закрывает диалог.
 */
export function AddSkuDialog({
  projectId,
  open,
  onOpenChange,
  onAdded,
}: AddSkuDialogProps) {
  const [mode, setMode] = useState<Mode>("existing");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // existing mode
  const [skus, setSkus] = useState<SKURead[]>([]);
  const [selectedSkuId, setSelectedSkuId] = useState<string>("");

  // new mode
  const [brand, setBrand] = useState("");
  const [name, setName] = useState("");
  const [format, setFormat] = useState("");
  const [volumeL, setVolumeL] = useState("");
  const [packageType, setPackageType] = useState("");

  // Загружаем глобальный каталог при открытии
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    listSkus()
      .then((data) => {
        if (!cancelled) setSkus(data);
      })
      .catch(() => {
        if (!cancelled) setSkus([]);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  // Сброс формы при закрытии
  useEffect(() => {
    if (open) return;
    setError(null);
    setSubmitting(false);
    setSelectedSkuId("");
    setBrand("");
    setName("");
    setFormat("");
    setVolumeL("");
    setPackageType("");
  }, [open]);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      let skuId: number;
      if (mode === "existing") {
        if (!selectedSkuId) {
          setError("Выберите SKU из каталога");
          setSubmitting(false);
          return;
        }
        skuId = Number(selectedSkuId);
      } else {
        const newSku = await createSku({
          brand,
          name,
          format: format || null,
          volume_l: volumeL || null,
          package_type: packageType || null,
          segment: null,
        });
        skuId = newSku.id;
      }
      await addSkuToProject(projectId, { sku_id: skuId });
      onAdded();
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail ?? err.message : "Ошибка");
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Добавить SKU в проект</DialogTitle>
          <DialogDescription>
            Выберите существующий SKU из справочника или создайте новый.
          </DialogDescription>
        </DialogHeader>

        <div className="flex gap-2">
          <Button
            type="button"
            variant={mode === "existing" ? "default" : "outline"}
            size="sm"
            onClick={() => setMode("existing")}
          >
            Из каталога
          </Button>
          <Button
            type="button"
            variant={mode === "new" ? "default" : "outline"}
            size="sm"
            onClick={() => setMode("new")}
          >
            Создать новый
          </Button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {mode === "existing" ? (
            <div className="space-y-2">
              <Label htmlFor="sku-select">SKU из каталога</Label>
              <Select
                value={selectedSkuId}
                onValueChange={(v) => setSelectedSkuId(v ?? "")}
                disabled={submitting}
              >
                <SelectTrigger id="sku-select">
                  <SelectValue placeholder="Выберите..." />
                </SelectTrigger>
                <SelectContent>
                  {skus.map((s) => (
                    <SelectItem key={s.id} value={String(s.id)}>
                      {s.brand} — {s.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {skus.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  Каталог пуст. Создайте новый SKU.
                </p>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              <div className="space-y-2">
                <Label htmlFor="brand">Бренд *</Label>
                <Input
                  id="brand"
                  required
                  value={brand}
                  onChange={(e) => setBrand(e.target.value)}
                  disabled={submitting}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="name">Название *</Label>
                <Input
                  id="name"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={submitting}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="format">Тип упаковки</Label>
                  <Input
                    id="format"
                    value={format}
                    onChange={(e) => setFormat(e.target.value)}
                    disabled={submitting}
                    placeholder="0,5л ПЭТ"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="volume_l">Объём, л</Label>
                  <Input
                    id="volume_l"
                    type="number"
                    step="0.01"
                    min="0"
                    value={volumeL}
                    onChange={(e) => setVolumeL(e.target.value)}
                    disabled={submitting}
                    placeholder="0.5"
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="package_type">Вложение в кейс</Label>
                <Input
                  id="package_type"
                  value={packageType}
                  onChange={(e) => setPackageType(e.target.value)}
                  disabled={submitting}
                  placeholder="6 / 12 / 24 шт"
                />
              </div>
            </div>
          )}

          {error !== null && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              Отмена
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Добавление..." : "Добавить"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
