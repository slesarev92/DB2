"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  distributeYear,
  fillRange,
  periodLabel,
} from "@/lib/financial-plan-utils";

/** Описывает, к какой строке (статье) применить bulk-fill. */
export interface BulkFillTarget {
  /** Ключ строки: "capex.total" / "opex.total" / "${kind}.${category}|${name}". */
  rowKey: string;
  /** Отображаемое имя для пользователя. */
  label: string;
}

export interface PeriodBulkFillProps {
  rows: BulkFillTarget[];
  /** Колбэк применения изменений: список (period_number, value) к выбранной строке. */
  onApply: (rowKey: string, updates: Array<[number, string]>) => void;
  disabled?: boolean;
}

type Mode = "distribute_year" | "fill_range";

const MODE_ITEMS: Record<Mode, string> = {
  distribute_year: "Распределить год (Y1-Y3)",
  fill_range: "Залить диапазон",
};

const YEAR_ITEMS: Record<string, string> = {
  "1": "Y1 (M1..M12)",
  "2": "Y2 (M13..M24)",
  "3": "Y3 (M25..M36)",
};

const PERIOD_ITEMS: Record<string, string> = Array.from(
  { length: 43 },
  (_, i) => i + 1,
).reduce<Record<string, string>>((acc, pn) => {
  acc[String(pn)] = periodLabel(pn);
  return acc;
}, {});

export function PeriodBulkFill({
  rows,
  onApply,
  disabled,
}: PeriodBulkFillProps) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<Mode>("distribute_year");
  const [rowKey, setRowKey] = useState<string>(rows[0]?.rowKey ?? "");
  const [year, setYear] = useState<number>(1);
  const [total, setTotal] = useState<string>("0");
  const [rangeFrom, setRangeFrom] = useState<number>(1);
  const [rangeTo, setRangeTo] = useState<number>(12);
  const [value, setValue] = useState<string>("0");

  const rowItems = rows.reduce<Record<string, string>>((acc, r) => {
    acc[r.rowKey] = r.label;
    return acc;
  }, {});

  function handleApply() {
    if (rowKey === "") return;
    if (mode === "distribute_year") {
      const updates = distributeYear(year, Number(total) || 0);
      onApply(rowKey, updates);
    } else {
      const updates = fillRange(rangeFrom, rangeTo, value);
      onApply(rowKey, updates);
    }
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger>
        <Button variant="outline" size="sm" disabled={disabled}>
          Bulk-fill
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Массовое заполнение</DialogTitle>
          <DialogDescription>
            Распределить сумму на год или залить значение на диапазон периодов.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="bulk-mode">Режим</Label>
            <Select
              value={mode}
              onValueChange={(v) => v && setMode(v as Mode)}
              items={MODE_ITEMS}
            >
              <SelectTrigger id="bulk-mode" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="distribute_year">
                  {MODE_ITEMS.distribute_year}
                </SelectItem>
                <SelectItem value="fill_range">
                  {MODE_ITEMS.fill_range}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="bulk-row">Строка</Label>
            <Select
              value={rowKey}
              onValueChange={(v) => v && setRowKey(v)}
              items={rowItems}
            >
              <SelectTrigger id="bulk-row" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {rows.map((r) => (
                  <SelectItem key={r.rowKey} value={r.rowKey}>
                    {r.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {mode === "distribute_year" && (
            <>
              <div className="space-y-2">
                <Label htmlFor="bulk-year">Год</Label>
                <Select
                  value={String(year)}
                  onValueChange={(v) => v && setYear(Number(v))}
                  items={YEAR_ITEMS}
                >
                  <SelectTrigger id="bulk-year" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="1">{YEAR_ITEMS["1"]}</SelectItem>
                    <SelectItem value="2">{YEAR_ITEMS["2"]}</SelectItem>
                    <SelectItem value="3">{YEAR_ITEMS["3"]}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="bulk-total">Сумма за год, ₽</Label>
                <Input
                  id="bulk-total"
                  type="number"
                  min="0"
                  step="1"
                  value={total}
                  onChange={(e) => setTotal(e.target.value)}
                />
              </div>
            </>
          )}

          {mode === "fill_range" && (
            <>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-2">
                  <Label htmlFor="bulk-from">От (период)</Label>
                  <Select
                    value={String(rangeFrom)}
                    onValueChange={(v) => v && setRangeFrom(Number(v))}
                    items={PERIOD_ITEMS}
                  >
                    <SelectTrigger id="bulk-from" className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Array.from({ length: 43 }, (_, i) => i + 1).map((pn) => (
                        <SelectItem key={pn} value={String(pn)}>
                          {periodLabel(pn)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="bulk-to">До (период)</Label>
                  <Select
                    value={String(rangeTo)}
                    onValueChange={(v) => v && setRangeTo(Number(v))}
                    items={PERIOD_ITEMS}
                  >
                    <SelectTrigger id="bulk-to" className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Array.from({ length: 43 }, (_, i) => i + 1).map((pn) => (
                        <SelectItem key={pn} value={String(pn)}>
                          {periodLabel(pn)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="bulk-value">Значение в каждый период, ₽</Label>
                <Input
                  id="bulk-value"
                  type="number"
                  min="0"
                  step="1"
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                />
              </div>
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => setOpen(false)}>
            Отмена
          </Button>
          <Button onClick={handleApply}>Применить</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
