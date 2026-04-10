/**
 * API wrappers for OBPPC Price-Pack-Channel matrix (B-13).
 */

import { apiDelete, apiGet, apiPatch, apiPost } from "./api";

import type { OBPPCRead, PriceTier } from "@/types/api";

export function listObppcEntries(projectId: number): Promise<OBPPCRead[]> {
  return apiGet<OBPPCRead[]>(`/api/projects/${projectId}/obppc`);
}

export function createObppcEntry(
  projectId: number,
  data: {
    sku_id: number;
    channel_id: number;
    occasion?: string | null;
    price_tier?: PriceTier;
    pack_format?: string;
    pack_size_ml?: number | null;
    price_point?: string | null;
    is_active?: boolean;
    notes?: string | null;
  },
): Promise<OBPPCRead> {
  return apiPost<OBPPCRead>(`/api/projects/${projectId}/obppc`, data);
}

export function updateObppcEntry(
  projectId: number,
  entryId: number,
  data: {
    occasion?: string | null;
    price_tier?: PriceTier;
    pack_format?: string;
    pack_size_ml?: number | null;
    price_point?: string | null;
    is_active?: boolean;
    notes?: string | null;
  },
): Promise<OBPPCRead> {
  return apiPatch<OBPPCRead>(
    `/api/projects/${projectId}/obppc/${entryId}`,
    data,
  );
}

export function deleteObppcEntry(
  projectId: number,
  entryId: number,
): Promise<void> {
  return apiDelete<void>(`/api/projects/${projectId}/obppc/${entryId}`);
}
