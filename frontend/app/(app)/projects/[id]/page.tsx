"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AkbTab } from "@/components/projects/akb-tab";
import { ChannelsTab } from "@/components/projects/channels-tab";
import { ContentTab } from "@/components/projects/content-tab";
import { FinancialPlanEditor } from "@/components/projects/financial-plan-editor";
import { IngredientsCatalog } from "@/components/projects/ingredients-catalog";
import { ObppcTab } from "@/components/projects/obppc-tab";
import { PeriodsTab } from "@/components/projects/periods-tab";
import { ResultsTab } from "@/components/projects/results-tab";
import { ScenariosTab } from "@/components/projects/scenarios-tab";
import { SensitivityTab } from "@/components/projects/sensitivity-tab";
import { SkusTab } from "@/components/projects/skus-tab";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { useAIPanel } from "@/components/ai-panel/ai-panel-context";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { getProject } from "@/lib/projects";

import type { ProjectRead } from "@/types/api";

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const projectId = Number(params.id);
  const [project, setProject] = useState<ProjectRead | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { setProjectId } = useAIPanel();

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
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Link
            href="/projects"
            className="text-sm text-muted-foreground hover:underline"
          >
            ← Все проекты
          </Link>
          <h1 className="mt-1 text-2xl font-semibold">{project.name}</h1>
          <p className="text-sm text-muted-foreground">
            Старт: {formatDate(project.start_date)} · {project.horizon_years} лет
          </p>
        </div>
      </div>

      <Tabs defaultValue="overview">
        <TabsList>
          {/* Настройка */}
          <TabsTrigger value="overview">Параметры</TabsTrigger>
          <TabsTrigger value="content">Содержание</TabsTrigger>
          <div className="mx-1 h-4 w-px shrink-0 bg-border" />
          {/* Продукт */}
          <TabsTrigger value="skus">SKU и BOM</TabsTrigger>
          <TabsTrigger value="ingredients">Ингредиенты</TabsTrigger>
          <div className="mx-1 h-4 w-px shrink-0 bg-border" />
          {/* Дистрибуция */}
          <TabsTrigger value="channels">Каналы</TabsTrigger>
          <TabsTrigger value="akb">АКБ</TabsTrigger>
          <TabsTrigger value="obppc">OBPPC</TabsTrigger>
          <div className="mx-1 h-4 w-px shrink-0 bg-border" />
          {/* Моделирование */}
          <TabsTrigger value="periods">Периоды</TabsTrigger>
          <TabsTrigger value="scenarios">Сценарии</TabsTrigger>
          <div className="mx-1 h-4 w-px shrink-0 bg-border" />
          {/* Анализ */}
          <TabsTrigger value="results">Результаты</TabsTrigger>
          <TabsTrigger value="sensitivity">Чувствительность</TabsTrigger>
        </TabsList>

        {/* ── Настройка ── */}

        <TabsContent value="overview" className="mt-4 space-y-4">
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

          <FinancialPlanEditor projectId={projectId} />
        </TabsContent>

        <TabsContent value="content" className="mt-4">
          <ContentTab projectId={projectId} />
        </TabsContent>

        {/* ── Продукт ── */}

        <TabsContent value="skus" className="mt-4">
          <SkusTab projectId={projectId} />
        </TabsContent>

        <TabsContent value="ingredients" className="mt-4">
          <IngredientsCatalog />
        </TabsContent>

        {/* ── Дистрибуция ── */}

        <TabsContent value="channels" className="mt-4">
          <ChannelsTab projectId={projectId} />
        </TabsContent>

        <TabsContent value="akb" className="mt-4">
          <AkbTab projectId={projectId} />
        </TabsContent>

        <TabsContent value="obppc" className="mt-4">
          <ObppcTab projectId={projectId} />
        </TabsContent>

        {/* ── Моделирование ── */}

        <TabsContent value="periods" className="mt-4">
          <PeriodsTab projectId={projectId} />
        </TabsContent>

        <TabsContent value="scenarios" className="mt-4">
          <ScenariosTab projectId={projectId} />
        </TabsContent>

        {/* ── Анализ ── */}

        <TabsContent value="results" className="mt-4">
          <ResultsTab projectId={projectId} />
        </TabsContent>

        <TabsContent value="sensitivity" className="mt-4">
          <SensitivityTab projectId={projectId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
