/**
 * Типизированные обёртки для SKU / ProjectSKU / BOM API.
 *
 * Структура backend:
 *   /api/skus                              — глобальный справочник
 *   /api/projects/{project_id}/skus        — list/add SKU в проект
 *   /api/project-skus/{psk_id}             — get/patch/delete (плоский путь)
 *   /api/project-skus/{psk_id}/bom         — list/create BOM
 *   /api/bom-items/{bom_id}                — patch/delete BOM (плоский путь)
 */

import { apiDelete, apiGet, apiPatch, apiPost } from "./api";

import type {
  BOMItemCreate,
  BOMItemRead,
  BOMItemUpdate,
  ProjectSKUCreate,
  ProjectSKUDetail,
  ProjectSKURead,
  ProjectSKUUpdate,
  SKUCreate,
  SKURead,
} from "@/types/api";

// ============================================================
// SKU справочник
// ============================================================

export function listSkus(): Promise<SKURead[]> {
  return apiGet<SKURead[]>("/api/skus");
}

export function createSku(data: SKUCreate): Promise<SKURead> {
  return apiPost<SKURead>("/api/skus", data);
}

// ============================================================
// ProjectSKU
// ============================================================

export function listProjectSkus(projectId: number): Promise<ProjectSKURead[]> {
  return apiGet<ProjectSKURead[]>(`/api/projects/${projectId}/skus`);
}

export function getProjectSku(pskId: number): Promise<ProjectSKUDetail> {
  return apiGet<ProjectSKUDetail>(`/api/project-skus/${pskId}`);
}

export function addSkuToProject(
  projectId: number,
  data: ProjectSKUCreate,
): Promise<ProjectSKURead> {
  return apiPost<ProjectSKURead>(`/api/projects/${projectId}/skus`, data);
}

export function updateProjectSku(
  pskId: number,
  data: ProjectSKUUpdate,
): Promise<ProjectSKURead> {
  return apiPatch<ProjectSKURead>(`/api/project-skus/${pskId}`, data);
}

export function deleteProjectSku(pskId: number): Promise<void> {
  return apiDelete<void>(`/api/project-skus/${pskId}`);
}

// ============================================================
// BOM
// ============================================================

export function listBomItems(pskId: number): Promise<BOMItemRead[]> {
  return apiGet<BOMItemRead[]>(`/api/project-skus/${pskId}/bom`);
}

export function createBomItem(
  pskId: number,
  data: BOMItemCreate,
): Promise<BOMItemRead> {
  return apiPost<BOMItemRead>(`/api/project-skus/${pskId}/bom`, data);
}

export function updateBomItem(
  bomId: number,
  data: BOMItemUpdate,
): Promise<BOMItemRead> {
  return apiPatch<BOMItemRead>(`/api/bom-items/${bomId}`, data);
}

export function deleteBomItem(bomId: number): Promise<void> {
  return apiDelete<void>(`/api/bom-items/${bomId}`);
}
