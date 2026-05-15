"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

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
import { HelpButton } from "@/components/ui/help-button";
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
import { ProductionModeByYearEditor } from "@/components/projects/production-mode-by-year-editor";
import { SkuImageUpload } from "@/components/projects/sku-image-upload";
import { ApiError } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { listIngredients } from "@/lib/ingredients";
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
  sortableHeaderProps,
  type SortableColumn,
} from "@/lib/use-sortable-table";

import type { BOMItemRead, IngredientRead, ProjectSKUDetail } from "@/types/api";

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
  ingredient_id: number | null;
  ingredient_name: string;
  quantity_per_unit: string;
  loss_pct: string;
  price_per_unit: string;
  vat_rate: string;
}

const EMPTY_DRAFT: NewBomDraft = {
  ingredient_id: null,
  ingredient_name: "",
  quantity_per_unit: "",
  loss_pct: "0",
  price_per_unit: "",
  vat_rate: "0.20",
};

/** String-only поля формы, подходящие под field-validation. ingredient_id
 * не валидируется (число | null, привязка к каталогу). */
type BomField =
  | "ingredient_name"
  | "quantity_per_unit"
  | "loss_pct"
  | "price_per_unit"
  | "vat_rate";

const BOM_RULES: ValidationRules<BomField> = {
  ingredient_name: { required: true, message: "Введите название" },
  quantity_per_unit: { required: true, numeric: true, min: 0 },
  loss_pct: { numeric: true, min: 0, max: 1 },
  price_per_unit: { numeric: true, min: 0 },
  vat_rate: { numeric: true, min: 0, max: 1 },
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
 *  - Editor для production_cost_rate / copacking_rate / production_mode
 *    (PATCH PSK). CA&M и Marketing переехали в Каналы (Q6, 2026-05-15).
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

  // B-04: каталог ингредиентов для авто-заполнения BOM.
  // Загружается при первом монтировании компонента; если каталог пуст —
  // пользователь вводит имя в поле вручную.
  const [catalog, setCatalog] = useState<IngredientRead[]>([]);
  useEffect(() => {
    let cancelled = false;
    listIngredients()
      .then((data) => {
        if (!cancelled) setCatalog(data);
      })
      .catch(() => {
        // Тихая ошибка: каталог — опциональный фичер автозаполнения.
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const bomRules = useMemo(() => BOM_RULES, []);
  const { errors: bomErrors, validateAll: validateBom, clearError: clearBomError } =
    useFieldValidation<BomField>(bomRules);
  const { sorted: sortedBom, sortState: bomSortState, toggleSort: toggleBomSort } =
    useSortableTable(bom ?? [], BOM_SORT_COLUMNS);

  // UX-10: BOM summary by ingredient category (moved here, hooks before early returns)
  const categorySums = useMemo(() => {
    const sums: Record<string, number> = {};
    if (bom === null) return sums;
    for (const b of bom) {
      const cat = b.ingredient_category ?? "other";
      const cost =
        Number(b.quantity_per_unit) *
        Number(b.price_per_unit) *
        (1 + Number(b.loss_pct));
      sums[cat] = (sums[cat] ?? 0) + cost;
    }
    return sums;
  }, [bom]);

  // Локальные значения rates для редактирования (PATCH on blur)
  // Q6 (2026-05-15): ca_m_rate и marketing_rate переехали в Каналы.
  const [productionMode, setProductionMode] = useState("own");
  const [copackingRate, setCopackingRate] = useState("");
  const [productionCostRate, setProductionCostRate] = useState("");
  // Q1 (2026-05-15): годовой override режима. Ключи "1".."10".
  // Пустой объект = override выключен, используется скаляр productionMode.
  const [productionModeByYear, setProductionModeByYear] = useState<
    Record<string, string>
  >({});

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
        setProductionMode(pskData.production_mode ?? "own");
        setCopackingRate(pskData.copacking_rate ?? "0");
        setProductionCostRate(pskData.production_cost_rate);
        setProductionModeByYear(pskData.production_mode_by_year ?? {});
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
    // ingredient_id is a number|null, not part of string-based validation rules
    const validateDraft: Record<BomField, string> = {
      ingredient_name: draft.ingredient_name,
      quantity_per_unit: draft.quantity_per_unit,
      loss_pct: draft.loss_pct,
      price_per_unit: draft.price_per_unit,
      vat_rate: draft.vat_rate,
    };
    if (!validateBom(validateDraft)) return;
    setError(null);
    setAdding(true);
    try {
      await createBomItem(pskId, {
        ingredient_id: draft.ingredient_id,
        ingredient_name: draft.ingredient_name,
        quantity_per_unit: draft.quantity_per_unit,
        loss_pct: draft.loss_pct || "0",
        price_per_unit: draft.price_per_unit || "0",
        vat_rate: draft.vat_rate || "0.20",
      });
      setDraft(EMPTY_DRAFT);
      toast.success("Ингредиент добавлен в BOM");
      reload();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка";
      setError(msg);
      toast.error(`Не удалось добавить ингредиент: ${msg}`);
    } finally {
      setAdding(false);
    }
  }

  /**
   * Обработка ввода названия ингредиента. Ищет точное совпадение в
   * каталоге (по имени) — если найдено, автоматически подставляет
   * ingredient_id и latest_price. Пользователь может также ввести
   * новое имя, не из каталога — ingredient_id остаётся null.
   */
  function handleIngredientNameChange(value: string) {
    const match = catalog.find((i) => i.name === value);
    setDraft((prev) => {
      const next = { ...prev, ingredient_name: value };
      if (match !== undefined) {
        next.ingredient_id = match.id;
        // Автозаполняем цену только если поле пустое или совпадало с default 0.
        if (!prev.price_per_unit || prev.price_per_unit === "0") {
          if (match.latest_price !== null && match.latest_price !== undefined) {
            next.price_per_unit = String(match.latest_price);
          }
        }
      } else {
        // Имя не из каталога — сбрасываем привязку.
        next.ingredient_id = null;
      }
      return next;
    });
    clearBomError("ingredient_name");
  }

  const [deletingBomId, setDeletingBomId] = useState<number | null>(null);

  async function handleDeleteConfirmed() {
    if (deletingBomId === null) return;
    const id = deletingBomId;
    setDeletingBomId(null);
    try {
      await deleteBomItem(id);
      toast.success("Ингредиент удалён");
      reload();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка";
      setError(msg);
      toast.error(`Не удалось удалить: ${msg}`);
    }
  }

  // Auto-save при смене production_mode (radio не имеет blur)
  const initialModeRef = useRef(productionMode);
  useEffect(() => {
    if (psk === null) return;
    // Пропустить первый рендер (когда state инициализируется из fetch)
    if (initialModeRef.current === productionMode) return;
    initialModeRef.current = productionMode;
    void saveRates();
  }, [productionMode]); // eslint-disable-line react-hooks/exhaustive-deps

  // Q1: auto-save при смене production_mode_by_year (Select по годам).
  // Сравниваем по сериализованному JSON, чтобы не триггерить save при
  // одинаковых объектах с разной ссылкой.
  const initialModeByYearRef = useRef(JSON.stringify(productionModeByYear));
  useEffect(() => {
    if (psk === null) return;
    const serialized = JSON.stringify(productionModeByYear);
    if (initialModeByYearRef.current === serialized) return;
    initialModeByYearRef.current = serialized;
    void saveRates();
  }, [productionModeByYear]); // eslint-disable-line react-hooks/exhaustive-deps

  async function saveRates() {
    if (psk === null) return;
    setSavingRates(true);
    setError(null);
    try {
      await updateProjectSku(pskId, {
        production_mode: productionMode,
        copacking_rate: copackingRate,
        production_cost_rate: productionCostRate,
        production_mode_by_year: productionModeByYear,
      });
      toast.success("Параметры SKU сохранены");
      reload();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка";
      setError(msg);
      toast.error(`Не удалось сохранить параметры: ${msg}`);
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

  // UX-10: BOM summary by ingredient category — labels
  const CATEGORY_LABELS_BOM: Record<string, string> = {
    raw_material: "Сырьё",
    packaging: "Упаковка",
    other: "Прочее",
  };

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
          {/* Тип производства: own / copacking */}
          <div className="mb-3 flex items-center gap-4">
            <span className="text-sm font-medium flex items-center gap-1.5">
              Тип производства:
              <HelpButton help="project_sku.production_mode" />
            </span>
            <label className="flex items-center gap-1.5 text-sm cursor-pointer">
              <input
                type="radio"
                name={`prod-mode-${pskId}`}
                value="own"
                checked={productionMode === "own"}
                onChange={() => { setProductionMode("own"); }}
                disabled={savingRates}
              />
              Собственное
            </label>
            <label className="flex items-center gap-1.5 text-sm cursor-pointer">
              <input
                type="radio"
                name={`prod-mode-${pskId}`}
                value="copacking"
                checked={productionMode === "copacking"}
                onChange={() => { setProductionMode("copacking"); }}
                disabled={savingRates}
              />
              Копакинг
            </label>
          </div>

          {/* Q1 (2026-05-15): годовой override режима производства. */}
          <ProductionModeByYearEditor
            scalarMode={productionMode}
            value={productionModeByYear}
            onChange={setProductionModeByYear}
            disabled={savingRates}
          />

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {productionMode === "own" ? (
              <div className="space-y-2">
                <Label htmlFor="production_cost_rate" className="flex items-center gap-1.5">
                  Произв. затраты, % от цены отгрузки
                  <HelpButton help="project_sku.production_cost_rate" />
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
            ) : (
              <div className="space-y-2">
                <Label htmlFor="copacking_rate" className="flex items-center gap-1.5">
                  Тариф копакера, ₽/ед.
                  <HelpButton help="project_sku.copacking_rate" />
                </Label>
                <Input
                  id="copacking_rate"
                  type="number"
                  step="0.01"
                  min="0"
                  value={copackingRate}
                  onChange={(e) => setCopackingRate(e.target.value)}
                  onBlur={saveRates}
                  disabled={savingRates}
                />
              </div>
            )}
            <p className="col-span-full text-xs text-muted-foreground">
              КАиУР и Маркетинг настраиваются по каналам в разделе
              «Дистрибуция → Каналы» (Q6, 2026-05-15).
            </p>
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
            <div className="text-right space-y-1">
              <p className="text-xs text-muted-foreground">
                COGS на единицу (preview)
              </p>
              <p className="text-lg font-semibold">
                {formatMoney(String(cogsPreview))}
              </p>
              {Object.keys(categorySums).length > 0 && (
                <div className="text-xs text-muted-foreground space-y-0.5">
                  {Object.entries(categorySums).map(([cat, sum]) => (
                    <div key={cat} className="flex justify-end gap-2">
                      <span>{CATEGORY_LABELS_BOM[cat] ?? cat}:</span>
                      <span className="font-medium text-foreground">
                        {formatMoney(String(sum))}
                      </span>
                    </div>
                  ))}
                </div>
              )}
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
                  <TableHead {...sortableHeaderProps(toggleBomSort, "name")}>
                    Ингредиент{sortIndicator(bomSortState, "name")}
                  </TableHead>
                  <TableHead {...sortableHeaderProps(toggleBomSort, "qty", "text-right")}>
                    Кол-во/ед{sortIndicator(bomSortState, "qty")}
                  </TableHead>
                  <TableHead {...sortableHeaderProps(toggleBomSort, "loss", "text-right")}>
                    % потерь{sortIndicator(bomSortState, "loss")}
                  </TableHead>
                  <TableHead {...sortableHeaderProps(toggleBomSort, "price", "text-right")}>
                    Цена/ед, ₽ (без НДС){sortIndicator(bomSortState, "price")}
                  </TableHead>
                  <TableHead className="text-right">НДС, %</TableHead>
                  <TableHead {...sortableHeaderProps(toggleBomSort, "cost", "text-right")}>
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
                      <TableCell className="text-right text-muted-foreground">
                        {(Number(b.vat_rate ?? 0.20) * 100).toFixed(0)}%
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
            <div className="col-span-3 space-y-1">
              <Label htmlFor="bom-name" className="text-xs">
                Ингредиент *
                {draft.ingredient_id !== null && (
                  <span className="ml-1 text-[10px] font-normal text-green-700">
                    ✓ из каталога
                  </span>
                )}
              </Label>
              <Input
                id="bom-name"
                list="bom-ingredient-catalog"
                required
                value={draft.ingredient_name}
                onChange={(e) => handleIngredientNameChange(e.target.value)}
                aria-invalid={!!bomErrors.ingredient_name}
                disabled={adding}
                placeholder={
                  catalog.length > 0
                    ? "Начните печатать или выберите из каталога"
                    : "Сахар"
                }
              />
              {catalog.length > 0 && (
                <datalist id="bom-ingredient-catalog">
                  {catalog.map((ing) => (
                    <option key={ing.id} value={ing.name}>
                      {ing.category === "raw_material"
                        ? "Сырьё"
                        : ing.category === "packaging"
                          ? "Упаковка"
                          : "Прочее"}
                      {ing.latest_price !== null &&
                      ing.latest_price !== undefined
                        ? ` · ${ing.latest_price} ₽/${ing.unit}`
                        : ""}
                    </option>
                  ))}
                </datalist>
              )}
              <FieldError error={bomErrors.ingredient_name} />
            </div>
            <div className="col-span-2 space-y-1">
              <Label htmlFor="bom-qty" className="flex items-center gap-1.5 text-xs">
                Кол-во *
                <HelpButton help="bom.quantity_per_unit" />
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
              <Label htmlFor="bom-loss" className="flex items-center gap-1.5 text-xs">
                Потери (доля)
                <HelpButton help="bom.loss_pct" />
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
              <Label htmlFor="bom-price" className="flex items-center gap-1.5 text-xs">
                Цена/ед, ₽ (без НДС)
                <HelpButton help="bom.price_per_unit" />
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
            <div className="col-span-2 space-y-1">
              <Label htmlFor="bom-vat" className="flex items-center gap-1.5 text-xs">
                НДС (доля)
                <HelpButton help="bom.vat_rate" />
              </Label>
              <Input
                id="bom-vat"
                type="number"
                step="0.01"
                min="0"
                max="1"
                value={draft.vat_rate}
                onChange={(e) => {
                  setDraft({ ...draft, vat_rate: e.target.value });
                  clearBomError("vat_rate");
                }}
                aria-invalid={!!bomErrors.vat_rate}
                disabled={adding}
                placeholder="0.20"
                list="vat-presets"
              />
              <datalist id="vat-presets">
                <option value="0" />
                <option value="0.10" />
                <option value="0.20" />
              </datalist>
              <FieldError error={bomErrors.vat_rate} />
            </div>
            <div className="col-span-1">
              <Button type="submit" disabled={adding} className="w-full" size="sm">
                {adding ? "..." : "+"}
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
