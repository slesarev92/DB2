"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

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
  listAkbAuto,
  listAkbEntries,
} from "@/lib/akb";
import { listChannels } from "@/lib/channels";
import { CHANNEL_GROUP_LABELS, CHANNEL_GROUP_ORDER } from "@/lib/channel-group";
import { formatPercent } from "@/lib/format";
import {
  useFieldValidation,
  type ValidationRules,
} from "@/lib/use-field-validation";
import {
  useSortableTable,
  sortIndicator,
  sortableHeaderProps,
  type SortableColumn,
} from "@/lib/use-sortable-table";

import type { AKBAutoEntry, AKBRead, Channel, ChannelGroup } from "@/types/api";

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

interface GroupAggregate {
  group: ChannelGroup;
  channelsCount: number;
  totalUniverse: number;
  totalTarget: number;
  avgNdTarget: number;
}

interface AkbTabProps {
  projectId: number;
}

export function AkbTab({ projectId }: AkbTabProps) {
  const [entries, setEntries] = useState<AKBRead[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [autoEntries, setAutoEntries] = useState<AKBAutoEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoLoading, setAutoLoading] = useState(true);
  const [aggregateView, setAggregateView] = useState(false);

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
    setAutoLoading(true);
    try {
      const [akbData, channelData, autoData] = await Promise.all([
        listAkbEntries(projectId),
        listChannels(),
        listAkbAuto(projectId),
      ]);
      setEntries(akbData);
      setChannels(channelData);
      setAutoEntries(autoData);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка",
      );
    } finally {
      setLoading(false);
      setAutoLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [projectId]);

  const { sorted: sortedEntries, sortState: akbSortState, toggleSort: toggleAkbSort } =
    useSortableTable(entries, AKB_SORT_COLUMNS);

  // Aggregate by channel group
  const aggregates = useMemo<GroupAggregate[]>(() => {
    const byGroup = new Map<ChannelGroup, AKBAutoEntry[]>();
    for (const e of autoEntries) {
      const arr = byGroup.get(e.channel_group) ?? [];
      arr.push(e);
      byGroup.set(e.channel_group, arr);
    }
    const result: GroupAggregate[] = [];
    for (const group of CHANNEL_GROUP_ORDER) {
      const groupEntries = byGroup.get(group);
      if (!groupEntries || groupEntries.length === 0) continue;
      const totalUniverse = groupEntries.reduce((s, e) => s + (e.universe_outlets ?? 0), 0);
      const totalTarget = groupEntries.reduce((s, e) => s + (e.target_outlets ?? 0), 0);
      const avgNd =
        groupEntries.reduce((s, e) => s + Number(e.nd_target), 0) / groupEntries.length;
      result.push({
        group,
        channelsCount: groupEntries.length,
        totalUniverse,
        totalTarget,
        avgNdTarget: avgNd,
      });
    }
    return result;
  }, [autoEntries]);

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
      toast.success("АКБ запись добавлена");
      await load();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка";
      setError(msg);
      toast.error(`Не удалось добавить АКБ: ${msg}`);
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
      toast.success("АКБ запись удалена");
      await load();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка";
      setError(msg);
      toast.error(`Не удалось удалить: ${msg}`);
    }
  }

  return (
    <div className="space-y-4">
      {/* ── Auto-compute section ─────────────────────────────── */}
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle className="text-base">
                Авто-расчёт АКБ (nd × ОКБ)
              </CardTitle>
              <CardDescription>
                Целевые ТТ автоматически = % дистрибуции × ОКБ канала.
                Меняйте параметры на вкладке «Каналы» — обновится здесь.
              </CardDescription>
            </div>
            <div className="flex gap-1 shrink-0">
              <Button
                size="sm"
                variant={aggregateView ? "outline" : "default"}
                onClick={() => setAggregateView(false)}
              >
                По SKU × каналу
              </Button>
              <Button
                size="sm"
                variant={aggregateView ? "default" : "outline"}
                onClick={() => setAggregateView(true)}
              >
                По группам
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {autoLoading && (
            <p className="text-sm text-muted-foreground">Загрузка...</p>
          )}
          {!autoLoading && autoEntries.length === 0 && (
            <EmptyState
              title="Нет данных для авто-расчёта"
              description="Привяжите каналы к SKU на вкладке «Каналы», чтобы увидеть план."
            />
          )}
          {!autoLoading && autoEntries.length > 0 && !aggregateView && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>SKU</TableHead>
                  <TableHead>Канал</TableHead>
                  <TableHead className="text-right">ОКБ, ТТ</TableHead>
                  <TableHead className="text-right">ND, %</TableHead>
                  <TableHead className="text-right">План АКБ, ТТ</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {autoEntries.map((e) => (
                  <TableRow key={`${e.psk_id}-${e.channel_id}`}>
                    <TableCell className="text-sm">
                      <div className="font-medium">{e.sku_brand}</div>
                      <div className="text-xs text-muted-foreground">{e.sku_name}</div>
                    </TableCell>
                    <TableCell className="text-sm">
                      <div className="font-medium">{e.channel_code}</div>
                      <div className="text-xs text-muted-foreground">
                        {CHANNEL_GROUP_LABELS[e.channel_group]} · {e.channel_name}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      {e.universe_outlets !== null
                        ? e.universe_outlets.toLocaleString("ru-RU")
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      {formatPercent(e.nd_target)}
                    </TableCell>
                    <TableCell className="text-right font-medium">
                      {e.target_outlets !== null
                        ? e.target_outlets.toLocaleString("ru-RU")
                        : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {!autoLoading && autoEntries.length > 0 && aggregateView && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Группа</TableHead>
                  <TableHead className="text-right">Каналов</TableHead>
                  <TableHead className="text-right">Σ ОКБ, ТТ</TableHead>
                  <TableHead className="text-right">avg ND, %</TableHead>
                  <TableHead className="text-right">Σ План АКБ, ТТ</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {aggregates.map((a) => (
                  <TableRow key={a.group}>
                    <TableCell className="font-medium">
                      {CHANNEL_GROUP_LABELS[a.group]}
                    </TableCell>
                    <TableCell className="text-right">{a.channelsCount}</TableCell>
                    <TableCell className="text-right">
                      {a.totalUniverse.toLocaleString("ru-RU")}
                    </TableCell>
                    <TableCell className="text-right">
                      {formatPercent(String(a.avgNdTarget))}
                    </TableCell>
                    <TableCell className="text-right font-medium">
                      {a.totalTarget.toLocaleString("ru-RU")}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* ── Manual AKB entries (legacy) ───────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Ручные записи АКБ (legacy)
          </CardTitle>
          <CardDescription>
            Ручная таблица дистрибуции по каналам — Universe, Target, Coverage.
            Не влияет на расчёт KPI. Используйте авто-расчёт выше для актуального плана.
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
                items={Object.fromEntries(
                  availableChannels.map((c) => [String(c.id), `${c.code} — ${c.name}`]),
                )}
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
                  <TableHead {...sortableHeaderProps(toggleAkbSort, "channel")}>
                    Канал{sortIndicator(akbSortState, "channel")}
                  </TableHead>
                  <TableHead {...sortableHeaderProps(toggleAkbSort, "universe", "w-28 text-right")}>
                    Universe{sortIndicator(akbSortState, "universe")}
                  </TableHead>
                  <TableHead {...sortableHeaderProps(toggleAkbSort, "target", "w-28 text-right")}>
                    Target{sortIndicator(akbSortState, "target")}
                  </TableHead>
                  <TableHead {...sortableHeaderProps(toggleAkbSort, "coverage", "w-28 text-right")}>
                    Coverage{sortIndicator(akbSortState, "coverage")}
                  </TableHead>
                  <TableHead {...sortableHeaderProps(toggleAkbSort, "wd", "w-28 text-right")}>
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
    </div>
  );
}
