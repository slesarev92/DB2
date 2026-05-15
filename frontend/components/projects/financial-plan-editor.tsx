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
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api";
import {
  getFinancialPlan,
  putFinancialPlan,
} from "@/lib/financial-plan";
import {
  isLegacyData,
  periodLabel,
} from "@/lib/financial-plan-utils";

import {
  CAPEX_CATEGORIES,
  CAPEX_CATEGORY_LABELS,
  OPEX_CATEGORIES,
  OPEX_CATEGORY_LABELS,
  type CapexItem,
  type FinancialPlanItem,
  type OpexItem,
} from "@/types/api";

import {
  FinancialPlanBulkFill,
  type BulkFillTarget,
} from "./financial-plan-bulk-fill";

interface Props {
  projectId: number;
}

type ItemKind = "capex" | "opex";

/**
 * Редактор финансового плана с per-period гранулярностью (B.9b).
 *
 * 43 колонки (M1..M36 + Y4..Y10), sticky left = имена строк.
 * Группирующие заголовки Y1/Y2/Y3 над месяцами.
 * Каждая статья CAPEX/OPEX = строка таблицы с 43 ячейками.
 */
export function FinancialPlanEditor({ projectId }: Props) {
  const [items, setItems] = useState<FinancialPlanItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [collapsed, setCollapsed] = useState<{ capex: boolean; opex: boolean }>(
    { capex: false, opex: false },
  );

  useEffect(() => {
    let cancelled = false;
    getFinancialPlan(projectId)
      .then((data) => {
        if (!cancelled) setItems(data);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.detail ?? err.message : "Ошибка");
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const showLegacyBanner = useMemo(
    () => (items !== null ? isLegacyData(items) : false),
    [items],
  );

  const capexArticleKeys = useMemo(
    () => collectArticleKeys(items, "capex"),
    [items],
  );
  const opexArticleKeys = useMemo(
    () => collectArticleKeys(items, "opex"),
    [items],
  );

  function updatePeriodTotal(
    periodNumber: number,
    field: "capex" | "opex",
    value: string,
  ) {
    setItems((prev) =>
      prev === null
        ? prev
        : prev.map((p) =>
            p.period_number === periodNumber ? { ...p, [field]: value } : p,
          ),
    );
  }

  function updateArticleAmount(
    periodNumber: number,
    kind: ItemKind,
    category: string,
    name: string,
    amount: string,
  ) {
    setItems((prev) => {
      if (prev === null) return prev;
      return prev.map((p) => {
        if (p.period_number !== periodNumber) return p;
        if (kind === "capex") {
          const list = p.capex_items;
          const idx = list.findIndex(
            (it) => it.category === category && it.name === name,
          );
          let newList: CapexItem[];
          if (idx === -1) {
            newList = [...list, { category, name, amount }];
          } else {
            newList = list.map((it, i) => (i === idx ? { ...it, amount } : it));
          }
          if (amount === "" || Number(amount) === 0) {
            newList = newList.filter(
              (it) => !(it.category === category && it.name === name),
            );
          }
          const newTotal = newList.reduce(
            (s, it) => s + Number(it.amount || 0),
            0,
          );
          return { ...p, capex_items: newList, capex: String(newTotal) };
        } else {
          const list = p.opex_items;
          const idx = list.findIndex(
            (it) => it.category === category && it.name === name,
          );
          let newList: OpexItem[];
          if (idx === -1) {
            newList = [...list, { category, name, amount }];
          } else {
            newList = list.map((it, i) => (i === idx ? { ...it, amount } : it));
          }
          if (amount === "" || Number(amount) === 0) {
            newList = newList.filter(
              (it) => !(it.category === category && it.name === name),
            );
          }
          const newTotal = newList.reduce(
            (s, it) => s + Number(it.amount || 0),
            0,
          );
          return { ...p, opex_items: newList, opex: String(newTotal) };
        }
      });
    });
  }

  function addArticle(kind: ItemKind, category: string, name: string) {
    setItems((prev) => {
      if (prev === null) return prev;
      return prev.map((p) => {
        if (p.period_number !== 1) return p;
        if (kind === "capex") {
          if (
            p.capex_items.some(
              (it) => it.category === category && it.name === name,
            )
          ) {
            return p;
          }
          const next: CapexItem[] = [
            ...p.capex_items,
            { category, name, amount: "0" },
          ];
          return { ...p, capex_items: next };
        } else {
          if (
            p.opex_items.some(
              (it) => it.category === category && it.name === name,
            )
          ) {
            return p;
          }
          const next: OpexItem[] = [
            ...p.opex_items,
            { category, name, amount: "0" },
          ];
          return { ...p, opex_items: next };
        }
      });
    });
  }

  function removeArticle(kind: ItemKind, category: string, name: string) {
    setItems((prev) => {
      if (prev === null) return prev;
      return prev.map((p) => {
        if (kind === "capex") {
          const newList = p.capex_items.filter(
            (it) => !(it.category === category && it.name === name),
          );
          if (newList.length === p.capex_items.length) return p;
          const newTotal = newList.reduce(
            (s, it) => s + Number(it.amount || 0),
            0,
          );
          return { ...p, capex_items: newList, capex: String(newTotal) };
        } else {
          const newList = p.opex_items.filter(
            (it) => !(it.category === category && it.name === name),
          );
          if (newList.length === p.opex_items.length) return p;
          const newTotal = newList.reduce(
            (s, it) => s + Number(it.amount || 0),
            0,
          );
          return { ...p, opex_items: newList, opex: String(newTotal) };
        }
      });
    });
  }

  function applyBulkFill(
    rowKey: string,
    updates: Array<[number, string]>,
  ): void {
    const dotIdx = rowKey.indexOf(".");
    if (dotIdx === -1) return;
    const kind = rowKey.slice(0, dotIdx) as ItemKind;
    const tail = rowKey.slice(dotIdx + 1);
    if (tail === "total") {
      for (const [pn, val] of updates) {
        updatePeriodTotal(pn, kind, val);
      }
    } else {
      const pipeIdx = tail.indexOf("|");
      if (pipeIdx === -1) return;
      const category = tail.slice(0, pipeIdx);
      const name = tail.slice(pipeIdx + 1);
      for (const [pn, val] of updates) {
        updateArticleAmount(pn, kind, category, name, val);
      }
    }
  }

  async function handleSave() {
    if (items === null) return;
    setSaving(true);
    setError(null);
    try {
      const sanitized = items.map((p) => ({
        ...p,
        capex: p.capex === "" ? "0" : p.capex,
        opex: p.opex === "" ? "0" : p.opex,
        opex_items: p.opex_items.map((oi) => ({
          ...oi,
          amount: oi.amount === "" ? "0" : oi.amount,
        })),
        capex_items: p.capex_items.map((ci) => ({
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
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка сохранения";
      setError(msg);
      toast.error(`Не удалось сохранить: ${msg}`);
    } finally {
      setSaving(false);
    }
  }

  const periods = useMemo(
    () => Array.from({ length: 43 }, (_, i) => i + 1),
    [],
  );

  const bulkRows: BulkFillTarget[] = useMemo(() => {
    const rows: BulkFillTarget[] = [
      { rowKey: "capex.total", label: "CAPEX итог (без статей)" },
      ...capexArticleKeys.map((k) => ({
        rowKey: `capex.${k.category}|${k.name}`,
        label: `CAPEX • ${
          (CAPEX_CATEGORY_LABELS as Record<string, string>)[k.category] ??
          k.category
        } • ${k.name}`,
      })),
      { rowKey: "opex.total", label: "OPEX итог (без статей)" },
      ...opexArticleKeys.map((k) => ({
        rowKey: `opex.${k.category}|${k.name}`,
        label: `OPEX • ${
          (OPEX_CATEGORY_LABELS as Record<string, string>)[k.category] ??
          k.category
        } • ${k.name}`,
      })),
    ];
    return rows;
  }, [capexArticleKeys, opexArticleKeys]);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div>
            <CardTitle className="text-base">
              Финансовый план (помесячно Y1-Y3, годами Y4-Y10)
            </CardTitle>
            <CardDescription>
              CAPEX и project OPEX по месяцам первых 3 лет и годам Y4-Y10.
              Используйте <b>Bulk-fill</b> чтобы распределить годовую сумму или
              залить значение на диапазон.
            </CardDescription>
          </div>
          <div className="flex items-center gap-3">
            <FinancialPlanBulkFill
              rows={bulkRows}
              onApply={applyBulkFill}
              disabled={saving || items === null}
            />
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
        {showLegacyBanner && (
          <div className="mb-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
            <b>Финплан сохранён годовыми точками.</b> Все значения сейчас
            видны в первом месяце года (M1, M13, M25). Используйте Bulk-fill →
            «Распределить год» чтобы разнести их по месяцам.
          </div>
        )}

        {items !== null && (
          <div className="overflow-x-auto border rounded">
            <table className="min-w-full text-xs border-collapse">
              <thead>
                <tr className="bg-muted">
                  <th
                    className="sticky left-0 bg-muted px-2 py-1 text-left border-r"
                    style={{ minWidth: 220 }}
                  >
                    Статья / Период
                  </th>
                  <th colSpan={12} className="text-center border-r">
                    Y1 (M1-M12)
                  </th>
                  <th colSpan={12} className="text-center border-r">
                    Y2 (M13-M24)
                  </th>
                  <th colSpan={12} className="text-center border-r">
                    Y3 (M25-M36)
                  </th>
                  <th colSpan={7} className="text-center">
                    Y4-Y10
                  </th>
                </tr>
                <tr className="bg-muted/50">
                  <th className="sticky left-0 bg-muted/50 border-r" />
                  {periods.map((pn) => (
                    <th
                      key={pn}
                      className="px-1 py-0.5 text-center border-r font-mono"
                      style={{ minWidth: 70 }}
                    >
                      {periodLabel(pn)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr className="bg-blue-50 font-semibold">
                  <td
                    className="sticky left-0 bg-blue-50 px-2 py-1 border-r cursor-pointer"
                    onClick={() =>
                      setCollapsed((c) => ({ ...c, capex: !c.capex }))
                    }
                  >
                    {collapsed.capex ? "▶" : "▼"} CAPEX итог
                  </td>
                  {periods.map((pn) => {
                    const it = items.find((x) => x.period_number === pn);
                    return (
                      <td key={pn} className="border-r text-center">
                        {it && it.capex_items.length === 0 ? (
                          <Input
                            type="number"
                            min="0"
                            step="1"
                            value={it.capex}
                            onChange={(e) =>
                              updatePeriodTotal(pn, "capex", e.target.value)
                            }
                            disabled={saving}
                            className="h-7 text-right text-xs"
                          />
                        ) : (
                          <span className="text-muted-foreground">
                            {Number(it?.capex || 0).toLocaleString("ru-RU")}
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>

                {!collapsed.capex &&
                  capexArticleKeys.map((k) => (
                    <ArticleRow
                      key={`capex-${k.category}-${k.name}`}
                      items={items}
                      kind="capex"
                      category={k.category}
                      name={k.name}
                      saving={saving}
                      onUpdate={(pn, val) =>
                        updateArticleAmount(pn, "capex", k.category, k.name, val)
                      }
                      onRemove={() =>
                        removeArticle("capex", k.category, k.name)
                      }
                    />
                  ))}
                {!collapsed.capex && (
                  <AddArticleRow
                    kind="capex"
                    onAdd={(cat, name) => addArticle("capex", cat, name)}
                    disabled={saving}
                  />
                )}

                <tr className="bg-green-50 font-semibold">
                  <td
                    className="sticky left-0 bg-green-50 px-2 py-1 border-r cursor-pointer"
                    onClick={() =>
                      setCollapsed((c) => ({ ...c, opex: !c.opex }))
                    }
                  >
                    {collapsed.opex ? "▶" : "▼"} OPEX итог
                  </td>
                  {periods.map((pn) => {
                    const it = items.find((x) => x.period_number === pn);
                    return (
                      <td key={pn} className="border-r text-center">
                        {it && it.opex_items.length === 0 ? (
                          <Input
                            type="number"
                            min="0"
                            step="1"
                            value={it.opex}
                            onChange={(e) =>
                              updatePeriodTotal(pn, "opex", e.target.value)
                            }
                            disabled={saving}
                            className="h-7 text-right text-xs"
                          />
                        ) : (
                          <span className="text-muted-foreground">
                            {Number(it?.opex || 0).toLocaleString("ru-RU")}
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>

                {!collapsed.opex &&
                  opexArticleKeys.map((k) => (
                    <ArticleRow
                      key={`opex-${k.category}-${k.name}`}
                      items={items}
                      kind="opex"
                      category={k.category}
                      name={k.name}
                      saving={saving}
                      onUpdate={(pn, val) =>
                        updateArticleAmount(pn, "opex", k.category, k.name, val)
                      }
                      onRemove={() =>
                        removeArticle("opex", k.category, k.name)
                      }
                    />
                  ))}
                {!collapsed.opex && (
                  <AddArticleRow
                    kind="opex"
                    onAdd={(cat, name) => addArticle("opex", cat, name)}
                    disabled={saving}
                  />
                )}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ============================================================
// Helpers
// ============================================================

function collectArticleKeys(
  items: FinancialPlanItem[] | null,
  kind: ItemKind,
): Array<{ category: string; name: string }> {
  if (items === null) return [];
  const seen = new Map<string, { category: string; name: string }>();
  for (const p of items) {
    const list = kind === "capex" ? p.capex_items : p.opex_items;
    for (const it of list) {
      const key = `${it.category}|${it.name}`;
      if (!seen.has(key)) {
        seen.set(key, { category: it.category, name: it.name });
      }
    }
  }
  return Array.from(seen.values());
}

// --- Sub-components ---

interface ArticleRowProps {
  items: FinancialPlanItem[];
  kind: ItemKind;
  category: string;
  name: string;
  saving: boolean;
  onUpdate: (periodNumber: number, value: string) => void;
  onRemove: () => void;
}

function ArticleRow({
  items,
  kind,
  category,
  name,
  saving,
  onUpdate,
  onRemove,
}: ArticleRowProps) {
  const labels =
    kind === "capex" ? CAPEX_CATEGORY_LABELS : OPEX_CATEGORY_LABELS;
  const catLabel = (labels as Record<string, string>)[category] ?? category;
  return (
    <tr>
      <td className="sticky left-0 bg-background px-2 py-1 border-r">
        <div className="flex items-center justify-between gap-2">
          <span>
            <span className="text-muted-foreground">{catLabel}</span> · {name}
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={onRemove}
            disabled={saving}
            className="h-5 px-1 text-destructive"
            title="Удалить статью"
          >
            ×
          </Button>
        </div>
      </td>
      {items.map((p) => {
        const article = (
          kind === "capex" ? p.capex_items : p.opex_items
        ).find((it) => it.category === category && it.name === name);
        return (
          <td key={p.period_number} className="border-r">
            <Input
              type="number"
              min="0"
              step="1"
              value={article?.amount ?? "0"}
              onChange={(e) => onUpdate(p.period_number, e.target.value)}
              disabled={saving}
              className="h-7 text-right text-xs"
            />
          </td>
        );
      })}
    </tr>
  );
}

interface AddArticleRowProps {
  kind: ItemKind;
  onAdd: (category: string, name: string) => void;
  disabled: boolean;
}

function AddArticleRow({ kind, onAdd, disabled }: AddArticleRowProps) {
  const [category, setCategory] = useState<string>("other");
  const [name, setName] = useState<string>("");
  const categories = kind === "capex" ? CAPEX_CATEGORIES : OPEX_CATEGORIES;
  const labels =
    kind === "capex" ? CAPEX_CATEGORY_LABELS : OPEX_CATEGORY_LABELS;

  function handle() {
    if (name.trim() === "") return;
    onAdd(category, name.trim());
    setName("");
  }

  return (
    <tr className="bg-muted/20">
      <td className="sticky left-0 bg-muted/20 px-2 py-1 border-r" colSpan={44}>
        <div className="flex items-center gap-2">
          <Select
            value={category}
            onValueChange={(v) => v && setCategory(v)}
            items={labels as Record<string, string>}
          >
            <SelectTrigger className="h-7 w-[180px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {categories.map((c) => (
                <SelectItem key={c} value={c} className="text-xs">
                  {(labels as Record<string, string>)[c] ?? c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            placeholder={`Название статьи ${kind === "capex" ? "CAPEX" : "OPEX"}`}
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={disabled}
            className="h-7 text-xs max-w-xs"
          />
          <Button
            variant="ghost"
            size="sm"
            onClick={handle}
            disabled={disabled || name.trim() === ""}
            className="h-7 text-xs text-primary"
          >
            + Добавить статью
          </Button>
        </div>
      </td>
    </tr>
  );
}
