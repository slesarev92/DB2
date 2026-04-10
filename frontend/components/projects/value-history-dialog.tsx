"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  type PeriodValueHistoryEntry,
  getPeriodValueHistory,
} from "@/lib/period-values";

interface ValueHistoryDialogProps {
  pskChannelId: number;
  periodId: number;
  scenarioId: number;
  periodLabel: string;
}

const SOURCE_LABELS: Record<string, string> = {
  predict: "Predict",
  finetuned: "Fine-tuned",
  actual: "Actual",
};

const SOURCE_COLORS: Record<string, string> = {
  predict: "text-blue-600",
  finetuned: "text-amber-600",
  actual: "text-green-600",
};

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Dialog с историей версий PeriodValue (B-10).
 *
 * Показывает все версии (predict, finetuned v1..vN, actual) для
 * конкретного (psk_channel × scenario × period). Кнопка-триггер
 * встраивается в PeriodsGrid.
 */
export function ValueHistoryDialog({
  pskChannelId,
  periodId,
  scenarioId,
  periodLabel,
}: ValueHistoryDialogProps) {
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<PeriodValueHistoryEntry[] | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setEntries(null);
    setError(null);
    getPeriodValueHistory(pskChannelId, periodId, scenarioId)
      .then(setEntries)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Ошибка"),
      );
  }, [open, pskChannelId, periodId, scenarioId]);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger>
        <Button variant="ghost" size="sm" className="text-xs px-1 h-6">
          ...
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>История версий — {periodLabel}</DialogTitle>
          <DialogDescription>
            Все версии значений для этого периода. Append-only: каждое
            редактирование создаёт новую версию.
          </DialogDescription>
        </DialogHeader>

        {error !== null && (
          <p className="text-sm text-destructive">{error}</p>
        )}

        {entries === null && error === null && (
          <p className="text-sm text-muted-foreground">Загрузка...</p>
        )}

        {entries !== null && entries.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Нет данных для этого периода.
          </p>
        )}

        {entries !== null && entries.length > 0 && (
          <div className="max-h-80 overflow-y-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Слой</TableHead>
                  <TableHead>v</TableHead>
                  <TableHead>Значения</TableHead>
                  <TableHead>Дата</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {entries.map((e, i) => (
                  <TableRow key={i}>
                    <TableCell
                      className={`text-xs font-medium ${SOURCE_COLORS[e.source_type] ?? ""}`}
                    >
                      {SOURCE_LABELS[e.source_type] ?? e.source_type}
                    </TableCell>
                    <TableCell className="text-xs">{e.version_id}</TableCell>
                    <TableCell className="text-xs">
                      {Object.entries(e.values)
                        .map(
                          ([k, v]) =>
                            `${k}: ${typeof v === "number" ? v.toFixed(4) : v}`,
                        )
                        .join(", ")}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatDateTime(e.created_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
