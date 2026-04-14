"use client";

import { useEffect, useRef, useState } from "react";

import { PeriodsGrid } from "@/components/projects/periods-grid";
import { SkuPanel } from "@/components/projects/sku-panel";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  type ActualImportResult,
  getActualTemplateUrl,
  uploadActualData,
} from "@/lib/actual-import";
import { ApiError } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";
import { listProjectSkuChannels } from "@/lib/channels";
import { listProjectScenarios } from "@/lib/scenarios";

import { SCENARIO_LABELS } from "@/types/api";
import type {
  ProjectSKUChannelRead,
  ScenarioRead,
} from "@/types/api";

interface PeriodsTabProps {
  projectId: number;
}

type PeriodFilter = "monthly" | "yearly" | "all";

// SCENARIO_LABELS импортируется из types/api.ts — единый русский map (L-01).

/**
 * Таб "Периоды" в карточке проекта.
 *
 * Layout: SkuPanel слева (1/3) + правая колонка с селекторами Channel/
 * Scenario/PeriodFilter + PeriodsGrid (2/3). Каждая смена селектора —
 * перезагружает PeriodsGrid (через изменение pskChannelId/scenarioId).
 *
 * Channels и Scenarios грузятся динамически когда выбран PSK.
 */
export function PeriodsTab({ projectId }: PeriodsTabProps) {
  const [selectedPskId, setSelectedPskId] = useState<number | null>(null);
  const [channels, setChannels] = useState<ProjectSKUChannelRead[]>([]);
  const [selectedPscId, setSelectedPscId] = useState<number | null>(null);
  const [scenarios, setScenarios] = useState<ScenarioRead[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState<number | null>(
    null,
  );
  const [periodFilter, setPeriodFilter] = useState<PeriodFilter>("monthly");
  const [error, setError] = useState<string | null>(null);

  // Actual import state (B-02)
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ActualImportResult | null>(
    null,
  );

  // Загружаем сценарии проекта (один раз)
  useEffect(() => {
    let cancelled = false;
    listProjectScenarios(projectId)
      .then((data) => {
        if (cancelled) return;
        setScenarios(data);
        // Авто-выбираем base
        const base = data.find((s) => s.type === "base");
        if (base) setSelectedScenarioId(base.id);
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

  // Загружаем каналы выбранного PSK
  useEffect(() => {
    if (selectedPskId === null) {
      setChannels([]);
      setSelectedPscId(null);
      return;
    }
    let cancelled = false;
    listProjectSkuChannels(selectedPskId)
      .then((data) => {
        if (cancelled) return;
        setChannels(data);
        if (data.length > 0) {
          setSelectedPscId(data[0].id);
        } else {
          setSelectedPscId(null);
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
  }, [selectedPskId]);

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || selectedScenarioId === null) return;
    setImporting(true);
    setError(null);
    setImportResult(null);
    try {
      const result = await uploadActualData(
        projectId,
        selectedScenarioId,
        file,
      );
      setImportResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка импорта");
    } finally {
      setImporting(false);
      // Reset file input so same file can be re-selected
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleDownloadTemplate() {
    const token = getAccessToken();
    const resp = await fetch(getActualTemplateUrl(projectId), {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!resp.ok) {
      setError("Не удалось скачать шаблон");
      return;
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `actual_template_project_${projectId}.xlsx`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
      <div className="md:col-span-1">
        <SkuPanel
          projectId={projectId}
          selectedPskId={selectedPskId}
          onSelectPsk={setSelectedPskId}
        />
      </div>
      <div className="md:col-span-2 space-y-4">
        {selectedPskId === null ? (
          <Card>
            <CardContent className="pt-6 text-sm text-muted-foreground">
              Выберите SKU слева, чтобы увидеть таблицу периодов.
            </CardContent>
          </Card>
        ) : channels.length === 0 ? (
          <Card>
            <CardContent className="pt-6 text-sm text-muted-foreground">
              У этого SKU нет привязанных каналов. Добавьте канал в табе
              «Каналы».
            </CardContent>
          </Card>
        ) : (
          <>
            <Card>
              <CardContent className="grid grid-cols-1 gap-4 pt-6 sm:grid-cols-3">
                <div className="space-y-2">
                  <Label htmlFor="psc-select">Канал</Label>
                  <Select
                    value={selectedPscId === null ? "" : String(selectedPscId)}
                    onValueChange={(v) => setSelectedPscId(Number(v))}
                  >
                    <SelectTrigger id="psc-select">
                      <SelectValue placeholder="Канал" />
                    </SelectTrigger>
                    <SelectContent>
                      {channels.map((psc) => (
                        <SelectItem key={psc.id} value={String(psc.id)}>
                          {psc.channel.code} — {psc.channel.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="scenario-select">Сценарий</Label>
                  <Select
                    value={
                      selectedScenarioId === null
                        ? ""
                        : String(selectedScenarioId)
                    }
                    onValueChange={(v) => setSelectedScenarioId(Number(v))}
                  >
                    <SelectTrigger id="scenario-select">
                      <SelectValue placeholder="Сценарий" />
                    </SelectTrigger>
                    <SelectContent>
                      {scenarios.map((s) => (
                        <SelectItem key={s.id} value={String(s.id)}>
                          {SCENARIO_LABELS[s.type] ?? s.type}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="period-filter">Период</Label>
                  <Select
                    value={periodFilter}
                    onValueChange={(v) => setPeriodFilter(v as PeriodFilter)}
                  >
                    <SelectTrigger id="period-filter">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="monthly">Месяцы (M1-M36)</SelectItem>
                      <SelectItem value="yearly">Годы (Y4-Y10)</SelectItem>
                      <SelectItem value="all">Все 43</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </CardContent>
            </Card>

            {/* B-02: Import actual data */}
            <Card>
              <CardContent className="flex items-center gap-3 pt-4 pb-4">
                <span className="text-sm font-medium">Импорт факта:</span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleDownloadTemplate}
                >
                  Скачать шаблон
                </Button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".xlsx"
                  className="hidden"
                  onChange={handleFileUpload}
                />
                <Button
                  variant="default"
                  size="sm"
                  disabled={importing || selectedScenarioId === null}
                  onClick={() => fileInputRef.current?.click()}
                >
                  {importing ? "Импорт..." : "Загрузить .xlsx"}
                </Button>
                {importResult !== null && (
                  <span className="text-xs text-muted-foreground">
                    Импортировано: {importResult.imported}, пропущено:{" "}
                    {importResult.skipped}
                    {importResult.errors.length > 0 && (
                      <span className="text-destructive">
                        {" "}
                        ({importResult.errors.length} ошиб.)
                      </span>
                    )}
                  </span>
                )}
              </CardContent>
            </Card>

            {importResult !== null && importResult.errors.length > 0 && (
              <Card>
                <CardContent className="pt-4 pb-4">
                  <p className="mb-2 text-sm font-medium text-destructive">
                    Ошибки импорта:
                  </p>
                  <ul className="list-disc pl-5 text-xs text-muted-foreground space-y-0.5">
                    {importResult.errors.slice(0, 20).map((err, i) => (
                      <li key={i}>{err}</li>
                    ))}
                    {importResult.errors.length > 20 && (
                      <li>
                        ... и ещё {importResult.errors.length - 20} ошибок
                      </li>
                    )}
                  </ul>
                </CardContent>
              </Card>
            )}

            {error !== null && (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            )}

            {selectedPscId !== null && selectedScenarioId !== null && (
              <PeriodsGrid
                key={`${selectedPscId}-${selectedScenarioId}`}
                projectId={projectId}
                pskChannelId={selectedPscId}
                scenarioId={selectedScenarioId}
                periodFilter={periodFilter}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
