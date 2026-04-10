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
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { ApiError } from "@/lib/api";
import { listChannels } from "@/lib/channels";
import { formatMoney } from "@/lib/format";
import {
  createObppcEntry,
  deleteObppcEntry,
  listObppcEntries,
} from "@/lib/obppc";
import { listSkus } from "@/lib/skus";

import type { Channel, OBPPCRead, PriceTier, SKURead } from "@/types/api";

const TIER_LABELS: Record<PriceTier, string> = {
  premium: "Premium",
  mainstream: "Mainstream",
  value: "Value",
};

interface ObppcTabProps {
  projectId: number;
}

export function ObppcTab({ projectId }: ObppcTabProps) {
  const [entries, setEntries] = useState<OBPPCRead[]>([]);
  const [skus, setSkus] = useState<SKURead[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Add form
  const [selectedSkuId, setSelectedSkuId] = useState("");
  const [selectedChannelId, setSelectedChannelId] = useState("");
  const [priceTier, setPriceTier] = useState<PriceTier>("mainstream");
  const [packFormat, setPackFormat] = useState("bottle");
  const [packSize, setPackSize] = useState("");
  const [pricePoint, setPricePoint] = useState("");
  const [adding, setAdding] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [obppcData, skuData, channelData] = await Promise.all([
        listObppcEntries(projectId),
        listSkus(),
        listChannels(),
      ]);
      setEntries(obppcData);
      setSkus(skuData);
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

  async function handleAdd() {
    if (!selectedSkuId || !selectedChannelId) return;
    setAdding(true);
    setError(null);
    try {
      await createObppcEntry(projectId, {
        sku_id: Number(selectedSkuId),
        channel_id: Number(selectedChannelId),
        price_tier: priceTier,
        pack_format: packFormat || "bottle",
        pack_size_ml: packSize ? Number(packSize) : null,
        price_point: pricePoint || null,
      });
      setSelectedSkuId("");
      setSelectedChannelId("");
      setPriceTier("mainstream");
      setPackFormat("bottle");
      setPackSize("");
      setPricePoint("");
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
      await deleteObppcEntry(projectId, id);
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
          OBPPC — Price-Pack-Channel
        </CardTitle>
        <CardDescription>
          Стратегическая матрица: какие SKU, в каких форматах, по каким
          ценам и в каких каналах.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error !== null && (
          <p className="text-sm text-destructive">{error}</p>
        )}

        {/* Add form */}
        <div className="flex items-end gap-2 flex-wrap border-b pb-4 mb-4">
          <Select value={selectedSkuId} onValueChange={(v) => { if (v) setSelectedSkuId(v); }}>
            <SelectTrigger className="w-48">
              <SelectValue placeholder="SKU" />
            </SelectTrigger>
            <SelectContent>
              {skus.map((s) => (
                <SelectItem key={s.id} value={String(s.id)}>
                  {s.brand} — {s.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={selectedChannelId}
            onValueChange={(v) => { if (v) setSelectedChannelId(v); }}
          >
            <SelectTrigger className="w-40">
              <SelectValue placeholder="Канал" />
            </SelectTrigger>
            <SelectContent>
              {channels.map((c) => (
                <SelectItem key={c.id} value={String(c.id)}>
                  {c.code}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={priceTier}
            onValueChange={(v) => { if (v) setPriceTier(v as PriceTier); }}
          >
            <SelectTrigger className="w-36">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="premium">Premium</SelectItem>
              <SelectItem value="mainstream">Mainstream</SelectItem>
              <SelectItem value="value">Value</SelectItem>
            </SelectContent>
          </Select>
          <Input
            placeholder="Формат"
            value={packFormat}
            onChange={(e) => setPackFormat(e.target.value)}
            className="w-28"
          />
          <Input
            type="number"
            placeholder="ml"
            value={packSize}
            onChange={(e) => setPackSize(e.target.value)}
            className="w-20"
          />
          <Input
            type="number"
            placeholder="Цена"
            value={pricePoint}
            onChange={(e) => setPricePoint(e.target.value)}
            className="w-24"
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
          <EmptyState
            title="Нет записей OBPPC"
            description="Добавьте первую комбинацию SKU × канал × формат."
          />
        )}

        {entries.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>SKU</TableHead>
                <TableHead>Канал</TableHead>
                <TableHead className="w-28">Tier</TableHead>
                <TableHead className="w-24">Формат</TableHead>
                <TableHead className="w-20 text-right">ml</TableHead>
                <TableHead className="w-24 text-right">Цена</TableHead>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((e) => (
                <TableRow
                  key={e.id}
                  className={e.is_active ? "" : "opacity-50"}
                >
                  <TableCell className="font-medium">
                    {e.sku.brand} — {e.sku.name}
                  </TableCell>
                  <TableCell>{e.channel.code}</TableCell>
                  <TableCell>{TIER_LABELS[e.price_tier]}</TableCell>
                  <TableCell>{e.pack_format}</TableCell>
                  <TableCell className="text-right">
                    {e.pack_size_ml ?? "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    {formatMoney(e.price_point)}
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
        title="Удалить запись OBPPC?"
      />
    </Card>
  );
}
