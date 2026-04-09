"use client";

import { useCallback, useEffect, useState } from "react";

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
import { ApiError } from "@/lib/api";
import { getProject, updateProject } from "@/lib/projects";

import type {
  Approver,
  FunctionDepartment,
  FunctionReadinessEntry,
  FunctionReadinessMap,
  FunctionReadinessStatus,
  GateStage,
  ProjectRead,
  ProjectUpdate,
  RiskItem,
  RoadmapTask,
  ValidationTests,
} from "@/types/api";
import { FUNCTION_DEPARTMENTS } from "@/types/api";

interface ContentTabProps {
  projectId: number;
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

export function ContentTab({ projectId }: ContentTabProps) {
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

  // Статус сохранения (для scalars + для JSONB секций)
  const [savingField, setSavingField] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<Date | null>(null);

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
        <CardHeader>
          <CardTitle className="text-base">1. Общая информация</CardTitle>
          <CardDescription>
            Стадия паспорта, владелец, базовые атрибуты проекта.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
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
            <Label htmlFor="description">Описание проекта</Label>
            <Textarea
              id="description"
              rows={3}
              value={scalars.description}
              onChange={(e) => setScalarField("description", e.target.value)}
              onBlur={() => flushScalar("description")}
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="project_goal">Цель проекта</Label>
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
              <Label htmlFor="innovation_type">Тип инновации</Label>
              <Input
                id="innovation_type"
                value={scalars.innovation_type}
                onChange={(e) => setScalarField("innovation_type", e.target.value)}
                onBlur={() => flushScalar("innovation_type")}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="geography">География</Label>
              <Input
                id="geography"
                value={scalars.geography}
                onChange={(e) => setScalarField("geography", e.target.value)}
                onBlur={() => flushScalar("geography")}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="production_type">Тип производства</Label>
              <Input
                id="production_type"
                value={scalars.production_type}
                onChange={(e) => setScalarField("production_type", e.target.value)}
                onBlur={() => flushScalar("production_type")}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ====================================================== */}
      {/* 2. Концепция продукта                                  */}
      {/* ====================================================== */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">2. Концепция продукта</CardTitle>
          <CardDescription>
            Рост, идея, целевая аудитория, технология.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="growth_opportunity">Growth opportunity</Label>
            <Textarea
              id="growth_opportunity"
              rows={2}
              value={scalars.growth_opportunity}
              onChange={(e) => setScalarField("growth_opportunity", e.target.value)}
              onBlur={() => flushScalar("growth_opportunity")}
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="concept_text">Концепция (полный текст)</Label>
            <Textarea
              id="concept_text"
              rows={4}
              value={scalars.concept_text}
              onChange={(e) => setScalarField("concept_text", e.target.value)}
              onBlur={() => flushScalar("concept_text")}
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="rationale">Обоснование</Label>
            <Textarea
              id="rationale"
              rows={3}
              value={scalars.rationale}
              onChange={(e) => setScalarField("rationale", e.target.value)}
              onBlur={() => flushScalar("rationale")}
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="idea_short">Короткая идея</Label>
            <Input
              id="idea_short"
              value={scalars.idea_short}
              onChange={(e) => setScalarField("idea_short", e.target.value)}
              onBlur={() => flushScalar("idea_short")}
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="target_audience">Целевая аудитория</Label>
            <Textarea
              id="target_audience"
              rows={2}
              value={scalars.target_audience}
              onChange={(e) => setScalarField("target_audience", e.target.value)}
              onBlur={() => flushScalar("target_audience")}
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="replacement_target">Кого замещаем</Label>
            <Input
              id="replacement_target"
              value={scalars.replacement_target}
              onChange={(e) => setScalarField("replacement_target", e.target.value)}
              onBlur={() => flushScalar("replacement_target")}
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="technology">Технология</Label>
            <Textarea
              id="technology"
              rows={2}
              value={scalars.technology}
              onChange={(e) => setScalarField("technology", e.target.value)}
              onBlur={() => flushScalar("technology")}
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="rnd_progress">Прогресс R&D</Label>
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
        </CardContent>
      </Card>

      {/* ====================================================== */}
      {/* 3. Валидация (JSONB)                                   */}
      {/* ====================================================== */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">3. Результаты валидации</CardTitle>
          <CardDescription>
            5 подтестов: concept test, naming, design, product, price. Score
            0–100, notes — выводы и рекомендации.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
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
        </CardContent>
      </Card>

      {/* ====================================================== */}
      {/* 4. Риски (JSONB list)                                  */}
      {/* ====================================================== */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">4. Риски</CardTitle>
          <CardDescription>
            Свободный список ключевых рисков. Порядок имеет значение —
            сверху важнее.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
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
        </CardContent>
      </Card>

      {/* ====================================================== */}
      {/* 5. Готовность функций (JSONB map — фиксированные 8)    */}
      {/* ====================================================== */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">5. Готовность функций</CardTitle>
          <CardDescription>
            8 фиксированных департаментов × светофор (green/yellow/red) +
            заметки.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
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
        </CardContent>
      </Card>

      {/* ====================================================== */}
      {/* 6. Дорожная карта (JSONB list)                         */}
      {/* ====================================================== */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">6. Дорожная карта</CardTitle>
          <CardDescription>
            Ключевые задачи проекта с датами, ответственными и статусом.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
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
        </CardContent>
      </Card>

      {/* ====================================================== */}
      {/* 7. Согласующие (JSONB list)                            */}
      {/* ====================================================== */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">7. Согласующие</CardTitle>
          <CardDescription>
            Метрики проекта и те, кто их подписывает (с источниками данных).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
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
                <Label>Источник</Label>
                <Input
                  value={a.source ?? ""}
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
        </CardContent>
      </Card>
    </div>
  );
}
