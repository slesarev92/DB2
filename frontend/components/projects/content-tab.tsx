"use client";

import { useCallback, useEffect, useState } from "react";

import { GanttChart } from "@/components/projects/gantt-chart";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ContentFieldAI } from "@/components/projects/content-field-ai";
import { MarketingResearchSection } from "@/components/projects/marketing-research-section";
import { ApiError } from "@/lib/api";
import { getProject, updateProject } from "@/lib/projects";

import type {
  Approver,
  FunctionDepartment,
  FunctionReadinessEntry,
  FunctionReadinessMap,
  FunctionReadinessStatus,
  GateStage,
  NielsenBenchmark,
  ProjectRead,
  ProjectUpdate,
  RiskItem,
  RoadmapTask,
  SupplierQuote,
  ValidationTests,
} from "@/types/api";
import { FUNCTION_DEPARTMENTS } from "@/types/api";

interface ContentTabProps {
  projectId: number;
  onProjectUpdate?: (updated: Record<string, unknown>) => void;
}

const GATE_OPTIONS: GateStage[] = ["G0", "G1", "G2", "G3", "G4", "G5"];
const FUNCTION_STATUS_OPTIONS: FunctionReadinessStatus[] = [
  "green",
  "yellow",
  "red",
];
const FUNCTION_STATUS_LABELS: Record<FunctionReadinessStatus, string> = {
  green: "Зелёный",
  yellow: "Жёлтый",
  red: "Красный",
};

const VALIDATION_SUBTESTS: Array<{
  key: keyof ValidationTests;
  label: string;
}> = [
  { key: "concept_test", label: "Concept test" },
  { key: "naming", label: "Naming" },
  { key: "design", label: "Design" },
  { key: "product", label: "Product" },
  { key: "price", label: "Price" },
];

/** Все scalar content-поля проекта, которые редактируются на этом табе. */
const SCALAR_FIELDS = [
  "description",
  "gate_stage",
  "passport_date",
  "project_owner",
  "project_goal",
  "innovation_type",
  "geography",
  "production_type",
  "growth_opportunity",
  "concept_text",
  "rationale",
  "idea_short",
  "target_audience",
  "replacement_target",
  "technology",
  "rnd_progress",
  "executive_summary",
] as const;

type ScalarField = (typeof SCALAR_FIELDS)[number];

type ScalarState = Record<ScalarField, string>;

function projectToScalarState(project: ProjectRead): ScalarState {
  const state = {} as ScalarState;
  for (const field of SCALAR_FIELDS) {
    const val = project[field] as string | null | undefined;
    state[field] = val ?? "";
  }
  return state;
}

function emptyFunctionReadiness(): FunctionReadinessMap {
  const map: FunctionReadinessMap = {};
  for (const dept of FUNCTION_DEPARTMENTS) {
    map[dept] = { status: "yellow", notes: "" };
  }
  return map;
}

function mergeFunctionReadiness(
  existing: FunctionReadinessMap | null | undefined,
): FunctionReadinessMap {
  const base = emptyFunctionReadiness();
  if (existing) {
    for (const dept of FUNCTION_DEPARTMENTS) {
      const entry = existing[dept];
      if (entry) base[dept] = { ...base[dept]!, ...entry };
    }
  }
  return base;
}

/** AI-генерируемые поля (Phase 7.6). */
const AI_FIELDS = new Set([
  "project_goal", "target_audience", "concept_text", "rationale",
  "growth_opportunity", "idea_short", "technology", "rnd_progress",
  "replacement_target", "description", "innovation_type",
  "geography", "production_type",
]);

/** Label с кнопкой AI — вынесен из ContentTab чтобы избежать remount при parent re-render. */
function FieldLabel({
  field,
  projectId,
  onApply,
  children,
}: {
  field: ScalarField;
  projectId: number;
  onApply: (field: ScalarField, text: string) => void;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center">
      <Label htmlFor={field}>{children}</Label>
      {AI_FIELDS.has(field) && (
        <ContentFieldAI
          projectId={projectId}
          field={field}
          onApply={(text) => onApply(field, text)}
        />
      )}
    </div>
  );
}

