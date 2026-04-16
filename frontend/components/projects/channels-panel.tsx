"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  AddChannelDialog,
  EditChannelDialog,
} from "@/components/projects/channel-dialogs";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Tooltip } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api";
import {
  deletePskChannel,
  listProjectSkuChannels,
} from "@/lib/channels";
import { formatPercent } from "@/lib/format";
import {
  useSortableTable,
  sortIndicator,
  sortableHeaderProps,
  type SortableColumn,
} from "@/lib/use-sortable-table";

import type { ProjectSKUChannelRead } from "@/types/api";

const CHANNEL_SORT_COLUMNS: SortableColumn<ProjectSKUChannelRead, string>[] = [
  { key: "channel", accessor: (p) => p.channel.code },
  { key: "nd", accessor: (p) => Number(p.nd_target) },
  { key: "offtake", accessor: (p) => Number(p.offtake_target) },
  { key: "margin", accessor: (p) => Number(p.channel_margin) },
  { key: "shelf", accessor: (p) => Number(p.shelf_price_reg) },
];

interface ChannelsPanelProps {
  pskId: number;
}

/**
 * Список ProjectSKUChannel'ов выбранного PSK с возможностью добавить /
 * редактировать / удалить. После create на backend автоматически
 * генерируется predict-слой (43 PeriodValue × 3 сценария — задача 2.5).
 */
export function ChannelsPanel({ pskId }: ChannelsPanelProps) {
  const [items, setItems] = useState<ProjectSKUChannelRead[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadCounter, setReloadCounter] = useState(0);
  const [addOpen, setAddOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<ProjectSKUChannelRead | null>(
    null,
  );

  useEffect(() => {
    let cancelled = false;
    setItems(null);
    setError(null);
    listProjectSkuChannels(pskId)
      .then((data) => {
        if (!cancelled) setItems(data);
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
  }, [pskId, reloadCounter]);

  function reload() {
    setReloadCounter((c) => c + 1);
  }

  const { sorted: sortedItems, sortState: chSortState, toggleSort: toggleChSort } =
    useSortableTable(items ?? [], CHANNEL_SORT_COLUMNS);

  const [deletingId, setDeletingId] = useState<number | null>(null);

  async function handleDeleteConfirmed() {
    if (deletingId === null) return;
    const id = deletingId;
    setDeletingId(null);
    try {
      await deletePskChannel(id);
      toast.success("Канал отвязан");
      reload();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка";
      setError(msg);
      toast.error(`Не удалось отвязать канал: ${msg}`);
    }
  }

  if (error !== null && items === null) {
    return (
      <Card className="border-destructive">
        <CardContent className="pt-6 text-sm text-destructive">
          {error}
        </CardContent>
      </Card>
    );
  }

  if (items === null) {
    return <p className="text-sm text-muted-foreground">Загрузка...</p>;
  }

  const excludeChannelIds = items.map((p) => p.channel_id);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <div>
              <CardTitle className="text-base">Каналы дистрибуции</CardTitle>
              <CardDescription>
                Параметры SKU в каждом канале сбыта. После добавления
                автоматически создаются 43 × 3 = 129 PeriodValue (predict).
              </CardDescription>
            </div>
            <Button size="sm" onClick={() => setAddOpen(true)}>
              + Привязать канал
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {items.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Каналов пока нет. Привяжите первый, чтобы запустить расчёт.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead {...sortableHeaderProps(toggleChSort, "channel")}>
                    Канал{sortIndicator(chSortState, "channel")}
                  </TableHead>
                  <TableHead {...sortableHeaderProps(toggleChSort, "nd", "text-right")}>
                    ND цель{sortIndicator(chSortState, "nd")}
                  </TableHead>
                  <TableHead {...sortableHeaderProps(toggleChSort, "offtake", "text-right")}>
                    Отгрузка{sortIndicator(chSortState, "offtake")}
                  </TableHead>
                  <TableHead {...sortableHeaderProps(toggleChSort, "margin", "text-right")}>
                    Маржа{sortIndicator(chSortState, "margin")}
                  </TableHead>
                  <TableHead className="text-right">Промо (скидка/доля)</TableHead>
                  <TableHead {...sortableHeaderProps(toggleChSort, "shelf", "text-right")}>
                    Цена полки, ₽{sortIndicator(chSortState, "shelf")}
                  </TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedItems.map((psc) => (
                  <TableRow key={psc.id}>
                    <TableCell className="max-w-[180px]">
                      <Tooltip
                        content={`${psc.channel.code} — ${psc.channel.name}`}
                        side="right"
                      >
                        <div>
                          <div className="font-medium truncate">
                            {psc.channel.code}
                          </div>
                          <div className="text-xs text-muted-foreground truncate">
                            {psc.channel.name}
                          </div>
                        </div>
                      </Tooltip>
                    </TableCell>
                    <TableCell className="text-right">
                      {formatPercent(psc.nd_target)}
                    </TableCell>
                    <TableCell className="text-right">
                      {Number(psc.offtake_target).toLocaleString("ru-RU", {
                        maximumFractionDigits: 2,
                      })}
                    </TableCell>
                    <TableCell className="text-right">
                      {formatPercent(psc.channel_margin)}
                    </TableCell>
                    <TableCell className="text-right text-xs">
                      {formatPercent(psc.promo_discount)} /{" "}
                      {formatPercent(psc.promo_share)}
                    </TableCell>
                    <TableCell className="text-right">
                      {Number(psc.shelf_price_reg).toLocaleString("ru-RU", {
                        maximumFractionDigits: 2,
                      })}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setEditTarget(psc)}
                      >
                        ✎
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setDeletingId(psc.id)}
                      >
                        ×
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {error !== null && (
            <p className="mt-4 text-sm text-destructive" role="alert">
              {error}
            </p>
          )}
        </CardContent>
      </Card>

      <AddChannelDialog
        pskId={pskId}
        open={addOpen}
        onOpenChange={setAddOpen}
        excludeChannelIds={excludeChannelIds}
        onAdded={reload}
      />

      <EditChannelDialog
        pskChannel={editTarget}
        open={editTarget !== null}
        onOpenChange={(open) => {
          if (!open) setEditTarget(null);
        }}
        onSaved={reload}
      />

      <ConfirmDialog
        open={deletingId !== null}
        onConfirm={handleDeleteConfirmed}
        onCancel={() => setDeletingId(null)}
        title="Удалить канал?"
        description="PeriodValue данные будут удалены каскадно."
      />
    </div>
  );
}
