/**
 * Типизированные обёртки для Channel / ProjectSKUChannel / RefSeasonality.
 *
 * Backend структура:
 *   /api/channels                          — read-only справочник 25 каналов
 *   /api/project-skus/{psk_id}/channels    — list/create PSC для PSK
 *   /api/psk-channels/{id}                 — get/patch/delete (плоский)
 *   /api/ref-seasonality                   — read-only профили сезонности
 */

import { apiDelete, apiGet, apiPatch, apiPost } from "./api";

import type {
  Channel,
  ProjectSKUChannelCreate,
  ProjectSKUChannelRead,
  ProjectSKUChannelUpdate,
  RefSeasonality,
} from "@/types/api";

// ============================================================
// Channel справочник (read-only)
// ============================================================

export function listChannels(): Promise<Channel[]> {
  return apiGet<Channel[]>("/api/channels");
}

// ============================================================
// ProjectSKUChannel
// ============================================================

export function listProjectSkuChannels(
  pskId: number,
): Promise<ProjectSKUChannelRead[]> {
  return apiGet<ProjectSKUChannelRead[]>(
    `/api/project-skus/${pskId}/channels`,
  );
}

export function getPskChannel(
  pskChannelId: number,
): Promise<ProjectSKUChannelRead> {
  return apiGet<ProjectSKUChannelRead>(`/api/psk-channels/${pskChannelId}`);
}

export function addChannelToPsk(
  pskId: number,
  data: ProjectSKUChannelCreate,
): Promise<ProjectSKUChannelRead> {
  return apiPost<ProjectSKUChannelRead>(
    `/api/project-skus/${pskId}/channels`,
    data,
  );
}

export function updatePskChannel(
  pskChannelId: number,
  data: ProjectSKUChannelUpdate,
): Promise<ProjectSKUChannelRead> {
  return apiPatch<ProjectSKUChannelRead>(
    `/api/psk-channels/${pskChannelId}`,
    data,
  );
}

export function deletePskChannel(pskChannelId: number): Promise<void> {
  return apiDelete<void>(`/api/psk-channels/${pskChannelId}`);
}

// ============================================================
// Reference
// ============================================================

export function listRefSeasonality(): Promise<RefSeasonality[]> {
  return apiGet<RefSeasonality[]>("/api/ref-seasonality");
}
