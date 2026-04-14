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
  await _downloadBlobAs(
    `/api/projects/${projectId}/export/xlsx`,
    `project_${projectId}.xlsx`,
    "xlsx",
  );
}

/**
 * Скачивает PPTX экспорт паспорта проекта (задача 5.2).
 *
 * Backend: GET /api/projects/{id}/export/pptx → 13 слайдов (title,
 * content sections из 4.5, KPI, PnL, BOM, roadmap, risks, approvers,
 * executive summary). Package images из MediaAsset embedded в слайд
 * «Продуктовый микс».
 */
export async function downloadProjectPptx(projectId: number): Promise<void> {
  await _downloadBlobAs(
    `/api/projects/${projectId}/export/pptx`,
    `project_${projectId}.pptx`,
    "pptx",
  );
}

/**
 * Скачивает PDF-паспорт проекта (задача 5.3).
 *
 * Backend: GET /api/projects/{id}/export/pdf — Jinja2 HTML template +
 * WeasyPrint → PDF A4. Включает content fields Phase 4.5, KPI, PnL,
 * риски, roadmap и т.д.
 */
export async function downloadProjectPdf(projectId: number): Promise<void> {
  await _downloadBlobAs(
    `/api/projects/${projectId}/export/pdf`,
    `project_${projectId}.pdf`,
    "pdf",
  );
}


/**
 * Универсальный blob → download trigger с диагностикой.
 *
 * BUG-01 на prod выглядел как "ничего не происходит при клике". Root cause
 * не подтверждён (backend отдаёт 200 OK, правильный Content-Disposition).
 * Гипотезы: browser extension блокирует blob URL / popup blocker /
 * CSP connect-src. Логируем каждый шаг в console чтобы пользователь
 * мог показать DevTools output.
 */
async function _downloadBlobAs(
  path: string,
  filename: string,
  kind: string,
): Promise<void> {
  console.info(`[export] start ${kind}: GET ${path}`);
  const blob = await apiGetBlob(path);
  console.info(
    `[export] blob received ${kind}: ${blob.size} bytes, type=${blob.type}`,
  );
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  try {
    a.click();
    console.info(`[export] click triggered ${kind} → ${filename}`);
  } catch (clickErr) {
    console.error(`[export] a.click() failed for ${kind}:`, clickErr);
    throw clickErr;
  } finally {
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
