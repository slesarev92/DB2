/**
 * Типизированные обёртки над apiGet/Post/Patch/Delete для проектов
 * и связанных справочников.
 *
 * Использование:
 *   const items = await listProjects();
 *   const newProject = await createProject({ name: ..., start_date: ... });
 */

import { apiDelete, apiGet, apiPatch, apiPost } from "./api";

import type {
  ProjectCreate,
  ProjectListItem,
  ProjectRead,
  ProjectUpdate,
  RefInflation,
} from "@/types/api";

export function listProjects(): Promise<ProjectListItem[]> {
  return apiGet<ProjectListItem[]>("/api/projects");
}

export function getProject(id: number): Promise<ProjectRead> {
  return apiGet<ProjectRead>(`/api/projects/${id}`);
}

export function createProject(data: ProjectCreate): Promise<ProjectRead> {
  return apiPost<ProjectRead>("/api/projects", data);
}

export function updateProject(
  id: number,
  data: ProjectUpdate,
): Promise<ProjectRead> {
  return apiPatch<ProjectRead>(`/api/projects/${id}`, data);
}

export function deleteProject(id: number): Promise<void> {
  return apiDelete<void>(`/api/projects/${id}`);
}

export function listRefInflation(): Promise<RefInflation[]> {
  return apiGet<RefInflation[]>("/api/ref-inflation");
}
