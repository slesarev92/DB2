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
  BulkChannelLinkCreate,
  Channel,
  ChannelCreate,
  ChannelUpdate,
  ProjectSKUChannelCreate,
  ProjectSKUChannelRead,
  ProjectSKUChannelUpdate,
  RefSeasonality,
} from "@/types/api";

// ============================================================
// Channel справочник (read + CRUD; C #16)
// ============================================================

export function listChannels(): Promise<Channel[]> {
  return apiGet<Channel[]>("/api/channels");
}

/** C #16: создать кастомный канал в каталоге. */
export function createChannel(data: ChannelCreate): Promise<Channel> {
  return apiPost<Channel>("/api/channels", data);
}

/** C #16: PATCH полей канала в каталоге (name/group/source_type/...). */
export function updateChannel(
  id: number,
  data: ChannelUpdate,
): Promise<Channel> {
  return apiPatch<Channel>(`/api/channels/${id}`, data);
}

/** C #16: удалить канал из каталога (запрещено если есть FK-зависимости). */
export function deleteChannel(id: number): Promise<void> {
  return apiDelete<void>(`/api/channels/${id}`);
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

/**
 * C #16: атомарно привязать список каналов к PSK с общими defaults.
 * Backend гарантирует rollback при FK / unique violation.
 */
export function bulkAddChannelsToPsk(
  pskId: number,
  data: BulkChannelLinkCreate,
): Promise<ProjectSKUChannelRead[]> {
  return apiPost<ProjectSKUChannelRead[]>(
    `/api/project-skus/${pskId}/channels/bulk`,
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
