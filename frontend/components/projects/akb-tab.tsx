"use client";

import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { FieldError } from "@/components/ui/field-error";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { ApiError } from "@/lib/api";
import {
  createAkbEntry,
  deleteAkbEntry,
  listAkbEntries,
} from "@/lib/akb";
import { listChannels } from "@/lib/channels";
import { formatPercent } from "@/lib/format";
import {
  useFieldValidation,
  type ValidationRules,
} from "@/lib/use-field-validation";
import {
  useSortableTable,
  sortIndicator,
  type SortableColumn,
} from "@/lib/use-sortable-table";

import type { AKBRead, Channel } from "@/types/api";

const AKB_SORT_COLUMNS: SortableColumn<AKBRead, string>[] = [
  { key: "channel", accessor: (e) => `${e.channel.code} — ${e.channel.name}` },
  { key: "universe", accessor: (e) => e.universe_outlets },
  { key: "target", accessor: (e) => e.target_outlets },
  { key: "coverage", accessor: (e) => (e.coverage_pct !== null ? Number(e.coverage_pct) : null) },
  {
    key: "wd",
    accessor: (e) =>
      e.weighted_distribution !== null ? Number(e.weighted_distribution) : null,
  },
];

type AkbField = "channel_id" | "universe" | "target" | "coverage";

const AKB_RULES: ValidationRules<AkbField> = {
  channel_id: { required: true, message: "Выберите канал" },
  universe: { numeric: true, min: 0 },
  target: { numeric: true, min: 0 },
  coverage: { numeric: true, min: 0, max: 1 },
};

interface AkbTabProps {
  projectId: number;
}

