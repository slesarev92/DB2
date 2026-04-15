"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { AddSkuDialog } from "@/components/projects/add-sku-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { deleteProjectSku, listProjectSkus } from "@/lib/skus";

import type { ProjectSKURead } from "@/types/api";

interface SkuPanelProps {
  projectId: number;
  selectedPskId: number | null;
  onSelectPsk: (pskId: number | null) => void;
}

/**
 * Список ProjectSKU проекта с возможностью добавить/удалить и выбрать
 * для просмотра BOM в правой панели.
 *
 * Selection state поднят в родителя (SkusTab) — нужен для координации
 * с BomPanel.
 */
export function SkuPanel({
  projectId,
  selectedPskId,
  onSelectPsk,
}: SkuPanelProps) {
  const [items, setItems] = useState<ProjectSKURead[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [reloadCounter, setReloadCounter] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listProjectSkus(projectId)
      .then((data) => {
        if (!cancelled) {
          setItems(data);
          // Авто-выбираем первый если ничего не выбрано
          if (data.length > 0 && selectedPskId === null) {
            onSelectPsk(data[0].id);
          }
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof ApiError ? err.detail ?? err.message : "Ошибка загрузки",
        );
      });
    return () => {
      cancelled = true;
    };
    // selectedPskId не в deps — иначе бесконечный цикл от auto-select
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, reloadCounter]);

  function reload() {
    setReloadCounter((c) => c + 1);
  }

  const [deletingPskId, setDeletingPskId] = useState<number | null>(null);

  async function handleDeleteConfirmed() {
    if (deletingPskId === null) return;
    const id = deletingPskId;
    setDeletingPskId(null);
    try {
      await deleteProjectSku(id);
      toast.success("SKU удалён");
      if (selectedPskId === id) {
        onSelectPsk(null);
      }
      reload();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка удаления";
      setError(msg);
      toast.error(`Не удалось удалить SKU: ${msg}`);
    }
  }

  return (
    <div className="flex h-full flex-col space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">SKU проекта</h2>
        <Button size="sm" onClick={() => setDialogOpen(true)}>
          + Добавить
        </Button>
      </div>

      {error !== null && (
        <Card className="border-destructive">
          <CardContent className="pt-6 text-sm text-destructive">
            {error}
          </CardContent>
        </Card>
      )}

      {items === null && error === null && (
        <p className="text-sm text-muted-foreground">Загрузка...</p>
      )}

      {items !== null && items.length === 0 && (
        <Card>
          <CardContent className="pt-6 text-sm text-muted-foreground">
            В проекте пока нет SKU. Добавьте первый, чтобы начать
            настройку BOM и каналов.
          </CardContent>
        </Card>
      )}

      {items !== null && items.length > 0 && (
        <div className="space-y-2">
          {items.map((p) => {
            const active = p.id === selectedPskId;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => onSelectPsk(p.id)}
                className={cn(
                  "w-full rounded-md border bg-card p-3 text-left text-card-foreground transition-colors",
                  active
                    ? "border-primary ring-1 ring-primary"
                    : "hover:border-accent-foreground/30",
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">
                      {p.sku.brand} — {p.sku.name}
                    </p>
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">
                      {p.sku.format ?? "—"}
                      {p.sku.volume_l !== null
                        ? ` · ${Number(p.sku.volume_l)} л`
                        : ""}
                      {p.sku.package_type !== null
                        ? ` · ${p.sku.package_type}`
                        : ""}
                    </p>
                  </div>
                  <span
                    role="button"
                    tabIndex={0}
                    className="shrink-0 cursor-pointer rounded px-2 py-1 text-xs text-muted-foreground hover:bg-destructive hover:text-destructive-foreground"
                    onClick={(e) => {
                      e.stopPropagation();
                      setDeletingPskId(p.id);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        e.stopPropagation();
                        setDeletingPskId(p.id);
                      }
                    }}
                  >
                    Удалить
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      )}

      <AddSkuDialog
        projectId={projectId}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onAdded={reload}
      />

      <ConfirmDialog
        open={deletingPskId !== null}
        onConfirm={handleDeleteConfirmed}
        onCancel={() => setDeletingPskId(null)}
        title="Удалить SKU из проекта?"
        description="BOM будет удалён каскадно."
      />
    </div>
  );
}
