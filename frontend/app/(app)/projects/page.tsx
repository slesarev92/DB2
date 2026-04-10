"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { GoNoGoBadge } from "@/components/go-no-go-badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ApiError } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format";
import { deleteProject, listProjects } from "@/lib/projects";

import type { ProjectListItem } from "@/types/api";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ProjectListItem | null>(null);
  const [deleting, setDeleting] = useState(false);

  const fetchProjects = useCallback(() => {
    let cancelled = false;
    listProjects()
      .then((data) => {
        if (!cancelled) setProjects(data);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.detail ?? err.message : "Ошибка загрузки");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => fetchProjects(), [fetchProjects]);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteProject(deleteTarget.id);
      setDeleteTarget(null);
      fetchProjects();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail ?? err.message : "Ошибка удаления",
      );
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Проекты</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Цифровые паспорта проектов вывода новых SKU. Карточка
            показывает базовые KPI после расчёта.
          </p>
        </div>
        {/* shadcn Button у нас без `asChild` Slot — оборачиваем Link
            снаружи, чтобы получить тот же визуал и navigate без runtime
            обработчика. */}
        <Link href="/projects/new">
          <Button type="button">Создать проект</Button>
        </Link>
      </div>

      {error !== null && (
        <Card className="border-destructive">
          <CardContent className="pt-6 text-sm text-destructive">
            {error}
          </CardContent>
        </Card>
      )}

      {projects === null && error === null && (
        <p className="text-sm text-muted-foreground">Загрузка...</p>
      )}

      {projects !== null && projects.length === 0 && (
        <Card>
          <CardContent className="pt-6 text-sm text-muted-foreground">
            Проектов пока нет. Создайте первый, чтобы начать работу.
          </CardContent>
        </Card>
      )}

      <ConfirmDialog
        open={deleteTarget !== null}
        title={`Удалить проект «${deleteTarget?.name ?? ""}»?`}
        description="Проект будет помечен как удалённый. Данные сохранятся в базе, но исчезнут из списка."
        confirmLabel={deleting ? "Удаление..." : "Удалить"}
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />

      {projects !== null && projects.length > 0 && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => (
            <Card key={p.id} className="h-full transition-shadow hover:shadow-md">
              <Link href={`/projects/${p.id}`} className="block">
                <CardHeader>
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="line-clamp-2 text-base">
                      {p.name}
                    </CardTitle>
                    <GoNoGoBadge value={p.go_no_go} />
                  </div>
                  <CardDescription>
                    Старт: {formatDate(p.start_date)} · {p.horizon_years} лет
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <dl className="space-y-1 text-sm">
                    <div className="flex justify-between">
                      <dt className="text-muted-foreground">NPV Y1-Y10</dt>
                      <dd className="font-medium">
                        {formatMoney(p.npv_y1y10)}
                      </dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-muted-foreground">WACC</dt>
                      <dd>{(Number(p.wacc) * 100).toFixed(1)}%</dd>
                    </div>
                  </dl>
                </CardContent>
              </Link>
              <div className="flex justify-end border-t px-4 py-2">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2 text-xs text-muted-foreground hover:text-destructive"
                  onClick={() => setDeleteTarget(p)}
                >
                  Удалить
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
