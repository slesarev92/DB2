/**
 * API обёртки для импорта фактических данных (B-02).
 *
 * POST /api/projects/{id}/actual-import?scenario_id — upload xlsx
 * GET  /api/projects/{id}/actual-import/template    — download template
 */

import { getAccessToken } from "./auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface ActualImportResult {
  imported: number;
  skipped: number;
  errors: string[];
}

export async function uploadActualData(
  projectId: number,
  scenarioId: number,
  file: File,
): Promise<ActualImportResult> {
  const token = getAccessToken();
  const formData = new FormData();
  formData.append("file", file);

  const resp = await fetch(
    `${API_URL}/api/projects/${projectId}/actual-import?scenario_id=${scenarioId}`,
    {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    },
  );

  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`;
    try {
      const body = await resp.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // keep default
    }
    throw new Error(detail);
  }

  return (await resp.json()) as ActualImportResult;
}

export function getActualTemplateUrl(projectId: number): string {
  return `${API_URL}/api/projects/${projectId}/actual-import/template`;
}
