/**
 * API обёртки для экспорта проекта (Фаза 5: XLSX, потом PPT, PDF).
 *
 * downloadProjectXlsx(projectId) → запрашивает Blob с auth и триггерит
 * браузер на скачивание файла. Не возвращает данные — side effect.
 */

import { apiGetBlob } from "./api";

/**
 * Скачивает XLSX экспорт проекта. Триггерит browser download.
 *
 * Backend: GET /api/projects/{id}/export/xlsx → 3 листа (Вводные / PnL / KPI).
 * Если ScenarioResult ещё не посчитан — KPI содержит "—".
 */
export async function downloadProjectXlsx(projectId: number): Promise<void> {
  const blob = await apiGetBlob(`/api/projects/${projectId}/export/xlsx`);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `project_${projectId}.xlsx`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Освобождаем object URL после клика (через таймаут чтобы браузер успел)
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
