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
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import {
  createBomItem,
  deleteBomItem,
  getProjectSku,
  listBomItems,
  updateProjectSku,
} from "@/lib/skus";

import type { BOMItemRead, ProjectSKUDetail } from "@/types/api";

interface BomPanelProps {
  pskId: number;
}

interface NewBomDraft {
  ingredient_name: string;
  quantity_per_unit: string;
  loss_pct: string;
  price_per_unit: string;
}

const EMPTY_DRAFT: NewBomDraft = {
  ingredient_name: "",
  quantity_per_unit: "",
  loss_pct: "0",
  price_per_unit: "",
};

/** Σ (qty × price × (1 + loss)) — preview расчёт COGS на единицу. */
function computeCogsPreview(items: BOMItemRead[]): number {
  return items.reduce((sum, b) => {
    const q = Number(b.quantity_per_unit);
    const p = Number(b.price_per_unit);
    const l = Number(b.loss_pct);
    if ([q, p, l].some(Number.isNaN)) return sum;
    return sum + q * p * (1 + l);
  }, 0);
}

/**
 * Панель BOM для выбранного ProjectSKU.
 *
 * Содержит:
 *  - Editor для production_cost_rate / ca_m_rate / marketing_rate (PATCH PSK)
 *  - Таблица BOM позиций (read-only display, удаление inline)
 *  - Inline форма добавления нового ингредиента
 *  - Live COGS_PER_UNIT preview (Σ qty × price × (1+loss))
 *
 * Persistance: каждое изменение → отдельный API call. Нет batch save —
 * MVP, можно оптимизировать позже.
 */
