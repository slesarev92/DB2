/**
 * C #21: Константы статуса жизненного цикла проекта.
 *
 * Синхронизировано с backend ProjectStatus (backend/app/models/project.py).
 * Используется в project header badge и в project list.
 */

import type { ProjectStatus } from "@/types/api";

export const PROJECT_STATUS_LABELS: Record<ProjectStatus, string> = {
  draft: "Черновик",
  active: "Активный",
  paused: "Приостановлен",
  cancelled: "Отменён",
  completed: "Завершён",
  archived: "Архив",
};

export const PROJECT_STATUS_COLORS: Record<ProjectStatus, string> = {
  draft: "bg-gray-100 text-gray-700",
  active: "bg-blue-100 text-blue-700",
  paused: "bg-amber-100 text-amber-700",
  cancelled: "bg-red-100 text-red-700",
  completed: "bg-green-100 text-green-700",
  archived: "bg-slate-100 text-slate-500",
};

/** Порядок отображения статусов в dropdown (логический, не алфавитный). */
export const PROJECT_STATUS_ORDER: ProjectStatus[] = [
  "draft",
  "active",
  "paused",
  "completed",
  "cancelled",
  "archived",
];
