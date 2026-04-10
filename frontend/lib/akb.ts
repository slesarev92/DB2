/**
 * API wrappers for AKB distribution plan (B-12).
 */

import { apiDelete, apiGet, apiPatch, apiPost } from "./api";

import type { AKBRead } from "@/types/api";

export function listAkbEntries(projectId: number): Promise<AKBRead[]> {
  return apiGet<AKBRead[]>(`/api/projects/${projectId}/akb`);
}

export function createAkbEntry(
  projectId: number,
  data: {
    channel_id: number;
    universe_outlets?: number | null;
    target_outlets?: number | null;
    coverage_pct?: string | null;
    weighted_distribution?: string | null;
    notes?: string | null;
  },
): Promise<AKBRead> {
  return apiPost<AKBRead>(`/api/projects/${projectId}/akb`, data);
}

export function updateAkbEntry(
  projectId: number,
  entryId: number,
  data: {
    universe_outlets?: number | null;
    target_outlets?: number | null;
    coverage_pct?: string | null;
    weighted_distribution?: string | null;
    notes?: string | null;
  },
): Promise<AKBRead> {
  return apiPatch<AKBRead>(`/api/projects/${projectId}/akb/${entryId}`, data);
}

export function deleteAkbEntry(
  projectId: number,
  entryId: number,
): Promise<void> {
  return apiDelete<void>(`/api/projects/${projectId}/akb/${entryId}`);
}