export function AkbTab({ projectId }: AkbTabProps) {
  const [entries, setEntries] = useState<AKBRead[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Add form
  const [selectedChannelId, setSelectedChannelId] = useState("");
  const [universe, setUniverse] = useState("");
  const [target, setTarget] = useState("");
  const [coverage, setCoverage] = useState("");
  const [adding, setAdding] = useState(false);
  const akbRules = useMemo(() => AKB_RULES, []);
  const { errors: akbErrors, validateAll: validateAkb, clearError: clearAkbError } =
    useFieldValidation<AkbField>(akbRules);

  async function load() {
    setLoading(true);
    try {
      const [akbData, channelData] = await Promise.all([
        listAkbEntries(projectId),
        listChannels(),
      ]);
      setEntries(akbData);
      setChannels(channelData);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [projectId]);

  const { sorted: sortedEntries, sortState: akbSortState, toggleSort: toggleAkbSort } =
    useSortableTable(entries, AKB_SORT_COLUMNS);

  // Channels not yet used in AKB
  const usedChannelIds = new Set(entries.map((e) => e.channel_id));
  const availableChannels = channels.filter(
    (c) => !usedChannelIds.has(c.id),
  );

  async function handleAdd() {
    if (!validateAkb({
      channel_id: selectedChannelId,
      universe,
      target,
      coverage,
    })) return;
    setAdding(true);
    setError(null);
    try {
      await createAkbEntry(projectId, {
        channel_id: Number(selectedChannelId),
        universe_outlets: universe ? Number(universe) : null,
        target_outlets: target ? Number(target) : null,
        coverage_pct: coverage || null,
      });
      setSelectedChannelId("");
      setUniverse("");
      setTarget("");
      setCoverage("");
      await load();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка",
      );
    } finally {
      setAdding(false);
    }
  }

  const [deletingId, setDeletingId] = useState<number | null>(null);

  async function handleDeleteConfirmed() {
    if (deletingId === null) return;
    const id = deletingId;
    setDeletingId(null);
    try {
      await deleteAkbEntry(projectId, id);
      await load();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка",
      );
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          АКБ — План дистрибуции
        </CardTitle>
        <CardDescription>
          Ассортиментная карта бренда — план дистрибуции по каналам.
          Справочный элемент паспорта, не влияет на расчёт KPI.
          Universe — общее кол-во ТТ в канале, Target — целевое покрытие, Coverage — % покрытия.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error !== null && (
          <p className="text-sm text-destructive">{error}</p>
        )}

        {/* Add form */}
        <div className="flex items-end gap-2 flex-wrap border-b pb-4 mb-4">
          <div>
            <Select
              value={selectedChannelId}
              onValueChange={(v) => { if (v) { setSelectedChannelId(v); clearAkbError("channel_id"); } }}
            >
              <SelectTrigger className={`w-48 ${akbErrors.channel_id ? "border-destructive" : ""}`}>
                <SelectValue placeholder="Канал *" />
              </SelectTrigger>
              <SelectContent>
                {availableChannels.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.code} — {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldError error={akbErrors.channel_id} />
          </div>
          <div>
            <Input
              type="number"
              placeholder="Universe, шт (ТТ)"
              value={universe}
              onChange={(e) => { setUniverse(e.target.value); clearAkbError("universe"); }}
              aria-invalid={!!akbErrors.universe}
              className="w-28"
            />
            <FieldError error={akbErrors.universe} />
          </div>
          <div>
            <Input
              type="number"
              placeholder="Target, шт (ТТ)"
              value={target}
              onChange={(e) => { setTarget(e.target.value); clearAkbError("target"); }}
              aria-invalid={!!akbErrors.target}
              className="w-28"
            />
            <FieldError error={akbErrors.target} />
          </div>
          <div>
            <Input
              type="number"
              placeholder="Coverage, % (доля)"
              value={coverage}
              onChange={(e) => { setCoverage(e.target.value); clearAkbError("coverage"); }}
              aria-invalid={!!akbErrors.coverage}
              className="w-28"
              step="0.01"
            />
            <FieldError error={akbErrors.coverage} />
          </div>
          <Button size="sm" onClick={handleAdd} disabled={adding}>
            {adding ? "..." : "Добавить"}
          </Button>
        </div>

        {loading && (
          <p className="text-sm text-muted-foreground">Загрузка...</p>
        )}

        {!loading && entries.length === 0 && (
          <EmptyState
            title="Нет записей АКБ"
            description="Добавьте канал дистрибуции, чтобы начать."
          />
        )}

        {entries.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="cursor-pointer select-none" onClick={() => toggleAkbSort("channel")}>
                  Канал{sortIndicator(akbSortState, "channel")}
                </TableHead>
                <TableHead className="w-28 cursor-pointer select-none text-right" onClick={() => toggleAkbSort("universe")}>
                  Universe{sortIndicator(akbSortState, "universe")}
                </TableHead>
                <TableHead className="w-28 cursor-pointer select-none text-right" onClick={() => toggleAkbSort("target")}>
                  Target{sortIndicator(akbSortState, "target")}
                </TableHead>
                <TableHead className="w-28 cursor-pointer select-none text-right" onClick={() => toggleAkbSort("coverage")}>
                  Coverage{sortIndicator(akbSortState, "coverage")}
                </TableHead>
                <TableHead className="w-28 cursor-pointer select-none text-right" onClick={() => toggleAkbSort("wd")}>
                  Wt. Distr.{sortIndicator(akbSortState, "wd")}
                </TableHead>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedEntries.map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="font-medium">
                    {e.channel.code} — {e.channel.name}
                  </TableCell>
                  <TableCell className="text-right">
                    {e.universe_outlets ?? "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    {e.target_outlets ?? "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    {formatPercent(e.coverage_pct)}
                  </TableCell>
                  <TableCell className="text-right">
                    {formatPercent(e.weighted_distribution)}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-xs text-destructive"
                      onClick={() => setDeletingId(e.id)}
                    >
                      &times;
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>

      <ConfirmDialog
        open={deletingId !== null}
        onConfirm={handleDeleteConfirmed}
        onCancel={() => setDeletingId(null)}
        title="Удалить запись АКБ?"
      />
    </Card>
  );
}
