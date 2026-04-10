"use client";

import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { FieldError } from "@/components/ui/field-error";
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
import { MockupGallery } from "@/components/projects/mockup-gallery";
import { SkuImageUpload } from "@/components/projects/sku-image-upload";
import { ApiError } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import {
  createBomItem,
  deleteBomItem,
  getProjectSku,
  listBomItems,
  updateProjectSku,
} from "@/lib/skus";
import {
  useFieldValidation,
  type ValidationRules,
} from "@/lib/use-field-validation";
import {
  useSortableTable,
  sortIndicator,
  type SortableColumn,
} from "@/lib/use-sortable-table";

import type { BOMItemRead, ProjectSKUDetail } from "@/types/api";

const BOM_SORT_COLUMNS: SortableColumn<BOMItemRead, string>[] = [
  { key: "name", accessor: (b) => b.ingredient_name },
  { key: "qty", accessor: (b) => Number(b.quantity_per_unit) },
  { key: "loss", accessor: (b) => Number(b.loss_pct) },
  { key: "price", accessor: (b) => Number(b.price_per_unit) },
  {
    key: "cost",
    accessor: (b) =>
      Number(b.quantity_per_unit) * Number(b.price_per_unit) * (1 + Number(b.loss_pct)),
  },
];

interface BomPanelProps {
  projectId: number;
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

type BomField = keyof NewBomDraft;

const BOM_RULES: ValidationRules<BomField> = {
  ingredient_name: { required: true, message: "Введите название" },
  quantity_per_unit: { required: true, numeric: true, min: 0 },
  loss_pct: { numeric: true, min: 0, max: 1 },
  price_per_unit: { numeric: true, min: 0 },
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
export function BomPanel({ projectId, pskId }: BomPanelProps) {
  const [psk, setPsk] = useState<ProjectSKUDetail | null>(null);
  const [bom, setBom] = useState<BOMItemRead[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadCounter, setReloadCounter] = useState(0);
  const [draft, setDraft] = useState<NewBomDraft>(EMPTY_DRAFT);
  const [adding, setAdding] = useState(false);
  const [savingRates, setSavingRates] = useState(false);
  const bomRules = useMemo(() => BOM_RULES, []);
  const { errors: bomErrors, validateAll: validateBom, clearError: clearBomError } =
    useFieldValidation<BomField>(bomRules);
  const { sorted: sortedBom, sortState: bomSortState, toggleSort: toggleBomSort } =
    useSortableTable(bom ?? [], BOM_SORT_COLUMNS);

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
    if (!validateBom(draft)) return;
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

  const [deletingBomId, setDeletingBomId] = useState<number | null>(null);

  async function handleDeleteConfirmed() {
    if (deletingBomId === null) return;
    const id = deletingBomId;
    setDeletingBomId(null);
    try {
      await deleteBomItem(id);
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

          {/* Фаза 4.5.3: изображение упаковки SKU */}
          <div className="mt-4 border-t pt-4">
            <SkuImageUpload
              projectId={projectId}
              pskId={pskId}
              currentImageId={psk.package_image_id}
              onChange={(newId) => {
                setPsk((prev) =>
                  prev ? { ...prev, package_image_id: newId } : prev,
                );
              }}
            />
          </div>

          {/* Phase 7.8: AI Mockup gallery */}
          <div className="mt-4 border-t pt-4">
            <MockupGallery
              projectId={projectId}
              projectSkuId={pskId}
              skuLabel={`${psk.sku?.brand ?? ""} ${psk.sku?.name ?? ""}`}
              currentPackageImageId={psk.package_image_id}
              onPrimaryChanged={(newId) => {
                setPsk((prev) =>
                  prev ? { ...prev, package_image_id: newId } : prev,
                );
              }}
            />
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
                  <TableHead className="cursor-pointer select-none" onClick={() => toggleBomSort("name")}>
                    Ингредиент{sortIndicator(bomSortState, "name")}
                  </TableHead>
                  <TableHead className="cursor-pointer select-none text-right" onClick={() => toggleBomSort("qty")}>
                    Кол-во/ед{sortIndicator(bomSortState, "qty")}
                  </TableHead>
                  <TableHead className="cursor-pointer select-none text-right" onClick={() => toggleBomSort("loss")}>
                    % потерь{sortIndicator(bomSortState, "loss")}
                  </TableHead>
                  <TableHead className="cursor-pointer select-none text-right" onClick={() => toggleBomSort("price")}>
                    Цена/ед, ₽{sortIndicator(bomSortState, "price")}
                  </TableHead>
                  <TableHead className="cursor-pointer select-none text-right" onClick={() => toggleBomSort("cost")}>
                    Стоимость, ₽{sortIndicator(bomSortState, "cost")}
                  </TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedBom.map((b) => {
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
                          onClick={() => setDeletingBomId(b.id)}
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
                onChange={(e) => {
                  setDraft({ ...draft, ingredient_name: e.target.value });
                  clearBomError("ingredient_name");
                }}
                aria-invalid={!!bomErrors.ingredient_name}
                disabled={adding}
                placeholder="Сахар"
              />
              <FieldError error={bomErrors.ingredient_name} />
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
                onChange={(e) => {
                  setDraft({ ...draft, quantity_per_unit: e.target.value });
                  clearBomError("quantity_per_unit");
                }}
                aria-invalid={!!bomErrors.quantity_per_unit}
                disabled={adding}
                placeholder="0.05"
              />
              <FieldError error={bomErrors.quantity_per_unit} />
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
                onChange={(e) => {
                  setDraft({ ...draft, loss_pct: e.target.value });
                  clearBomError("loss_pct");
                }}
                aria-invalid={!!bomErrors.loss_pct}
                disabled={adding}
                placeholder="0.02"
              />
              <FieldError error={bomErrors.loss_pct} />
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
                onChange={(e) => {
                  setDraft({ ...draft, price_per_unit: e.target.value });
                  clearBomError("price_per_unit");
                }}
                aria-invalid={!!bomErrors.price_per_unit}
                disabled={adding}
                placeholder="80.00"
              />
              <FieldError error={bomErrors.price_per_unit} />
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

      <ConfirmDialog
        open={deletingBomId !== null}
        onConfirm={handleDeleteConfirmed}
        onCancel={() => setDeletingBomId(null)}
        title="Удалить ингредиент из BOM?"
      />
    </div>
  );
}
