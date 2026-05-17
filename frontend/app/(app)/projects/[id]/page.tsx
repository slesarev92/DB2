"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AkbTab } from "@/components/projects/akb-tab";
import { ChannelsTab } from "@/components/projects/channels-tab";
import { ContentTab } from "@/components/projects/content-tab";
import { FinancialPlanEditor } from "@/components/projects/financial-plan-editor";
import { FineTuningPerPeriodPanel } from "@/components/projects/fine-tuning-per-period-panel";
import { IngredientsCatalog } from "@/components/projects/ingredients-catalog";
import { ObppcTab } from "@/components/projects/obppc-tab";
import { PeriodsTab } from "@/components/projects/periods-tab";
import { ResultsTab } from "@/components/projects/results-tab";
import { ScenariosTab } from "@/components/projects/scenarios-tab";
import { SensitivityTab } from "@/components/projects/sensitivity-tab";
import { PricingTab } from "@/components/projects/pricing-tab";
import { ValueChainTab } from "@/components/projects/value-chain-tab";
import { PnlTab } from "@/components/projects/pnl-tab";
import { GateTimeline } from "@/components/projects/gate-timeline";
import { SkusTab } from "@/components/projects/skus-tab";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAIPanel } from "@/components/ai-panel/ai-panel-context";
import { toast } from "sonner";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { getProject, updateProject } from "@/lib/projects";
import {
  PROJECT_STATUS_COLORS,
  PROJECT_STATUS_LABELS,
  PROJECT_STATUS_ORDER,
} from "@/lib/project-status";
import {
  TAB_ORDER,
  useProjectNavRegistry,
  type TabValue,
} from "@/lib/project-nav-context";
import { useProjectProgress } from "@/lib/use-project-progress";
import { useKeyboardShortcuts } from "@/lib/use-keyboard-shortcuts";
import { useUnsavedChanges } from "@/lib/use-unsaved-changes";

import type { ProjectRead, ProjectStatus } from "@/types/api";

