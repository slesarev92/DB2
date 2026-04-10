"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import { ApiError } from "@/lib/api";
import {
  createAkbEntry,
  deleteAkbEntry,
  listAkbEntries,
} from "@/lib/akb";
import { listChannels } from "@/lib/channels";
import { formatPercent } from "@/lib/format";

import type { AKBRead, Channel } from "@/types/api";

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

  // Channels not yet used in AKB
  const usedChannelIds = new Set(entries.map((e) => e.channel_id));
  const availableChannels = channels.filter(
    (c) => !usedChannelIds.has(c.id),
  );

  async function handleAdd() {
    if (!selectedChannelId) return;
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

  async function handleDelete(entryId: number) {
    if (!window.confirm("Удалить запись АКБ?")) return;
    try {
      await deleteAkbEntry(projectId, entryId);
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
          Активная клиентская база по каналам: universe, target, покрытие.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error !== null && (
          <p className="text-sm text-destructive">{error}</p>
        )}

        {/* Add form */}
        <div className="flex items-end gap-2 flex-wrap">
          <Select
            value={selectedChannelId}
            onValueChange={(v) => { if (v) setSelectedChannelId(v); }}
          >
            <SelectTrigger className="w-48">
              <SelectValue placeholder="Канал" />
            </SelectTrigger>
            <SelectContent>
              {availableChannels.map((c) => (
                <SelectItem key={c.id} value={String(c.id)}>
                  {c.code} — {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            type="number"
            placeholder="Universe"
            value={universe}
            onChange={(e) => setUniverse(e.target.value)}
            className="w-28"
          />
          <Input
            type="number"
            placeholder="Target"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            className="w-28"
          />
          <Input
            type="number"
            placeholder="Coverage %"
            value={coverage}
            onChange={(e) => setCoverage(e.target.value)}
            className="w-28"
            step="0.01"
          />
          <Button size="sm" onClick={handleAdd} disabled={adding}>
            {adding ? "..." : "Добавить"}
          </Button>
        </div>

        {loading && (
          <p className="text-sm text-muted-foreground">Загрузка...</p>
        )}

        {!loading && entries.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Нет записей АКБ. Добавьте канал дистрибуции.
          </p>
        )}

        {entries.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Канал</TableHead>
                <TableHead className="w-28 text-right">Universe</TableHead>
                <TableHead className="w-28 text-right">Target</TableHead>
                <TableHead className="w-28 text-right">Coverage</TableHead>
                <TableHead className="w-28 text-right">Wt. Distr.</TableHead>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((e) => (
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
                      onClick={() => handleDelete(e.id)}
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
    </Card>
  );
}
