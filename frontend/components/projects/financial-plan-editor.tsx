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

import type { FinancialPlanItem } from "@/types/api";

interface FinancialPlanEditorProps {
  projectId: number;
}

/**
 * Редактор CAPEX/OPEX по годам проекта.
 *
 * UI: таблица из 10 строк Y1..Y10 × колонки (Год, CAPEX ₽, OPEX ₽).
 * Inline edit через controlled Input. Кнопка "Сохранить" делает PUT
 * полной замены плана (backend удалит старое + вставит новое).
 *
 * Backend маппит year → period_id первого периода model_year автоматически.
 * Pipeline применяет capex/opex в `run_project_pipeline` через
 * `project_capex` / `project_opex` tuples.
 *
 * После сохранения — нужно нажать "Пересчитать" в табе "Результаты"
 * чтобы увидеть обновлённые KPI.
 */
export function FinancialPlanEditor({ projectId }: FinancialPlanEditorProps) {
  const [items, setItems] = useState<FinancialPlanItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<Date | null>(null);

  // Загрузка при mount
  useEffect(() => {
    let cancelled = false;
    getFinancialPlan(projectId)
      .then((data) => {
        if (!cancelled) setItems(data);
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

  function updateItem(year: number, field: "capex" | "opex", value: string) {
    setItems((prev) => {
      if (prev === null) return prev;
      return prev.map((item) =>
        item.year === year ? { ...item, [field]: value } : item,
      );
    });
  }

  async function handleSave() {
    if (items === null) return;
    setSaving(true);
    setError(null);
    try {
      const saved = await putFinancialPlan(projectId, { items });
      setItems(saved);
      setSavedAt(new Date());
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка сохранения",
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
              маркетинг и т.п.) на уровне всего проекта. Применяются в
              pipeline после SKU/каналов. После сохранения нажмите
              «Пересчитать» в табе «Результаты» чтобы увидеть обновлённые KPI.
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
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item) => (
                <TableRow key={item.year}>
                  <TableCell className="font-medium">Y{item.year}</TableCell>
                  <TableCell>
                    <Input
                      type="number"
                      step="1"
                      min="0"
                      value={item.capex}
                      onChange={(e) =>
                        updateItem(item.year, "capex", e.target.value)
                      }
                      disabled={saving}
                      className="max-w-xs"
                    />
                  </TableCell>
                  <TableCell>
                    <Input
                      type="number"
                      step="1"
                      min="0"
                      value={item.opex}
                      onChange={(e) =>
                        updateItem(item.year, "opex", e.target.value)
                      }
                      disabled={saving}
                      className="max-w-xs"
                    />
                  </TableCell>
                </TableRow>
              ))}
              <TableRow className="border-t-2 font-semibold">
                <TableCell>Итого</TableCell>
                <TableCell className="pl-3">
                  {formatMoney(String(totalCapex))}
                </TableCell>
                <TableCell className="pl-3">
                  {formatMoney(String(totalOpex))}
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
