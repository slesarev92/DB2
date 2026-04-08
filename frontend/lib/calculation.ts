/**
 * API обёртки для асинхронного пересчёта проекта через Celery.
 *
 * Flow:
 *   1. POST /api/projects/{id}/recalculate → 202 + { task_id, status }
 *   2. polling GET /api/tasks/{task_id} каждую секунду
 *   3. при status=SUCCESS → refetch scenario results
 *   4. при status=FAILURE → показать error + traceback
 *
 * См. backend/app/tasks/calculate_project.py для task implementation
 * и backend/app/api/tasks.py для status endpoint.
 */

import { apiGet, apiPost } from "./api";

import type { RecalculateResponse, TaskStatusResponse } from "@/types/api";

export function recalculateProject(
  projectId: number,
): Promise<RecalculateResponse> {
  return apiPost<RecalculateResponse>(
    `/api/projects/${projectId}/recalculate`,
  );
}

export function getTaskStatus(taskId: string): Promise<TaskStatusResponse> {
  return apiGet<TaskStatusResponse>(`/api/tasks/${taskId}`);
}
