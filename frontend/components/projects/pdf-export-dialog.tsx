"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { apiGetBlob } from "@/lib/api";
import {
  loadSavedSections,
  saveSections,
  PDF_SECTION_LABELS,
  PDF_SECTION_ORDER,
  type PdfSectionId,
} from "@/lib/pdf-sections";

interface PdfExportDialogProps {
  projectId: number;
  projectName?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function PdfExportDialog({
  projectId,
  projectName,
  open,
  onOpenChange,
}: PdfExportDialogProps) {
  const [selected, setSelected] = useState<Set<PdfSectionId>>(
    new Set(PDF_SECTION_ORDER),
  );
  const [downloading, setDownloading] = useState(false);

  // Restore saved selection when dialog opens
  useEffect(() => {
    if (open) {
      setSelected(new Set(loadSavedSections()));
    }
  }, [open]);

  function toggleSection(id: PdfSectionId) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function selectAll() {
    setSelected(new Set(PDF_SECTION_ORDER));
  }

  function deselectAll() {
    setSelected(new Set());
  }

  const isAllSelected = selected.size === PDF_SECTION_ORDER.length;

  async function handleDownload() {
    if (selected.size === 0) return;
    setDownloading(true);
    try {
      // Preserve order from PDF_SECTION_ORDER
      const arr = PDF_SECTION_ORDER.filter((id) => selected.has(id));
      saveSections(arr);

      const sectionsParam = isAllSelected
        ? ""
        : `?sections=${arr.join(",")}`;
      const url = `/api/projects/${projectId}/export/pdf${sectionsParam}`;

      const blob = await apiGetBlob(url);

      const suffix = isAllSelected ? "" : "_partial";
      const filename = `project_${projectId}${suffix}.pdf`;

      const blobUrl = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = filename;
      a.rel = "noopener";
      document.body.appendChild(a);
      try {
        a.click();
      } finally {
        document.body.removeChild(a);
        setTimeout(() => window.URL.revokeObjectURL(blobUrl), 1000);
      }

      toast.success("PDF скачан");
      onOpenChange(false);
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Неизвестная ошибка";
      toast.error(`Не удалось скачать PDF: ${msg}`);
    } finally {
      setDownloading(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Экспорт PDF</DialogTitle>
          <DialogDescription>
            Выберите секции для включения в PDF
            {projectName ? ` «${projectName}»` : ""}.
            Выбор запоминается для следующего экспорта.
          </DialogDescription>
        </DialogHeader>

        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={selectAll}
            disabled={downloading || isAllSelected}
          >
            Выбрать всё
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={deselectAll}
            disabled={downloading || selected.size === 0}
          >
            Снять всё
          </Button>
        </div>

        <div className="max-h-[50vh] overflow-y-auto space-y-1 pt-2">
          {PDF_SECTION_ORDER.map((id) => (
            <div key={id} className="flex items-center gap-2 py-1">
              <Checkbox
                id={`pdf-section-${id}`}
                checked={selected.has(id)}
                onCheckedChange={() => toggleSection(id)}
                disabled={downloading}
              />
              <label
                htmlFor={`pdf-section-${id}`}
                className="flex-1 text-sm cursor-pointer"
              >
                {PDF_SECTION_LABELS[id]}
              </label>
            </div>
          ))}
        </div>

        <DialogFooter>
          <span className="mr-auto text-sm text-muted-foreground">
            Выбрано: {selected.size} / {PDF_SECTION_ORDER.length}
          </span>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={downloading}
          >
            Отмена
          </Button>
          <Button
            type="button"
            onClick={() => void handleDownload()}
            disabled={downloading || selected.size === 0}
          >
            {downloading ? "Скачивание..." : "Скачать PDF"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
