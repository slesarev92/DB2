/**
 * API обёртка для sensitivity analysis (4.4 / E-09).
 *
 * Backend: POST /api/projects/{id}/sensitivity → синхронный response
 * с матрицей 4 параметра × 5 уровней (20 cells).
 */

import { apiPost } from "./api";

import type { SensitivityResponse } from "@/types/api";

export function computeSensitivity(
  projectId: number,
  scope: string = "y1y10",
): Promise<SensitivityResponse> {
  return apiPost<SensitivityResponse>(
    `/api/projects/${projectId}/sensitivity?scope=${scope}`,
  );
}
