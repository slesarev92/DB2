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
import { listChannels } from "@/lib/channels";
import { formatMoney } from "@/lib/format";
import {
  createObppcEntry,
  deleteObppcEntry,
  listObppcEntries,
} from "@/lib/obppc";
import { listSkus } from "@/lib/skus";
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

import { PACK_FORMAT_LABELS, PRICE_TIER_LABELS } from "@/types/api";
import type { Channel, OBPPCRead, PriceTier, SKURead } from "@/types/api";

const OBPPC_SORT_COLUMNS: SortableColumn<OBPPCRead, string>[] = [
  { key: "sku", accessor: (e) => `${e.sku.brand} — ${e.sku.name}` },
  { key: "channel", accessor: (e) => e.channel.code },
  { key: "tier", accessor: (e) => e.price_tier },
  { key: "format", accessor: (e) => e.pack_format },
  { key: "ml", accessor: (e) => e.pack_size_ml },
  { key: "price", accessor: (e) => (e.price_point !== null ? Number(e.price_point) : null) },
];

type ObppcField = "sku_id" | "channel_id" | "pack_size" | "price_point";

const OBPPC_RULES: ValidationRules<ObppcField> = {
  sku_id: { required: true, message: "Выберите SKU" },
  channel_id: { required: true, message: "Выберите канал" },
  pack_size: { numeric: true, min: 0 },
  price_point: { numeric: true, min: 0 },
};

// Используем единые PRICE_TIER_LABELS / PACK_FORMAT_LABELS из types/api.ts (L-02).
const TIER_LABELS: Record<PriceTier, string> = PRICE_TIER_LABELS as Record<PriceTier, string>;

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
  const obppcRules = useMemo(() => OBPPC_RULES, []);
  const { errors: obppcErrors, validateAll: validateObppc, clearError: clearObppcError } =
    useFieldValidation<ObppcField>(obppcRules);

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
    if (!validateObppc({
      sku_id: selectedSkuId,
      channel_id: selectedChannelId,
      pack_size: packSize,
      price_point: pricePoint,
    })) return;
    setAdding(true);
    setError(null);
    try {
      await createObppcEntry(projectId, {
        sku_id: Number(selectedSkuId),
        channel_id: Number(selectedChannelId),
        price_tier: priceTier,
        pack_format: packFormat || "bottle",
        pack_size_ml: packSize && Number(packSize) > 0 ? Number(packSize) : null,
        price_point: pricePoint && pricePoint.trim() !== "" ? pricePoint : null,
      });
      setSelectedSkuId("");
      setSelectedChannelId("");
      setPriceTier("mainstream");
      setPackFormat("bottle");
      setPackSize("");
      setPricePoint("");
      toast.success("OBPPC запись добавлена");
      await load();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка";
      setError(msg);
      toast.error(`Не удалось добавить: ${msg}`);
    } finally {
      setAdding(false);
    }
  }

  const { sorted: sortedEntries, sortState: obSortState, toggleSort: toggleObSort } =
    useSortableTable(entries, OBPPC_SORT_COLUMNS);

  const [deletingId, setDeletingId] = useState<number | null>(null);

  async function handleDeleteConfirmed() {
    if (deletingId === null) return;
    const id = deletingId;
    setDeletingId(null);
    try {
      await deleteObppcEntry(projectId, id);
      toast.success("OBPPC запись удалена");
      await load();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка";
      setError(msg);
      toast.error(`Не удалось удалить: ${msg}`);
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
          <div>
            <Select value={selectedSkuId} onValueChange={(v) => { if (v) { setSelectedSkuId(v); clearObppcError("sku_id"); } }}>
              <SelectTrigger className={`w-48 ${obppcErrors.sku_id ? "border-destructive" : ""}`}>
                <SelectValue placeholder="SKU *" />
              </SelectTrigger>
              <SelectContent>
                {skus.map((s) => (
                  <SelectItem key={s.id} value={String(s.id)}>
                    {s.brand} — {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldError error={obppcErrors.sku_id} />
          </div>
          <div>
            <Select
              value={selectedChannelId}
              onValueChange={(v) => { if (v) { setSelectedChannelId(v); clearObppcError("channel_id"); } }}
            >
              <SelectTrigger className={`w-40 ${obppcErrors.channel_id ? "border-destructive" : ""}`}>
                <SelectValue placeholder="Канал *" />
              </SelectTrigger>
              <SelectContent>
                {channels.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.code}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldError error={obppcErrors.channel_id} />
          </div>
          <Select
            value={priceTier}
            onValueChange={(v) => { if (v) setPriceTier(v as PriceTier); }}
          >
            <SelectTrigger className="w-36">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="premium">{PRICE_TIER_LABELS.premium}</SelectItem>
              <SelectItem value="mainstream">{PRICE_TIER_LABELS.mainstream}</SelectItem>
              <SelectItem value="value">{PRICE_TIER_LABELS.value}</SelectItem>
            </SelectContent>
          </Select>
          <Input
            placeholder="Формат"
            value={packFormat}
            onChange={(e) => setPackFormat(e.target.value)}
            className="w-28"
          />
          <div>
            <Input
              type="number"
              placeholder="Объём, мл"
              value={packSize}
              onChange={(e) => { setPackSize(e.target.value); clearObppcError("pack_size"); }}
              aria-invalid={!!obppcErrors.pack_size}
              className="w-20"
            />
            <FieldError error={obppcErrors.pack_size} />
          </div>
          <div>
            <Input
              type="number"
              placeholder="Цена, ₽"
              value={pricePoint}
              onChange={(e) => { setPricePoint(e.target.value); clearObppcError("price_point"); }}
              aria-invalid={!!obppcErrors.price_point}
              className="w-24"
              step="0.01"
            />
            <FieldError error={obppcErrors.price_point} />
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
            title="Нет записей OBPPC"
            description="Добавьте первую комбинацию SKU × канал × формат."
          />
        )}

        {entries.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead {...sortableHeaderProps(toggleObSort, "sku")}>
                  SKU{sortIndicator(obSortState, "sku")}
                </TableHead>
                <TableHead {...sortableHeaderProps(toggleObSort, "channel")}>
                  Канал{sortIndicator(obSortState, "channel")}
                </TableHead>
                <TableHead {...sortableHeaderProps(toggleObSort, "tier", "w-28")}>
                  Tier{sortIndicator(obSortState, "tier")}
                </TableHead>
                <TableHead {...sortableHeaderProps(toggleObSort, "format", "w-24")}>
                  Формат{sortIndicator(obSortState, "format")}
                </TableHead>
                <TableHead {...sortableHeaderProps(toggleObSort, "ml", "w-20 text-right")}>
                  ml{sortIndicator(obSortState, "ml")}
                </TableHead>
                <TableHead {...sortableHeaderProps(toggleObSort, "price", "w-24 text-right")}>
                  Цена{sortIndicator(obSortState, "price")}
                </TableHead>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedEntries.map((e) => (
                <TableRow
                  key={e.id}
                  className={e.is_active ? "" : "opacity-50"}
                >
                  <TableCell className="font-medium">
                    {e.sku.brand} — {e.sku.name}
                  </TableCell>
                  <TableCell>{e.channel.code}</TableCell>
                  <TableCell>{TIER_LABELS[e.price_tier]}</TableCell>
                  <TableCell>
                    {PACK_FORMAT_LABELS[e.pack_format] ?? e.pack_format}
                  </TableCell>
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