export function ContentTab({ projectId, onProjectUpdate }: ContentTabProps) {
  const [project, setProject] = useState<ProjectRead | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Controlled state для scalar-полей (auto-save on blur)
  const [scalars, setScalars] = useState<ScalarState | null>(null);

  // JSONB state (явный Save button)
  const [risks, setRisks] = useState<RiskItem[]>([]);
  const [validationTests, setValidationTests] = useState<ValidationTests>({});
  const [functionReadiness, setFunctionReadiness] = useState<FunctionReadinessMap>(
    emptyFunctionReadiness(),
  );
  const [roadmapTasks, setRoadmapTasks] = useState<RoadmapTask[]>([]);
  const [approvers, setApprovers] = useState<Approver[]>([]);
  const [nielsenBenchmarks, setNielsenBenchmarks] = useState<NielsenBenchmark[]>([]);
  const [supplierQuotes, setSupplierQuotes] = useState<SupplierQuote[]>([]);

  // Статус сохранения (для scalars + для JSONB секций)
  const [savingField, setSavingField] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<Date | null>(null);

  // UX-13: collapsible sections (collapsed by default: none)
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
  function toggleSection(n: number) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(n)) next.delete(n); else next.add(n);
      return next;
    });
  }

  // Initial load
  useEffect(() => {
    let cancelled = false;
    getProject(projectId)
      .then((data) => {
        if (cancelled) return;
        setProject(data);
        setScalars(projectToScalarState(data));
        setRisks(data.risks ?? []);
        setValidationTests(data.validation_tests ?? {});
        setFunctionReadiness(mergeFunctionReadiness(data.function_readiness));
        setRoadmapTasks(data.roadmap_tasks ?? []);
        setApprovers(data.approvers ?? []);
        setNielsenBenchmarks(data.nielsen_benchmarks ?? []);
        setSupplierQuotes(data.supplier_quotes ?? []);
      })
      .catch((err) => {
        if (cancelled) return;
        setLoadError(
          err instanceof ApiError
            ? err.detail ?? err.message
            : "Ошибка загрузки проекта",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  // Общий saver для PATCH. field — имя поля для статуса.
  const patchProject = useCallback(
    async (field: string, body: ProjectUpdate): Promise<boolean> => {
      setSavingField(field);
      setSaveError(null);
      try {
        const updated = await updateProject(projectId, body);
        setProject(updated);
        setSavedAt(new Date());
        onProjectUpdate?.(body as unknown as Record<string, unknown>);
        return true;
      } catch (err) {
        setSaveError(
          err instanceof ApiError
            ? err.detail ?? err.message
            : "Ошибка сохранения",
        );
        return false;
      } finally {
        setSavingField(null);
      }
    },
    [projectId],
  );

  /**
   * Auto-save scalar поля на blur. Отправляется только если значение
   * отличается от сохранённого в project (чтобы не городить PATCH на
   * каждом фокусе без изменений).
   */
  async function flushScalar(field: ScalarField) {
    if (project === null || scalars === null) return;
    const current = scalars[field];
    const prev = (project[field] as string | null) ?? "";
    if (current === prev) return;

    const value: string | null = current === "" ? null : current;
    await patchProject(field, { [field]: value } as ProjectUpdate);
  }

  function setScalarField(field: ScalarField, value: string) {
    setScalars((prev) => (prev ? { ...prev, [field]: value } : prev));
  }



  /** Callback для AI apply — стабильная ссылка через useCallback. */
  const handleAIApply = useCallback(
    async (field: ScalarField, text: string) => {
      setScalarField(field, text);
      await patchProject(field, { [field]: text } as ProjectUpdate);
    },
    [patchProject],
  );

  if (loadError !== null) {
    return (
      <Card className="border-destructive">
        <CardContent className="pt-6 text-sm text-destructive">
          {loadError}
        </CardContent>
      </Card>
    );
  }

  if (project === null || scalars === null) {
    return <p className="text-sm text-muted-foreground">Загрузка...</p>;
  }

  // ==========================================================
  // Хелперы для JSONB секций
  // ==========================================================

  async function saveRisks() {
    await patchProject("risks", { risks });
  }
  async function saveValidationTests() {
    await patchProject("validation_tests", { validation_tests: validationTests });
  }
  async function saveFunctionReadiness() {
    await patchProject("function_readiness", { function_readiness: functionReadiness });
  }
  async function saveRoadmap() {
    await patchProject("roadmap_tasks", { roadmap_tasks: roadmapTasks });
  }
  async function saveApprovers() {
    await patchProject("approvers", { approvers });
  }
  async function saveNielsenBenchmarks() {
    await patchProject("nielsen_benchmarks", { nielsen_benchmarks: nielsenBenchmarks });
  }
  async function saveSupplierQuotes() {
    await patchProject("supplier_quotes", { supplier_quotes: supplierQuotes });
  }

  return (
    <div className="space-y-6">
      {/* Status bar */}
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        {savingField && <span>Сохранение: {savingField}...</span>}
        {!savingField && savedAt && (
          <span className="text-emerald-600">
            ✓ Сохранено в {savedAt.toLocaleTimeString("ru-RU")}
          </span>
        )}
        {saveError && <span className="text-destructive">Ошибка: {saveError}</span>}
      </div>

      {/* ====================================================== */}
      {/* 1. Общая информация                                    */}
      {/* ====================================================== */}
      <Card>
        <CardHeader className="cursor-pointer" onClick={() => toggleSection(1)}>
          <CardTitle className="text-base flex items-center justify-between">
            1. Общая информация
            <span className="text-muted-foreground text-sm font-normal">{collapsed.has(1) ? "▸" : "▾"}</span>
          </CardTitle>
          <CardDescription>
            Стадия паспорта, владелец, базовые атрибуты проекта.
          </CardDescription>
        </CardHeader>
        {!collapsed.has(1) && <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-1">
              <Label htmlFor="gate_stage">Gate-стадия</Label>
              <Select
                value={scalars.gate_stage || undefined}
                onValueChange={async (v) => {
                  const value = (v ?? "") as string;
                  setScalarField("gate_stage", value);
                  await patchProject("gate_stage", {
                    gate_stage: (value || null) as GateStage | null,
                  });
                }}
              >
                <SelectTrigger id="gate_stage" className="w-full">
                  <SelectValue placeholder="—" />
                </SelectTrigger>
                <SelectContent>
                  {GATE_OPTIONS.map((g) => (
                    <SelectItem key={g} value={g}>
                      {g}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <Label htmlFor="passport_date">Дата паспорта</Label>
              <Input
                id="passport_date"
                type="date"
                value={scalars.passport_date}
                onChange={(e) => setScalarField("passport_date", e.target.value)}
                onBlur={() => flushScalar("passport_date")}
              />
            </div>

            <div className="space-y-1">
              <Label htmlFor="project_owner">Владелец проекта</Label>
              <Input
                id="project_owner"
                value={scalars.project_owner}
                onChange={(e) => setScalarField("project_owner", e.target.value)}
                onBlur={() => flushScalar("project_owner")}
              />
            </div>
          </div>

          <div className="space-y-1">
            <FieldLabel field="description" projectId={projectId} onApply={handleAIApply}>Описание проекта</FieldLabel>
            <Textarea
              id="description"
              rows={3}
              value={scalars.description}
              onChange={(e) => setScalarField("description", e.target.value)}
              onBlur={() => flushScalar("description")}
            />
          </div>

          <div className="space-y-1">
            <FieldLabel field="project_goal" projectId={projectId} onApply={handleAIApply}>Цель проекта</FieldLabel>
            <Textarea
              id="project_goal"
              rows={2}
              value={scalars.project_goal}
              onChange={(e) => setScalarField("project_goal", e.target.value)}
              onBlur={() => flushScalar("project_goal")}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-1">
              <FieldLabel field="innovation_type" projectId={projectId} onApply={handleAIApply}>Тип инновации</FieldLabel>
              <Input
                id="innovation_type"
                value={scalars.innovation_type}
                onChange={(e) => setScalarField("innovation_type", e.target.value)}
                onBlur={() => flushScalar("innovation_type")}
              />
            </div>
            <div className="space-y-1">
              <FieldLabel field="geography" projectId={projectId} onApply={handleAIApply}>География</FieldLabel>
              <Input
                id="geography"
                value={scalars.geography}
                onChange={(e) => setScalarField("geography", e.target.value)}
                onBlur={() => flushScalar("geography")}
              />
            </div>
            <div className="space-y-1">
              <FieldLabel field="production_type" projectId={projectId} onApply={handleAIApply}>Тип производства</FieldLabel>
              <Input
                id="production_type"
                value={scalars.production_type}
                onChange={(e) => setScalarField("production_type", e.target.value)}
                onBlur={() => flushScalar("production_type")}
                placeholder="Копакинг / Собственное"
              />
              <p className="text-[11px] text-muted-foreground">
                Копакинг — контрактное производство (тариф за ед.), Собственное — своя площадка (% от цены отгрузки). Влияет на структуру COGS.
              </p>
            </div>
          </div>
        </CardContent>}
      </Card>

      {/* ====================================================== */}
      {/* 2. Концепция продукта                                  */}
      {/* ====================================================== */}
      <Card>
        <CardHeader className="cursor-pointer" onClick={() => toggleSection(2)}>
          <CardTitle className="text-base flex items-center justify-between">
            2. Концепция продукта
            <span className="text-muted-foreground text-sm font-normal">{collapsed.has(2) ? "▸" : "▾"}</span>
          </CardTitle>
          <CardDescription>
            Рост, идея, целевая аудитория, технология.
          </CardDescription>
        </CardHeader>
        {!collapsed.has(2) && <CardContent className="space-y-4">
          <div className="space-y-1">
            <FieldLabel field="growth_opportunity" projectId={projectId} onApply={handleAIApply}>Growth opportunity</FieldLabel>
            <Textarea
              id="growth_opportunity"
              rows={2}
              value={scalars.growth_opportunity}
              onChange={(e) => setScalarField("growth_opportunity", e.target.value)}
              onBlur={() => flushScalar("growth_opportunity")}
            />
          </div>

          <div className="space-y-1">
            <FieldLabel field="concept_text" projectId={projectId} onApply={handleAIApply}>Концепция (полный текст)</FieldLabel>
            <Textarea
              id="concept_text"
              rows={4}
              value={scalars.concept_text}
              onChange={(e) => setScalarField("concept_text", e.target.value)}
              onBlur={() => flushScalar("concept_text")}
            />
          </div>

          <div className="space-y-1">
            <FieldLabel field="rationale" projectId={projectId} onApply={handleAIApply}>Обоснование</FieldLabel>
            <Textarea
              id="rationale"
              rows={3}
              value={scalars.rationale}
              onChange={(e) => setScalarField("rationale", e.target.value)}
              onBlur={() => flushScalar("rationale")}
            />
          </div>

          <div className="space-y-1">
            <FieldLabel field="idea_short" projectId={projectId} onApply={handleAIApply}>Короткая идея</FieldLabel>
            <Input
              id="idea_short"
              value={scalars.idea_short}
              onChange={(e) => setScalarField("idea_short", e.target.value)}
              onBlur={() => flushScalar("idea_short")}
            />
          </div>

          <div className="space-y-1">
            <FieldLabel field="target_audience" projectId={projectId} onApply={handleAIApply}>Целевая аудитория</FieldLabel>
            <Textarea
              id="target_audience"
              rows={2}
              value={scalars.target_audience}
              onChange={(e) => setScalarField("target_audience", e.target.value)}
              onBlur={() => flushScalar("target_audience")}
            />
          </div>

          <div className="space-y-1">
            <FieldLabel field="replacement_target" projectId={projectId} onApply={handleAIApply}>Кого замещаем</FieldLabel>
            <Input
              id="replacement_target"
              value={scalars.replacement_target}
              onChange={(e) => setScalarField("replacement_target", e.target.value)}
              onBlur={() => flushScalar("replacement_target")}
            />
          </div>

          <div className="space-y-1">
            <FieldLabel field="technology" projectId={projectId} onApply={handleAIApply}>Технология</FieldLabel>
            <Textarea
              id="technology"
              rows={2}
              value={scalars.technology}
              onChange={(e) => setScalarField("technology", e.target.value)}
              onBlur={() => flushScalar("technology")}
            />
          </div>

          <div className="space-y-1">
            <FieldLabel field="rnd_progress" projectId={projectId} onApply={handleAIApply}>Прогресс R&D</FieldLabel>
            <Textarea
              id="rnd_progress"
              rows={2}
              value={scalars.rnd_progress}
              onChange={(e) => setScalarField("rnd_progress", e.target.value)}
              onBlur={() => flushScalar("rnd_progress")}
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="executive_summary">
              Executive summary
              <span className="ml-2 text-xs text-muted-foreground">
                (AI-generated в Phase 7.6, можно править вручную)
              </span>
            </Label>
            <Textarea
              id="executive_summary"
              rows={4}
              value={scalars.executive_summary}
              onChange={(e) => setScalarField("executive_summary", e.target.value)}
              onBlur={() => flushScalar("executive_summary")}
            />
          </div>
        </CardContent>}
      </Card>

      {/* ====================================================== */}
      {/* 3-4. Валидация + Риски — 2-column on xl+               */}
      {/* ====================================================== */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
      <Card>
        <CardHeader className="cursor-pointer" onClick={() => toggleSection(3)}>
          <CardTitle className="text-base flex items-center justify-between">
            3. Результаты валидации
            <span className="text-muted-foreground text-sm font-normal">{collapsed.has(3) ? "▸" : "▾"}</span>
          </CardTitle>
          <CardDescription>
            5 подтестов: concept test, naming, design, product, price. Score
            0–100, notes — выводы и рекомендации.
          </CardDescription>
        </CardHeader>
        {!collapsed.has(3) && <CardContent className="space-y-4">
          {VALIDATION_SUBTESTS.map(({ key, label }) => {
            const entry = validationTests[key] ?? { score: null, notes: "" };
            return (
              <div key={key} className="grid grid-cols-1 md:grid-cols-4 gap-3">
                <div className="md:col-span-1">
                  <Label>{label}</Label>
                  <Input
                    type="number"
                    min={0}
                    max={100}
                    placeholder="score 0–100"
                    value={entry.score ?? ""}
                    onChange={(e) => {
                      const raw = e.target.value;
                      const score = raw === "" ? null : Number(raw);
                      setValidationTests((prev) => ({
                        ...prev,
                        [key]: { score, notes: entry.notes },
                      }));
                    }}
                  />
                </div>
                <div className="md:col-span-3">
                  <Label>Notes</Label>
                  <Textarea
                    rows={2}
                    placeholder="выводы теста"
                    value={entry.notes}
                    onChange={(e) => {
                      const notes = e.target.value;
                      setValidationTests((prev) => ({
                        ...prev,
                        [key]: { score: entry.score ?? null, notes },
                      }));
                    }}
                  />
                </div>
              </div>
            );
          })}
          <div>
            <Button size="sm" onClick={saveValidationTests}>
              Сохранить валидацию
            </Button>
          </div>
        </CardContent>}
      </Card>

      {/* ====================================================== */}
      {/* 4. Риски (JSONB list)                                  */}
      {/* ====================================================== */}
      <Card>
        <CardHeader className="cursor-pointer" onClick={() => toggleSection(4)}>
          <CardTitle className="text-base flex items-center justify-between">
            4. Риски
            <span className="text-muted-foreground text-sm font-normal">{collapsed.has(4) ? "▸" : "▾"}</span>
          </CardTitle>
          <CardDescription>
            Свободный список ключевых рисков. Порядок имеет значение —
            сверху важнее.
          </CardDescription>
        </CardHeader>
        {!collapsed.has(4) && <CardContent className="space-y-3">
          {risks.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Рисков пока не добавлено.
            </p>
          )}
          {risks.map((risk, idx) => (
            <div key={idx} className="flex gap-2">
              <Input
                value={risk.text}
                onChange={(e) => {
                  const text = e.target.value;
                  setRisks((prev) =>
                    prev.map((r, i) => (i === idx ? { text } : r)),
                  );
                }}
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  setRisks((prev) => prev.filter((_, i) => i !== idx))
                }
              >
                Удалить
              </Button>
            </div>
          ))}
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setRisks((prev) => [...prev, { text: "" }])}
            >
              + Добавить риск
            </Button>
            <Button size="sm" onClick={saveRisks}>
              Сохранить риски
            </Button>
          </div>
        </CardContent>}
      </Card>
      </div>{/* end 2-column grid */}

      {/* ====================================================== */}
      {/* 5. Готовность функций (JSONB map — фиксированные 8)    */}
      {/* ====================================================== */}
      <Card>
        <CardHeader className="cursor-pointer" onClick={() => toggleSection(5)}>
          <CardTitle className="text-base flex items-center justify-between">
            5. Готовность функций
            <span className="text-muted-foreground text-sm font-normal">{collapsed.has(5) ? "▸" : "▾"}</span>
          </CardTitle>
          <CardDescription>
            8 фиксированных департаментов × светофор (green/yellow/red) +
            заметки.
          </CardDescription>
        </CardHeader>
        {!collapsed.has(5) && <CardContent className="space-y-3">
          {FUNCTION_DEPARTMENTS.map((dept) => {
            const entry: FunctionReadinessEntry =
              functionReadiness[dept] ?? { status: "yellow", notes: "" };
            return (
              <div
                key={dept}
                className="grid grid-cols-1 md:grid-cols-[140px_140px_1fr] gap-3 items-start"
              >
                <div className="text-sm font-medium pt-2">{dept}</div>
                <Select
                  value={entry.status}
                  onValueChange={(v) => {
                    const status = v as FunctionReadinessStatus;
                    setFunctionReadiness((prev) => ({
                      ...prev,
                      [dept]: { status, notes: entry.notes },
                    }));
                  }}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {FUNCTION_STATUS_OPTIONS.map((s) => (
                      <SelectItem key={s} value={s}>
                        {FUNCTION_STATUS_LABELS[s]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Textarea
                  rows={1}
                  placeholder="комментарий"
                  value={entry.notes}
                  onChange={(e) => {
                    const notes = e.target.value;
                    setFunctionReadiness((prev) => ({
                      ...prev,
                      [dept]: { status: entry.status, notes },
                    }));
                  }}
                />
              </div>
            );
          })}
          <div>
            <Button size="sm" onClick={saveFunctionReadiness}>
              Сохранить готовность
            </Button>
          </div>
        </CardContent>}
      </Card>

      {/* ====================================================== */}
      {/* 6. Дорожная карта (JSONB list)                         */}
      {/* ====================================================== */}
      <Card>
        <CardHeader className="cursor-pointer" onClick={() => toggleSection(6)}>
          <CardTitle className="text-base flex items-center justify-between">
            6. Дорожная карта
            <span className="text-muted-foreground text-sm font-normal">{collapsed.has(6) ? "▸" : "▾"}</span>
          </CardTitle>
          <CardDescription>
            Ключевые задачи проекта с датами, ответственными и статусом.
          </CardDescription>
        </CardHeader>
        {!collapsed.has(6) && <CardContent className="space-y-3">
          {roadmapTasks.length === 0 && (
            <p className="text-sm text-muted-foreground">Задач пока нет.</p>
          )}
          {roadmapTasks.map((task, idx) => (
            <div
              key={idx}
              className="rounded-md border border-border p-3 space-y-2"
            >
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                <div>
                  <Label>Задача</Label>
                  <Input
                    value={task.name}
                    onChange={(e) => {
                      const name = e.target.value;
                      setRoadmapTasks((prev) =>
                        prev.map((t, i) => (i === idx ? { ...t, name } : t)),
                      );
                    }}
                  />
                </div>
                <div>
                  <Label>Ответственный</Label>
                  <Input
                    value={task.owner ?? ""}
                    onChange={(e) => {
                      const owner = e.target.value;
                      setRoadmapTasks((prev) =>
                        prev.map((t, i) => (i === idx ? { ...t, owner } : t)),
                      );
                    }}
                  />
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                <div>
                  <Label>Начало</Label>
                  <Input
                    type="date"
                    value={task.start_date ?? ""}
                    onChange={(e) => {
                      const start_date = e.target.value;
                      setRoadmapTasks((prev) =>
                        prev.map((t, i) => (i === idx ? { ...t, start_date } : t)),
                      );
                    }}
                  />
                </div>
                <div>
                  <Label>Конец</Label>
                  <Input
                    type="date"
                    value={task.end_date ?? ""}
                    onChange={(e) => {
                      const end_date = e.target.value;
                      setRoadmapTasks((prev) =>
                        prev.map((t, i) => (i === idx ? { ...t, end_date } : t)),
                      );
                    }}
                  />
                </div>
                <div>
                  <Label>Статус</Label>
                  <Input
                    value={task.status ?? ""}
                    placeholder="в работе / готово / ..."
                    onChange={(e) => {
                      const status = e.target.value;
                      setRoadmapTasks((prev) =>
                        prev.map((t, i) => (i === idx ? { ...t, status } : t)),
                      );
                    }}
                  />
                </div>
              </div>
              <div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setRoadmapTasks((prev) => prev.filter((_, i) => i !== idx))
                  }
                >
                  Удалить задачу
                </Button>
              </div>
            </div>
          ))}
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                setRoadmapTasks((prev) => [...prev, { name: "" }])
              }
            >
              + Добавить задачу
            </Button>
            <Button size="sm" onClick={saveRoadmap}>
              Сохранить дорожную карту
            </Button>
          </div>
        </CardContent>}
      </Card>

      {/* B-07: Gantt chart visualization */}
      {roadmapTasks.length > 0 && (
        <GanttChart
          tasks={roadmapTasks}
          projectStartDate={project?.start_date}
        />
      )}

      {/* ====================================================== */}
      {/* 7. Согласующие (JSONB list)                            */}
      {/* ====================================================== */}
      <Card>
        <CardHeader className="cursor-pointer" onClick={() => toggleSection(7)}>
          <CardTitle className="text-base flex items-center justify-between">
            7. Согласующие
            <span className="text-muted-foreground text-sm font-normal">{collapsed.has(7) ? "▸" : "▾"}</span>
          </CardTitle>
          <CardDescription>
            Метрики проекта и те, кто их подписывает (с источниками данных).
          </CardDescription>
        </CardHeader>
        {!collapsed.has(7) && <CardContent className="space-y-3">
          {approvers.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Согласующих пока нет.
            </p>
          )}
          {approvers.map((a, idx) => (
            <div
              key={idx}
              className="grid grid-cols-1 md:grid-cols-[1fr_1fr_1fr_auto] gap-2 items-end"
            >
              <div>
                <Label>Метрика</Label>
                <Input
                  value={a.metric}
                  onChange={(e) => {
                    const metric = e.target.value;
                    setApprovers((prev) =>
                      prev.map((x, i) => (i === idx ? { ...x, metric } : x)),
                    );
                  }}
                />
              </div>
              <div>
                <Label>Согласующий</Label>
                <Input
                  value={a.name}
                  onChange={(e) => {
                    const name = e.target.value;
                    setApprovers((prev) =>
                      prev.map((x, i) => (i === idx ? { ...x, name } : x)),
                    );
                  }}
                />
              </div>
              <div>
                <Label title="Откуда взят согласующий (подразделение, должность)">Источник</Label>
                <Input
                  value={a.source ?? ""}
                  placeholder="Подразделение / должность"
                  onChange={(e) => {
                    const source = e.target.value;
                    setApprovers((prev) =>
                      prev.map((x, i) => (i === idx ? { ...x, source } : x)),
                    );
                  }}
                />
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  setApprovers((prev) => prev.filter((_, i) => i !== idx))
                }
              >
                Удалить
              </Button>
            </div>
          ))}
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                setApprovers((prev) => [
                  ...prev,
                  { metric: "", name: "", source: "" },
                ])
              }
            >
              + Добавить согласующего
            </Button>
            <Button size="sm" onClick={saveApprovers}>
              Сохранить согласующих
            </Button>
          </div>
        </CardContent>}
      </Card>

      {/* ====================================================== */}
      {/* 8. Nielsen бенчмарки (Phase 8.9)                       */}
      {/* ====================================================== */}
      <Card>
        <CardHeader className="cursor-pointer" onClick={() => toggleSection(8)}>
          <CardTitle className="text-base flex items-center justify-between">
            8. Nielsen бенчмарки
            <span className="text-muted-foreground text-sm font-normal">{collapsed.has(8) ? "▸" : "▾"}</span>
          </CardTitle>
          <CardDescription>
            Рыночные данные по каналам/регионам — вселенная, офтейк,
            дистрибуция, цены. Заполняется вручную из отчётов Nielsen.
          </CardDescription>
        </CardHeader>
        {!collapsed.has(8) && <CardContent className="space-y-3">
          {nielsenBenchmarks.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Бенчмарков пока нет.
            </p>
          )}
          {nielsenBenchmarks.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs border-collapse">
                <thead>
                  <tr className="border-b">
                    <th className="px-2 py-1.5 text-left font-medium text-muted-foreground">Канал</th>
                    <th className="px-2 py-1.5 text-right font-medium text-muted-foreground">Universe (точек)</th>
                    <th className="px-2 py-1.5 text-right font-medium text-muted-foreground">Off-take</th>
                    <th className="px-2 py-1.5 text-right font-medium text-muted-foreground">ND %</th>
                    <th className="px-2 py-1.5 text-right font-medium text-muted-foreground">Цена ср., ₽</th>
                    <th className="px-2 py-1.5 text-right font-medium text-muted-foreground">Категория %</th>
                    <th className="px-2 py-1.5 text-left font-medium text-muted-foreground">Note</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {nielsenBenchmarks.map((b, idx) => (
                    <tr key={idx} className="border-b last:border-0 hover:bg-muted/30">
                      <td className="px-1 py-1">
                        <Input
                          value={b.channel}
                          onChange={(e) => {
                            const v = e.target.value;
                            setNielsenBenchmarks((p) =>
                              p.map((x, i) => (i === idx ? { ...x, channel: v } : x)),
                            );
                          }}
                          className="h-7 text-xs"
                        />
                      </td>
                      <td className="px-1 py-1">
                        <Input
                          type="number"
                          value={b.universe_outlets ?? ""}
                          onChange={(e) => {
                            const v = e.target.value === "" ? null : Number(e.target.value);
                            setNielsenBenchmarks((p) =>
                              p.map((x, i) => (i === idx ? { ...x, universe_outlets: v } : x)),
                            );
                          }}
                          className="h-7 text-xs text-right"
                        />
                      </td>
                      <td className="px-1 py-1">
                        <Input
                          type="number"
                          step="0.01"
                          value={b.offtake ?? ""}
                          onChange={(e) => {
                            const v = e.target.value === "" ? null : Number(e.target.value);
                            setNielsenBenchmarks((p) =>
                              p.map((x, i) => (i === idx ? { ...x, offtake: v } : x)),
                            );
                          }}
                          className="h-7 text-xs text-right"
                        />
                      </td>
                      <td className="px-1 py-1">
                        <Input
                          type="number"
                          step="0.01"
                          value={b.nd_pct ?? ""}
                          onChange={(e) => {
                            const v = e.target.value === "" ? null : Number(e.target.value);
                            setNielsenBenchmarks((p) =>
                              p.map((x, i) => (i === idx ? { ...x, nd_pct: v } : x)),
                            );
                          }}
                          placeholder="0..1"
                          className="h-7 text-xs text-right"
                        />
                      </td>
                      <td className="px-1 py-1">
                        <Input
                          type="number"
                          step="0.01"
                          value={b.avg_price ?? ""}
                          onChange={(e) => {
                            const v = e.target.value === "" ? null : Number(e.target.value);
                            setNielsenBenchmarks((p) =>
                              p.map((x, i) => (i === idx ? { ...x, avg_price: v } : x)),
                            );
                          }}
                          className="h-7 text-xs text-right"
                        />
                      </td>
                      <td className="px-1 py-1">
                        <Input
                          type="number"
                          step="0.01"
                          value={b.category_value_share ?? ""}
                          onChange={(e) => {
                            const v = e.target.value === "" ? null : Number(e.target.value);
                            setNielsenBenchmarks((p) =>
                              p.map((x, i) => (i === idx ? { ...x, category_value_share: v } : x)),
                            );
                          }}
                          placeholder="0..1"
                          className="h-7 text-xs text-right"
                        />
                      </td>
                      <td className="px-1 py-1">
                        <Input
                          value={b.note ?? ""}
                          onChange={(e) => {
                            const v = e.target.value;
                            setNielsenBenchmarks((p) =>
                              p.map((x, i) => (i === idx ? { ...x, note: v } : x)),
                            );
                          }}
                          className="h-7 text-xs"
                        />
                      </td>
                      <td className="px-1 py-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() =>
                            setNielsenBenchmarks((p) => p.filter((_, i) => i !== idx))
                          }
                          className="text-destructive hover:text-destructive px-2 h-7"
                          title="Удалить"
                        >
                          &times;
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                setNielsenBenchmarks((prev) => [
                  ...prev,
                  {
                    channel: "",
                    universe_outlets: null,
                    offtake: null,
                    nd_pct: null,
                    avg_price: null,
                    category_value_share: null,
                    note: "",
                  },
                ])
              }
            >
              + Добавить бенчмарк
            </Button>
            <Button size="sm" onClick={saveNielsenBenchmarks}>
              Сохранить бенчмарки
            </Button>
          </div>
        </CardContent>}
      </Card>

      {/* ====================================================== */}
      {/* 9. КП на производство (Phase 8.10)                     */}
      {/* ====================================================== */}
      <Card>
        <CardHeader className="cursor-pointer" onClick={() => toggleSection(9)}>
          <CardTitle className="text-base flex items-center justify-between">
            9. КП на производство
            <span className="text-muted-foreground text-sm font-normal">{collapsed.has(9) ? "▸" : "▾"}</span>
          </CardTitle>
          <CardDescription>
            Детальные котировки копакеров и поставщиков сырья. Используется
            для обоснования COGS и сравнения предложений.
          </CardDescription>
        </CardHeader>
        {!collapsed.has(9) && <CardContent className="space-y-3">
          {supplierQuotes.length === 0 && (
            <p className="text-sm text-muted-foreground">КП пока нет.</p>
          )}
          {supplierQuotes.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs border-collapse table-fixed">
                <thead>
                  <tr className="border-b">
                    <th className="px-2 py-1.5 text-left font-medium text-muted-foreground w-[18%]">Поставщик</th>
                    <th className="px-2 py-1.5 text-left font-medium text-muted-foreground w-[18%]">Позиция</th>
                    <th className="px-2 py-1.5 text-left font-medium text-muted-foreground w-[8%]">Ед.</th>
                    <th className="px-2 py-1.5 text-right font-medium text-muted-foreground w-[12%]">Цена ₽/ед</th>
                    <th className="px-2 py-1.5 text-right font-medium text-muted-foreground w-[10%]">МОЗ</th>
                    <th className="px-2 py-1.5 text-right font-medium text-muted-foreground w-[10%]">Срок (дн)</th>
                    <th className="px-2 py-1.5 text-left font-medium text-muted-foreground w-[18%]">Примечание</th>
                    <th className="w-[6%]" />
                  </tr>
                </thead>
                <tbody>
                  {supplierQuotes.map((q, idx) => (
                    <tr key={idx} className="border-b last:border-0 hover:bg-muted/30">
                      <td className="px-1 py-1">
                        <Input
                          value={q.supplier}
                          onChange={(e) => {
                            const v = e.target.value;
                            setSupplierQuotes((p) =>
                              p.map((x, i) => (i === idx ? { ...x, supplier: v } : x)),
                            );
                          }}
                          className="h-7 text-xs"
                        />
                      </td>
                      <td className="px-1 py-1">
                        <Input
                          value={q.item}
                          onChange={(e) => {
                            const v = e.target.value;
                            setSupplierQuotes((p) =>
                              p.map((x, i) => (i === idx ? { ...x, item: v } : x)),
                            );
                          }}
                          className="h-7 text-xs"
                        />
                      </td>
                      <td className="px-1 py-1">
                        <Input
                          value={q.unit ?? ""}
                          onChange={(e) => {
                            const v = e.target.value;
                            setSupplierQuotes((p) =>
                              p.map((x, i) => (i === idx ? { ...x, unit: v } : x)),
                            );
                          }}
                          placeholder="кг / шт"
                          className="h-7 text-xs w-16"
                        />
                      </td>
                      <td className="px-1 py-1">
                        <Input
                          type="number"
                          step="0.01"
                          value={q.price_per_unit ?? ""}
                          onChange={(e) => {
                            const v = e.target.value === "" ? null : Number(e.target.value);
                            setSupplierQuotes((p) =>
                              p.map((x, i) => (i === idx ? { ...x, price_per_unit: v } : x)),
                            );
                          }}
                          className="h-7 text-xs text-right"
                        />
                      </td>
                      <td className="px-1 py-1">
                        <Input
                          type="number"
                          value={q.moq ?? ""}
                          onChange={(e) => {
                            const v = e.target.value === "" ? null : Number(e.target.value);
                            setSupplierQuotes((p) =>
                              p.map((x, i) => (i === idx ? { ...x, moq: v } : x)),
                            );
                          }}
                          className="h-7 text-xs text-right w-20"
                        />
                      </td>
                      <td className="px-1 py-1">
                        <Input
                          type="number"
                          value={q.lead_time_days ?? ""}
                          onChange={(e) => {
                            const v = e.target.value === "" ? null : Number(e.target.value);
                            setSupplierQuotes((p) =>
                              p.map((x, i) => (i === idx ? { ...x, lead_time_days: v } : x)),
                            );
                          }}
                          className="h-7 text-xs text-right w-16"
                        />
                      </td>
                      <td className="px-1 py-1">
                        <Input
                          value={q.note ?? ""}
                          onChange={(e) => {
                            const v = e.target.value;
                            setSupplierQuotes((p) =>
                              p.map((x, i) => (i === idx ? { ...x, note: v } : x)),
                            );
                          }}
                          className="h-7 text-xs"
                        />
                      </td>
                      <td className="px-1 py-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() =>
                            setSupplierQuotes((p) => p.filter((_, i) => i !== idx))
                          }
                          className="text-destructive hover:text-destructive px-2 h-7"
                          title="Удалить"
                        >
                          &times;
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                setSupplierQuotes((prev) => [
                  ...prev,
                  {
                    supplier: "",
                    item: "",
                    unit: "",
                    price_per_unit: null,
                    moq: null,
                    lead_time_days: null,
                    note: "",
                  },
                ])
              }
            >
              + Добавить КП
            </Button>
            <Button size="sm" onClick={saveSupplierQuotes}>
              Сохранить КП
            </Button>
          </div>
        </CardContent>}
      </Card>

      {/* ====================================================== */}
      {/* 10. Marketing Research (Phase 7.7)                     */}
      {/* ====================================================== */}
      <MarketingResearchSection
        projectId={projectId}
        research={project.marketing_research as Record<string, never> | null}
        onUpdate={() => {
          getProject(projectId).then((data) => {
            setProject(data);
          });
        }}
      />
    </div>
  );
}