/** Validate a query param as a valid tab value. */
function parseTabParam(value: string | null): TabValue {
  if (value && (TAB_ORDER as readonly string[]).includes(value)) {
    return value as TabValue;
  }
  return "overview";
}

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const projectId = Number(params.id);
  const [project, setProject] = useState<ProjectRead | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTabState] = useState<TabValue>(() =>
    parseTabParam(searchParams.get("tab")),
  );
  const { setProjectId } = useAIPanel();
  const { containerRef, confirmIfDirty } = useUnsavedChanges();
  const { register, unregister } = useProjectNavRegistry();
  const { groups, loading: progressLoading } = useProjectProgress(
    projectId,
    project,
  );

  /** Switch tab — blurs active input first, updates state + URL. */
  const switchTab = useCallback(
    (tab: TabValue) => {
      confirmIfDirty(() => {
        setActiveTabState(tab);
        const url = `/projects/${projectId}?tab=${tab}`;
        router.replace(url, { scroll: false });
      });
    },
    [confirmIfDirty, projectId, router],
  );

  // Register into ProjectNavContext for sidebar
  useEffect(() => {
    if (project) {
      register({
        projectId,
        projectName: project.name,
        activeTab,
        setActiveTab: switchTab,
        groups,
        progressLoading,
      });
    }
    return () => unregister();
  }, [
    project,
    projectId,
    activeTab,
    switchTab,
    groups,
    progressLoading,
    register,
    unregister,
  ]);

  // Ctrl+[ previous tab, Ctrl+] next tab
  const goToPrevTab = useCallback(() => {
    setActiveTabState((cur) => {
      const idx = TAB_ORDER.indexOf(cur);
      const prev = idx > 0 ? TAB_ORDER[idx - 1] : cur;
      if (prev !== cur) {
        router.replace(`/projects/${projectId}?tab=${prev}`, { scroll: false });
      }
      return prev;
    });
  }, [projectId, router]);

  const goToNextTab = useCallback(() => {
    setActiveTabState((cur) => {
      const idx = TAB_ORDER.indexOf(cur);
      const next =
        idx < TAB_ORDER.length - 1 ? TAB_ORDER[idx + 1] : cur;
      if (next !== cur) {
        router.replace(`/projects/${projectId}?tab=${next}`, { scroll: false });
      }
      return next;
    });
  }, [projectId, router]);

  // Ctrl+S — blur active element to trigger onBlur auto-save handlers
  const saveShortcut = useCallback(() => {
    const el = document.activeElement;
    if (el instanceof HTMLElement) el.blur();
  }, []);

  const shortcuts = useMemo(
    () => [
      { key: "[", ctrl: true, handler: goToPrevTab },
      { key: "]", ctrl: true, handler: goToNextTab },
      { key: "s", ctrl: true, handler: saveShortcut },
    ],
    [goToPrevTab, goToNextTab, saveShortcut],
  );

  useKeyboardShortcuts(shortcuts, project !== null);

  // C #21: PATCH project status from header badge dropdown
  const updateProjectStatus = useCallback(
    async (status: ProjectStatus) => {
      if (!project) return;
      try {
        const updated = await updateProject(projectId, { status });
        setProject(updated);
        toast.success(`Статус изменён: ${PROJECT_STATUS_LABELS[status]}`);
      } catch (err) {
        const msg =
          err instanceof ApiError
            ? err.detail ?? err.message
            : "Ошибка сохранения статуса";
        toast.error(msg);
      }
    },
    [project, projectId],
  );

  // Phase 7.5: sync AI panel with current project for usage/budget fetch
  useEffect(() => {
    if (!Number.isNaN(projectId)) setProjectId(projectId);
    return () => setProjectId(null);
  }, [projectId, setProjectId]);

  useEffect(() => {
    if (Number.isNaN(projectId)) {
      setError("Некорректный id проекта");
      return;
    }
    let cancelled = false;
    getProject(projectId)
      .then((data) => {
        if (!cancelled) setProject(data);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setError("Проект не найден");
        } else {
          setError(
            err instanceof ApiError ? err.detail ?? err.message : "Ошибка загрузки",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  if (error !== null) {
    return (
      <div className="space-y-4">
        <Card className="border-destructive">
          <CardContent className="pt-6 text-sm text-destructive">
            {error}
          </CardContent>
        </Card>
        <Button variant="outline" onClick={() => router.push("/projects")}>
          ← К списку проектов
        </Button>
      </div>
    );
  }

  if (project === null) {
    return <p className="text-sm text-muted-foreground">Загрузка...</p>;
  }

  return (
    <div className="space-y-6" ref={containerRef}>
      {/* Project header */}
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold">{project.name}</h1>
          {/* C #21: статус проекта — кликабельный badge-dropdown */}
          <Select
            value={project.status}
            onValueChange={(v) => updateProjectStatus(v as ProjectStatus)}
          >
            <SelectTrigger
              size="sm"
              className={`h-7 w-auto px-2 text-xs border-0 font-medium ${PROJECT_STATUS_COLORS[project.status]}`}
            >
              <SelectValue>{PROJECT_STATUS_LABELS[project.status]}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {PROJECT_STATUS_ORDER.map((s) => (
                <SelectItem key={s} value={s}>
                  {PROJECT_STATUS_LABELS[s]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <p className="text-sm text-muted-foreground">
          Старт: {formatDate(project.start_date)} · {project.horizon_years} лет
        </p>
      </div>

      {/* Active section content */}
      {activeTab === "overview" && (
        <div className="space-y-6">
        {/* Gate Timeline (Phase 8.7) */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Gate-шкала проекта</CardTitle>
          </CardHeader>
          <CardContent>
            <GateTimeline currentGate={project.gate_stage ?? null} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Финансовые параметры</CardTitle>
            <CardDescription>
              Дефолты соответствуют GORJI Excel модели.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
              <div>
                <dt className="text-muted-foreground">WACC</dt>
                <dd className="font-medium">
                  {(Number(project.wacc) * 100).toFixed(2)}%
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Налог на прибыль</dt>
                <dd className="font-medium">
                  {(Number(project.tax_rate) * 100).toFixed(2)}%
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Working Capital</dt>
                <dd className="font-medium">
                  {(Number(project.wc_rate) * 100).toFixed(2)}%
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">VAT</dt>
                <dd className="font-medium">
                  {(Number(project.vat_rate) * 100).toFixed(2)}%
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Валюта</dt>
                <dd className="font-medium">{project.currency}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Профиль инфляции</dt>
                <dd className="font-medium">
                  {project.inflation_profile_id ?? "—"}
                </dd>
              </div>
            </dl>
          </CardContent>
        </Card>
        </div>
      )}

      {activeTab === "content" && (
        <ContentTab
          projectId={projectId}
          onProjectUpdate={(updated) => setProject((prev) => prev ? { ...prev, ...updated } : prev)}
        />
      )}

      {activeTab === "financial-plan" && (
        <FinancialPlanEditor projectId={projectId} />
      )}

      {activeTab === "skus" && <SkusTab projectId={projectId} />}

      {activeTab === "ingredients" && <IngredientsCatalog />}

      {activeTab === "channels" && <ChannelsTab projectId={projectId} />}

      {activeTab === "akb" && <AkbTab projectId={projectId} />}

      {activeTab === "obppc" && <ObppcTab projectId={projectId} />}

      {activeTab === "periods" && <PeriodsTab projectId={projectId} />}

      {activeTab === "fine-tuning" && (
        <FineTuningPerPeriodPanel projectId={projectId} />
      )}

      {activeTab === "scenarios" && <ScenariosTab projectId={projectId} />}

      {activeTab === "results" && <ResultsTab projectId={projectId} />}

      {activeTab === "sensitivity" && <SensitivityTab projectId={projectId} />}

      {activeTab === "pricing" && <PricingTab projectId={projectId} />}

      {activeTab === "value-chain" && <ValueChainTab projectId={projectId} />}

      {activeTab === "pnl" && <PnlTab projectId={projectId} />}
    </div>
  );
}
