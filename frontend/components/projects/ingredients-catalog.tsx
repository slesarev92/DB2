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
import { formatMoney } from "@/lib/format";
import {
  addIngredientPrice,
  createIngredient,
  deleteIngredient,
  listIngredientPrices,
  listIngredients,
} from "@/lib/ingredients";
import {
  useSortableTable,
  sortIndicator,
  type SortableColumn,
} from "@/lib/use-sortable-table";

import type { IngredientPriceRead, IngredientRead } from "@/types/api";

const ING_SORT_COLUMNS: SortableColumn<IngredientRead, string>[] = [
  { key: "name", accessor: (i) => i.name },
  { key: "unit", accessor: (i) => i.unit },
  { key: "category", accessor: (i) => i.category },
  {
    key: "price",
    accessor: (i) => (i.latest_price !== null ? Number(i.latest_price) : null),
  },
];

const CATEGORY_LABELS: Record<string, string> = {
  raw_material: "Сырьё",
  packaging: "Упаковка",
  other: "Прочее",
};

/**
 * Каталог ингредиентов с историей цен (B-04).
 *
 * Глобальный справочник: не привязан к конкретному проекту.
 * Используется при создании BOM-позиций (auto-fill ingredient_name + price).
 */
export function IngredientsCatalog() {
  const [ingredients, setIngredients] = useState<IngredientRead[]>([]);
  const { sorted: sortedIngredients, sortState: ingSortState, toggleSort: toggleIngSort } =
    useSortableTable(ingredients, ING_SORT_COLUMNS);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // New ingredient form
  const [newName, setNewName] = useState("");
  const [newUnit, setNewUnit] = useState("kg");
  const [newCategory, setNewCategory] = useState("raw_material");
  const [adding, setAdding] = useState(false);

  // Price history
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [prices, setPrices] = useState<IngredientPriceRead[]>([]);
  const [newPrice, setNewPrice] = useState("");
  const [newDate, setNewDate] = useState("");
  const [addingPrice, setAddingPrice] = useState(false);

  async function loadIngredients() {
    setLoading(true);
    try {
      const data = await listIngredients();
      setIngredients(data);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadIngredients();
  }, []);

  async function handleAdd() {
    if (!newName.trim()) return;
    setAdding(true);
    setError(null);
    try {
      await createIngredient({
        name: newName.trim(),
        unit: newUnit,
        category: newCategory,
      });
      setNewName("");
      await loadIngredients();
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
      await deleteIngredient(id);
      if (expandedId === id) setExpandedId(null);
      await loadIngredients();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка",
      );
    }
  }

  async function handleTogglePrices(id: number) {
    if (expandedId === id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(id);
    try {
      const data = await listIngredientPrices(id);
      setPrices(data);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка",
      );
    }
  }

  async function handleAddPrice() {
    if (expandedId === null || !newPrice || !newDate) return;
    setAddingPrice(true);
    try {
      await addIngredientPrice(expandedId, {
        price_per_unit: newPrice,
        effective_date: newDate,
      });
      const data = await listIngredientPrices(expandedId);
      setPrices(data);
      setNewPrice("");
      setNewDate("");
      await loadIngredients();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка",
      );
    } finally {
      setAddingPrice(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Каталог ингредиентов</CardTitle>
        <CardDescription>
          Глобальный справочник сырья и упаковки с историей цен. При
          создании BOM-позиции выберите ингредиент — имя и цена
          заполнятся автоматически.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error !== null && (
          <p className="text-sm text-destructive">{error}</p>
        )}

        {/* Add new ingredient */}
        <div className="flex items-end gap-2">
          <Input
            placeholder="Название"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            className="max-w-[200px]"
          />
          <Input
            placeholder="Ед."
            value={newUnit}
            onChange={(e) => setNewUnit(e.target.value)}
            className="w-16"
          />
          <Select value={newCategory} onValueChange={(v) => { if (v) setNewCategory(v); }}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="raw_material">Сырьё</SelectItem>
              <SelectItem value="packaging">Упаковка</SelectItem>
              <SelectItem value="other">Прочее</SelectItem>
            </SelectContent>
          </Select>
          <Button size="sm" onClick={handleAdd} disabled={adding}>
            {adding ? "..." : "Добавить"}
          </Button>
        </div>

        {loading && <p className="text-sm text-muted-foreground">Загрузка...</p>}

        {!loading && ingredients.length === 0 && (
          <EmptyState
            title="Каталог пуст"
            description="Добавьте первый ингредиент для автозаполнения BOM."
          />
        )}

        {ingredients.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="cursor-pointer select-none" onClick={() => toggleIngSort("name")}>
                  Название{sortIndicator(ingSortState, "name")}
                </TableHead>
                <TableHead className="w-16 cursor-pointer select-none" onClick={() => toggleIngSort("unit")}>
                  Ед.{sortIndicator(ingSortState, "unit")}
                </TableHead>
                <TableHead className="w-24 cursor-pointer select-none" onClick={() => toggleIngSort("category")}>
                  Категория{sortIndicator(ingSortState, "category")}
                </TableHead>
                <TableHead className="w-28 cursor-pointer select-none" onClick={() => toggleIngSort("price")}>
                  Цена{sortIndicator(ingSortState, "price")}
                </TableHead>
                <TableHead className="w-24" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedIngredients.map((ing) => (
                <>
                  <TableRow key={ing.id}>
                    <TableCell className="font-medium">{ing.name}</TableCell>
                    <TableCell className="text-sm">{ing.unit}</TableCell>
                    <TableCell className="text-sm">
                      {CATEGORY_LABELS[ing.category] ?? ing.category}
                    </TableCell>
                    <TableCell className="text-sm">
                      {ing.latest_price
                        ? formatMoney(ing.latest_price)
                        : "—"}
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button
                          variant={expandedId === ing.id ? "secondary" : "ghost"}
                          size="sm"
                          className="text-xs"
                          onClick={() => handleTogglePrices(ing.id)}
                        >
                          Цены
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-xs text-destructive"
                          onClick={() => setDeletingId(ing.id)}
                        >
                          &times;
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                  {expandedId === ing.id && (
                    <TableRow className="bg-muted/30">
                      <TableCell colSpan={5}>
                        <div className="space-y-2 py-1">
                          <div className="flex items-end gap-2">
                            <Input
                              type="number"
                              placeholder="Цена"
                              value={newPrice}
                              onChange={(e) => setNewPrice(e.target.value)}
                              className="w-28 text-sm"
                            />
                            <Input
                              type="date"
                              value={newDate}
                              onChange={(e) => setNewDate(e.target.value)}
                              className="w-36 text-sm"
                            />
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={handleAddPrice}
                              disabled={addingPrice}
                              className="text-xs"
                            >
                              + Цена
                            </Button>
                          </div>
                          {prices.length > 0 && (
                            <div className="text-xs space-y-0.5">
                              {prices.map((p) => (
                                <div
                                  key={p.id}
                                  className="flex gap-3 text-muted-foreground"
                                >
                                  <span>{p.effective_date}</span>
                                  <span className="font-medium text-foreground">
                                    {formatMoney(p.price_per_unit)}
                                  </span>
                                  {p.notes && <span>({p.notes})</span>}
                                </div>
                              ))}
                            </div>
                          )}
                          {prices.length === 0 && (
                            <p className="text-xs text-muted-foreground">
                              Нет записей о ценах.
                            </p>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>

      <ConfirmDialog
        open={deletingId !== null}
        onConfirm={handleDeleteConfirmed}
        onCancel={() => setDeletingId(null)}
        title="Удалить ингредиент?"
        description="Связи с BOM-позициями будут разорваны."
      />
    </Card>
  );
}
