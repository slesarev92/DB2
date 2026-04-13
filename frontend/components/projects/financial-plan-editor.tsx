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
  getFinancialPlan,
  putFinancialPlan,
} from "@/lib/financial-plan";
import { formatMoney } from "@/lib/format";

import {
  OPEX_CATEGORIES,
  OPEX_CATEGORY_LABELS,
  type FinancialPlanItem,
  type OpexItem,
} from "@/types/api";

interface FinancialPlanEditorProps {
  projectId: number;
}

/** Годы, для которых раскрыта разбивка OPEX. */
type ExpandedSet = Set<number>;

/**
 * Редактор CAPEX/OPEX по годам проекта.
 *
 * UI: таблица из 10 строк Y1..Y10 × колонки (Год, CAPEX ₽, OPEX ₽).
 * Кнопка «Разбить» раскрывает вложенные строки статей OPEX (B-19).
 * Backend маппит year → period_id автоматически.
 */
export function FinancialPlanEditor({ projectId }: FinancialPlanEditorProps) {
  const [items, setItems] = useState<FinancialPlanItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [expanded, setExpanded] = useState<ExpandedSet>(new Set());

  useEffect(() => {
    let cancelled = false;
    getFinancialPlan(projectId)
      .then((data) => {
        if (!cancelled) {
          setItems(data);
          // Авто-раскрываем годы у которых уже есть items
          const autoExpand = new Set<number>();
          for (const d of data) {
            if (d.opex_items.length > 0) autoExpand.add(d.year);
          }
          if (autoExpand.size > 0) setExpanded(autoExpand);
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof ApiError ? err.detail ?? err.message : "Ошибка",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  // --- Мутации state ---

  function updateItem(year: number, field: "capex" | "opex", value: string) {
    setItems((prev) => {
      if (prev === null) return prev;
      return prev.map((item) =>
        item.year === year ? { ...item, [field]: value } : item,
      );
    });
  }

  function toggleExpand(year: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(year)) {
        next.delete(year);
      } else {
        next.add(year);
      }
      return next;
    });
  }

  function addOpexItem(year: number) {
    setItems((prev) => {
      if (prev === null) return prev;
      return prev.map((item) => {
        if (item.year !== year) return item;
        const newItem: OpexItem = { category: "other", name: "", amount: "0" };
        const newItems = [...item.opex_items, newItem];
        return {
          ...item,
          opex_items: newItems,
          opex: sumOpexItems(newItems),
        };
      });
    });
    // Авто-раскрываем
    setExpanded((prev) => new Set(prev).add(year));
  }

  function removeOpexItem(year: number, idx: number) {
    setItems((prev) => {
      if (prev === null) return prev;
      return prev.map((item) => {
        if (item.year !== year) return item;
        const newItems = item.opex_items.filter((_, i) => i !== idx);
        return {
          ...item,
          opex_items: newItems,
          opex: newItems.length > 0 ? sumOpexItems(newItems) : item.opex,
        };
      });
    });
  }

  function updateOpexItem(
    year: number,
    idx: number,
    field: "category" | "name" | "amount",
    value: string,
  ) {
    setItems((prev) => {
      if (prev === null) return prev;
      return prev.map((item) => {
        if (item.year !== year) return item;
        const newItems = item.opex_items.map((oi, i) =>
          i === idx ? { ...oi, [field]: value } : oi,
        );
        return {
          ...item,
          opex_items: newItems,
          opex: sumOpexItems(newItems),
        };
      });
    });
  }

  async function handleSave() {
    if (items === null) return;
    setSaving(true);
    setError(null);
    try {
      // Sanitize: пустые строки → "0" чтобы backend Pydantic не падал на Decimal("")
      const sanitized = items.map((item) => ({
        ...item,
        capex: item.capex === "" ? "0" : item.capex,
        opex: item.opex === "" ? "0" : item.opex,
        opex_items: item.opex_items.map((oi) => ({
          ...oi,
          amount: oi.amount === "" ? "0" : oi.amount,
        })),
      }));
      const saved = await putFinancialPlan(projectId, { items: sanitized });
      setItems(saved);
      setSavedAt(new Date());
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.detail ?? err.message
          : "Ошибка сохранения",
      );
    } finally {
      setSaving(false);
    }
  }

  // Итоги
  const totalCapex =
    items?.reduce((sum, i) => sum + Number(i.capex || 0), 0) ?? 0;
  const totalOpex =
    items?.reduce((sum, i) => sum + Number(i.opex || 0), 0) ?? 0;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div>
            <CardTitle className="text-base">
              Инвестиции и project OPEX по годам
            </CardTitle>
            <CardDescription>
              CAPEX (инвестиции) и периодические OPEX (листинги, запускной
              маркетинг и т.п.) на уровне всего проекта. Нажмите «Разбить»
              чтобы детализировать OPEX по статьям. После сохранения нажмите
              «Пересчитать» в табе «Результаты».
            </CardDescription>
          </div>
          <div className="flex items-center gap-3">
            {savedAt !== null && !saving && error === null && (
              <span className="text-xs text-muted-foreground">
                Сохранено {savedAt.toLocaleTimeString("ru-RU")}
              </span>
            )}
            <Button
              size="sm"
              onClick={handleSave}
              disabled={saving || items === null}
            >
              {saving ? "Сохранение..." : "Сохранить"}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {items === null && error === null && (
          <p className="text-sm text-muted-foreground">Загрузка...</p>
        )}

        {error !== null && (
          <p className="mb-3 text-sm text-destructive" role="alert">
            {error}
          </p>
        )}

        {items !== null && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-24">Год</TableHead>
                <TableHead>CAPEX, ₽</TableHead>
                <TableHead>Project OPEX, ₽</TableHead>
                <TableHead className="w-28" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item) => {
                const isExpanded = expanded.has(item.year);
                const hasItems = item.opex_items.length > 0;
                return (
                  <OpexYearRow
                    key={item.year}
                    item={item}
                    isExpanded={isExpanded}
                    hasItems={hasItems}
                    saving={saving}
                    onUpdateItem={updateItem}
                    onToggleExpand={toggleExpand}
                    onAddOpexItem={addOpexItem}
                    onRemoveOpexItem={removeOpexItem}
                    onUpdateOpexItem={updateOpexItem}
                  />
                );
              })}
              <TableRow className="border-t-2 font-semibold">
                <TableCell>Итого</TableCell>
                <TableCell className="pl-3">
                  {formatMoney(String(totalCapex))}
                </TableCell>
                <TableCell className="pl-3">
                  {formatMoney(String(totalOpex))}
                </TableCell>
                <TableCell />
              </TableRow>
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

