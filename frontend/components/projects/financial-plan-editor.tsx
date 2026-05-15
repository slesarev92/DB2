"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { HelpButton } from "@/components/ui/help-button";
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
  CAPEX_CATEGORIES,
  CAPEX_CATEGORY_LABELS,
  OPEX_CATEGORIES,
  OPEX_CATEGORY_LABELS,
  type CapexItem,
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
          // Авто-раскрываем годы у которых уже есть статьи (OPEX или CAPEX)
          const autoExpand = new Set<number>();
          for (const d of data) {
            if (d.opex_items.length > 0 || d.capex_items.length > 0) {
              autoExpand.add(d.year);
            }
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

  // B.9 (2026-05-15): аналогичные мутаторы для capex_items.
  function addCapexItem(year: number) {
    setItems((prev) => {
      if (prev === null) return prev;
      return prev.map((item) => {
        if (item.year !== year) return item;
        const newItem: CapexItem = { category: "other", name: "", amount: "0" };
        const newItems = [...item.capex_items, newItem];
        return {
          ...item,
          capex_items: newItems,
          capex: sumCapexItems(newItems),
        };
      });
    });
    setExpanded((prev) => new Set(prev).add(year));
  }

  function removeCapexItem(year: number, idx: number) {
    setItems((prev) => {
      if (prev === null) return prev;
      return prev.map((item) => {
        if (item.year !== year) return item;
        const newItems = item.capex_items.filter((_, i) => i !== idx);
        return {
          ...item,
          capex_items: newItems,
          capex: newItems.length > 0 ? sumCapexItems(newItems) : item.capex,
        };
      });
    });
  }

  function updateCapexItem(
    year: number,
    idx: number,
    field: "category" | "name" | "amount",
    value: string,
  ) {
    setItems((prev) => {
      if (prev === null) return prev;
      return prev.map((item) => {
        if (item.year !== year) return item;
        const newItems = item.capex_items.map((ci, i) =>
          i === idx ? { ...ci, [field]: value } : ci,
        );
        return {
          ...item,
          capex_items: newItems,
          capex: sumCapexItems(newItems),
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
        capex_items: item.capex_items.map((ci) => ({
          ...ci,
          amount: ci.amount === "" ? "0" : ci.amount,
        })),
      }));
      const saved = await putFinancialPlan(projectId, { items: sanitized });
      setItems(saved);
      setSavedAt(new Date());
      toast.success("Финансовый план сохранён");
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.detail ?? err.message
          : "Ошибка сохранения";
      setError(msg);
      toast.error(`Не удалось сохранить: ${msg}`);
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
          <div className="overflow-x-auto">
            <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-24">Год</TableHead>
                <TableHead>
                  <span className="inline-flex items-center gap-1.5">
                    CAPEX, ₽
                    <HelpButton help="financial_plan.capex" />
                  </span>
                </TableHead>
                <TableHead>
                  <span className="inline-flex items-center gap-1.5">
                    Project OPEX, ₽
                    <HelpButton help="financial_plan.opex" />
                  </span>
                </TableHead>
                <TableHead className="w-28" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item) => {
                const isExpanded = expanded.has(item.year);
                return (
                  <PlanYearRow
                    key={item.year}
                    item={item}
                    isExpanded={isExpanded}
                    saving={saving}
                    onUpdateItem={updateItem}
                    onToggleExpand={toggleExpand}
                    onAddOpexItem={addOpexItem}
                    onRemoveOpexItem={removeOpexItem}
                    onUpdateOpexItem={updateOpexItem}
                    onAddCapexItem={addCapexItem}
                    onRemoveCapexItem={removeCapexItem}
                    onUpdateCapexItem={updateCapexItem}
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
          </div>
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

function sumCapexItems(items: CapexItem[]): string {
  const total = items.reduce((s, ci) => s + Number(ci.amount || 0), 0);
  return String(total);
}

// --- Sub-component: year row + expandable OPEX и CAPEX статей ---

interface PlanYearRowProps {
  item: FinancialPlanItem;
  isExpanded: boolean;
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
  onAddCapexItem: (year: number) => void;
  onRemoveCapexItem: (year: number, idx: number) => void;
  onUpdateCapexItem: (
    year: number,
    idx: number,
    field: "category" | "name" | "amount",
    value: string,
  ) => void;
}

function PlanYearRow({
  item,
  isExpanded,
  saving,
  onUpdateItem,
  onToggleExpand,
  onAddOpexItem,
  onRemoveOpexItem,
  onUpdateOpexItem,
  onAddCapexItem,
  onRemoveCapexItem,
  onUpdateCapexItem,
}: PlanYearRowProps) {
  const hasOpexItems = item.opex_items.length > 0;
  const hasCapexItems = item.capex_items.length > 0;
  const hasAnyItems = hasOpexItems || hasCapexItems;
  return (
    <>
      <TableRow>
        <TableCell className="font-medium">Y{item.year}</TableCell>
        <TableCell>
          {hasCapexItems ? (
            <span className="text-sm text-muted-foreground pl-3">
              {formatMoney(item.capex)}
            </span>
          ) : (
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
          )}
        </TableCell>
        <TableCell>
          {hasOpexItems ? (
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
              if (!isExpanded && !hasAnyItems) {
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
          {/* CAPEX статьи (B.9 / MEMO 2.1) */}
          {item.capex_items.map((ci, idx) => (
            <TableRow
              key={`${item.year}-ci-${idx}`}
              className="bg-muted/30"
            >
              <TableCell />
              <TableCell>
                <div className="flex items-center gap-2">
                  <Select
                    value={ci.category || "other"}
                    onValueChange={(v) =>
                      onUpdateCapexItem(item.year, idx, "category", v ?? "other")
                    }
                    disabled={saving}
                    items={CAPEX_CATEGORY_LABELS}
                  >
                    <SelectTrigger className="h-8 w-[160px] text-xs">
                      <SelectValue placeholder="Категория" />
                    </SelectTrigger>
                    <SelectContent>
                      {CAPEX_CATEGORIES.map((c) => (
                        <SelectItem key={c} value={c} className="text-xs">
                          {CAPEX_CATEGORY_LABELS[c]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Input
                    placeholder="Статья CAPEX"
                    value={ci.name}
                    onChange={(e) =>
                      onUpdateCapexItem(item.year, idx, "name", e.target.value)
                    }
                    disabled={saving}
                    className="max-w-[180px] text-sm"
                  />
                  <Input
                    type="number"
                    step="1"
                    min="0"
                    value={ci.amount}
                    onChange={(e) =>
                      onUpdateCapexItem(
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
                    onClick={() => onRemoveCapexItem(item.year, idx)}
                    disabled={saving}
                    className="text-destructive hover:text-destructive px-2"
                    title="Удалить статью"
                  >
                    &times;
                  </Button>
                </div>
              </TableCell>
              <TableCell />
              <TableCell />
            </TableRow>
          ))}
          <TableRow className="bg-muted/30">
            <TableCell />
            <TableCell>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onAddCapexItem(item.year)}
                disabled={saving}
                className="text-xs text-primary"
              >
                + Статья CAPEX
              </Button>
            </TableCell>
            <TableCell />
            <TableCell />
          </TableRow>

          {/* OPEX статьи (B-19) */}
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
                    items={OPEX_CATEGORY_LABELS}
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
                    placeholder="Статья OPEX"
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
                + Статья OPEX
              </Button>
            </TableCell>
            <TableCell />
          </TableRow>
        </>
      )}
    </>
  );
}