export function BomPanel({ pskId }: BomPanelProps) {
  const [psk, setPsk] = useState<ProjectSKUDetail | null>(null);
  const [bom, setBom] = useState<BOMItemRead[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadCounter, setReloadCounter] = useState(0);
  const [draft, setDraft] = useState<NewBomDraft>(EMPTY_DRAFT);
  const [adding, setAdding] = useState(false);
  const [savingRates, setSavingRates] = useState(false);

  // Локальные значения rates для редактирования (PATCH on blur)
  const [productionCostRate, setProductionCostRate] = useState("");
  const [caMRate, setCaMRate] = useState("");
  const [marketingRate, setMarketingRate] = useState("");

  // Загрузка ProjectSKU + BOM при смене pskId или reload
  useEffect(() => {
    let cancelled = false;
    setPsk(null);
    setBom(null);
    setError(null);

    Promise.all([getProjectSku(pskId), listBomItems(pskId)])
      .then(([pskData, bomData]) => {
        if (cancelled) return;
        setPsk(pskData);
        setBom(bomData);
        setProductionCostRate(pskData.production_cost_rate);
        setCaMRate(pskData.ca_m_rate);
        setMarketingRate(pskData.marketing_rate);
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

  async function handleAdd(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setAdding(true);
    try {
      await createBomItem(pskId, {
        ingredient_name: draft.ingredient_name,
        quantity_per_unit: draft.quantity_per_unit,
        loss_pct: draft.loss_pct || "0",
        price_per_unit: draft.price_per_unit || "0",
      });
      setDraft(EMPTY_DRAFT);
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail ?? err.message : "Ошибка");
    } finally {
      setAdding(false);
    }
  }

  async function handleDelete(bomId: number) {
    try {
      await deleteBomItem(bomId);
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail ?? err.message : "Ошибка");
    }
  }

  async function saveRates() {
    if (psk === null) return;
    setSavingRates(true);
    setError(null);
    try {
      await updateProjectSku(pskId, {
        production_cost_rate: productionCostRate,
        ca_m_rate: caMRate,
        marketing_rate: marketingRate,
      });
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail ?? err.message : "Ошибка");
    } finally {
      setSavingRates(false);
    }
  }

  if (error !== null && psk === null) {
    return (
      <Card className="border-destructive">
        <CardContent className="pt-6 text-sm text-destructive">
          {error}
        </CardContent>
      </Card>
    );
  }

  if (psk === null || bom === null) {
    return <p className="text-sm text-muted-foreground">Загрузка...</p>;
  }

  const cogsPreview = computeCogsPreview(bom);

  return (
    <div className="space-y-4">
      {/* === ProjectSKU rates editor === */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {psk.sku.brand} — {psk.sku.name}
          </CardTitle>
          <CardDescription>
            Параметры % от выручки. Меняются здесь, расчёт ядра подхватит
            при следующем POST /api/projects/{"{id}"}/recalculate.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="production_cost_rate">
                Production cost (% от ex-factory)
              </Label>
              <Input
                id="production_cost_rate"
                type="number"
                step="0.001"
                min="0"
                max="1"
                value={productionCostRate}
                onChange={(e) => setProductionCostRate(e.target.value)}
                onBlur={saveRates}
                disabled={savingRates}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ca_m_rate">CA&M (% от выручки)</Label>
              <Input
                id="ca_m_rate"
                type="number"
                step="0.001"
                min="0"
                max="1"
                value={caMRate}
                onChange={(e) => setCaMRate(e.target.value)}
                onBlur={saveRates}
                disabled={savingRates}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="marketing_rate">Marketing (% от выручки)</Label>
              <Input
                id="marketing_rate"
                type="number"
                step="0.001"
                min="0"
                max="1"
                value={marketingRate}
                onChange={(e) => setMarketingRate(e.target.value)}
                onBlur={saveRates}
                disabled={savingRates}
              />
            </div>
          </div>

        </CardContent>
      </Card>

      {/* === BOM table + add form + COGS preview === */}
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <div>
              <CardTitle className="text-base">Bill of Materials</CardTitle>
              <CardDescription>
                Σ (количество × цена × (1 + потери)) на единицу продукции.
              </CardDescription>
            </div>
            <div className="text-right">
              <p className="text-xs text-muted-foreground">
                COGS на единицу (preview)
              </p>
              <p className="text-lg font-semibold">
                {formatMoney(String(cogsPreview))}
              </p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {bom.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Ингредиентов пока нет. Добавьте первый.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Ингредиент</TableHead>
                  <TableHead className="text-right">Кол-во/ед</TableHead>
                  <TableHead className="text-right">% потерь</TableHead>
                  <TableHead className="text-right">Цена/ед, ₽</TableHead>
                  <TableHead className="text-right">Стоимость, ₽</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {bom.map((b) => {
                  const itemCost =
                    Number(b.quantity_per_unit) *
                    Number(b.price_per_unit) *
                    (1 + Number(b.loss_pct));
                  return (
                    <TableRow key={b.id}>
                      <TableCell>{b.ingredient_name}</TableCell>
                      <TableCell className="text-right">
                        {Number(b.quantity_per_unit).toLocaleString("ru-RU", {
                          maximumFractionDigits: 4,
                        })}
                      </TableCell>
                      <TableCell className="text-right">
                        {(Number(b.loss_pct) * 100).toFixed(1)}%
                      </TableCell>
                      <TableCell className="text-right">
                        {Number(b.price_per_unit).toLocaleString("ru-RU", {
                          maximumFractionDigits: 4,
                        })}
                      </TableCell>
                      <TableCell className="text-right font-medium">
                        {formatMoney(String(itemCost))}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDelete(b.id)}
                        >
                          ×
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}

          {/* === Inline add form === */}
          <form
            onSubmit={handleAdd}
            className="grid grid-cols-12 items-end gap-2 border-t pt-4"
          >
            <div className="col-span-4 space-y-1">
              <Label htmlFor="bom-name" className="text-xs">
                Ингредиент *
              </Label>
              <Input
                id="bom-name"
                required
                value={draft.ingredient_name}
                onChange={(e) =>
                  setDraft({ ...draft, ingredient_name: e.target.value })
                }
                disabled={adding}
                placeholder="Сахар"
              />
            </div>
            <div className="col-span-2 space-y-1">
              <Label htmlFor="bom-qty" className="text-xs">
                Кол-во *
              </Label>
              <Input
                id="bom-qty"
                type="number"
                step="0.0001"
                min="0"
                required
                value={draft.quantity_per_unit}
                onChange={(e) =>
                  setDraft({ ...draft, quantity_per_unit: e.target.value })
                }
                disabled={adding}
                placeholder="0.05"
              />
            </div>
            <div className="col-span-2 space-y-1">
              <Label htmlFor="bom-loss" className="text-xs">
                Потери (доля)
              </Label>
              <Input
                id="bom-loss"
                type="number"
                step="0.001"
                min="0"
                max="1"
                value={draft.loss_pct}
                onChange={(e) =>
                  setDraft({ ...draft, loss_pct: e.target.value })
                }
                disabled={adding}
                placeholder="0.02"
              />
            </div>
            <div className="col-span-2 space-y-1">
              <Label htmlFor="bom-price" className="text-xs">
                Цена/ед, ₽
              </Label>
              <Input
                id="bom-price"
                type="number"
                step="0.01"
                min="0"
                value={draft.price_per_unit}
                onChange={(e) =>
                  setDraft({ ...draft, price_per_unit: e.target.value })
                }
                disabled={adding}
                placeholder="80.00"
              />
            </div>
            <div className="col-span-2">
              <Button type="submit" disabled={adding} className="w-full">
                {adding ? "..." : "Добавить"}
              </Button>
            </div>
          </form>

          {error !== null && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