// --- Helpers ---

function sumOpexItems(items: OpexItem[]): string {
  const total = items.reduce((s, oi) => s + Number(oi.amount || 0), 0);
  return String(total);
}

// --- Sub-component: year row + expandable opex items ---

interface OpexYearRowProps {
  item: FinancialPlanItem;
  isExpanded: boolean;
  hasItems: boolean;
  saving: boolean;
  onUpdateItem: (year: number, field: "capex" | "opex", value: string) => void;
  onToggleExpand: (year: number) => void;
  onAddOpexItem: (year: number) => void;
  onRemoveOpexItem: (year: number, idx: number) => void;
  onUpdateOpexItem: (
    year: number,
    idx: number,
    field: "category" | "name" | "amount",
    value: string,
  ) => void;
}

function OpexYearRow({
  item,
  isExpanded,
  hasItems,
  saving,
  onUpdateItem,
  onToggleExpand,
  onAddOpexItem,
  onRemoveOpexItem,
  onUpdateOpexItem,
}: OpexYearRowProps) {
  return (
    <>
      <TableRow>
        <TableCell className="font-medium">Y{item.year}</TableCell>
        <TableCell>
          <Input
            type="number"
            step="1"
            min="0"
            value={item.capex}
            onChange={(e) =>
              onUpdateItem(item.year, "capex", e.target.value)
            }
            disabled={saving}
            className="max-w-xs"
          />
        </TableCell>
        <TableCell>
          {hasItems ? (
            <span className="text-sm text-muted-foreground pl-3">
              {formatMoney(item.opex)}
            </span>
          ) : (
            <Input
              type="number"
              step="1"
              min="0"
              value={item.opex}
              onChange={(e) =>
                onUpdateItem(item.year, "opex", e.target.value)
              }
              disabled={saving}
              className="max-w-xs"
            />
          )}
        </TableCell>
        <TableCell>
          <Button
            variant={isExpanded ? "secondary" : "outline"}
            size="sm"
            onClick={() => {
              if (!isExpanded && !hasItems) {
                onAddOpexItem(item.year);
              } else {
                onToggleExpand(item.year);
              }
            }}
            disabled={saving}
            className="text-xs"
          >
            {isExpanded ? "Свернуть" : "Разбить"}
          </Button>
        </TableCell>
      </TableRow>
      {isExpanded && (
        <>
          {item.opex_items.map((oi, idx) => (
            <TableRow
              key={`${item.year}-oi-${idx}`}
              className="bg-muted/30"
            >
              <TableCell />
              <TableCell />
              <TableCell>
                <div className="flex items-center gap-2">
                  <Select
                    value={oi.category || "other"}
                    onValueChange={(v) =>
                      onUpdateOpexItem(item.year, idx, "category", v ?? "other")
                    }
                    disabled={saving}
                  >
                    <SelectTrigger className="h-8 w-[130px] text-xs">
                      <SelectValue placeholder="Категория" />
                    </SelectTrigger>
                    <SelectContent>
                      {OPEX_CATEGORIES.map((c) => (
                        <SelectItem key={c} value={c} className="text-xs">
                          {OPEX_CATEGORY_LABELS[c]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Input
                    placeholder="Статья"
                    value={oi.name}
                    onChange={(e) =>
                      onUpdateOpexItem(item.year, idx, "name", e.target.value)
                    }
                    disabled={saving}
                    className="max-w-[180px] text-sm"
                  />
                  <Input
                    type="number"
                    step="1"
                    min="0"
                    value={oi.amount}
                    onChange={(e) =>
                      onUpdateOpexItem(
                        item.year,
                        idx,
                        "amount",
                        e.target.value,
                      )
                    }
                    disabled={saving}
                    className="max-w-[120px] text-sm"
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onRemoveOpexItem(item.year, idx)}
                    disabled={saving}
                    className="text-destructive hover:text-destructive px-2"
                    title="Удалить статью"
                  >
                    &times;
                  </Button>
                </div>
              </TableCell>
              <TableCell />
            </TableRow>
          ))}
          <TableRow className="bg-muted/30">
            <TableCell />
            <TableCell />
            <TableCell>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onAddOpexItem(item.year)}
                disabled={saving}
                className="text-xs text-primary"
              >
                + Добавить статью
              </Button>
            </TableCell>
            <TableCell />
          </TableRow>
        </>
      )}
    </>
  );
}
