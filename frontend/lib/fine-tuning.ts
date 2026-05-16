/**
 * API обёртки для C #14 Fine Tuning per-period overrides.
 *
 * Backend endpoints (см. `backend/app/api/fine_tuning.py`):
 *   GET  /api/projects/{id}/fine-tuning/per-period/sku/{psk_id}
 *   PUT  /api/projects/{id}/fine-tuning/per-period/sku/{psk_id}
 *   GET  /api/projects/{id}/fine-tuning/per-period/channel/{psk_channel_id}
 *   PUT  /api/projects/{id}/fine-tuning/per-period/channel/{psk_channel_id}
 *
 * NB: `psk_id` в URL — это id строки `ProjectSKU` (а не глобальный `SKU.id`),
 * хотя backend использует имя `sku_id`. Это id из `ProjectSKURead.id`.
 *
 * PUT возвращает 204 No Content (apiPut вернёт `undefined`).
 * GET возвращает поля как `(string | null)[] | null` — string для Decimal.
 */

import { apiGet, apiPut } from "./api";

import type {
  ChannelOverridesPayload,
  ChannelOverridesResponse,
  SkuOverridesPayload,
  SkuOverridesResponse,
} from "@/types/api";

export function getSkuOverrides(
  projectId: number,
  pskId: number,
): Promise<SkuOverridesResponse> {
  return apiGet<SkuOverridesResponse>(
    `/api/projects/${projectId}/fine-tuning/per-period/sku/${pskId}`,
  );
}

export function putSkuOverrides(
  projectId: number,
  pskId: number,
  body: SkuOverridesPayload,
): Promise<void> {
  return apiPut<void>(
    `/api/projects/${projectId}/fine-tuning/per-period/sku/${pskId}`,
    body,
  );
}

export function getChannelOverrides(
  projectId: number,
  pskChannelId: number,
): Promise<ChannelOverridesResponse> {
  return apiGet<ChannelOverridesResponse>(
    `/api/projects/${projectId}/fine-tuning/per-period/channel/${pskChannelId}`,
  );
}

export function putChannelOverrides(
  projectId: number,
  pskChannelId: number,
  body: ChannelOverridesPayload,
): Promise<void> {
  return apiPut<void>(
    `/api/projects/${projectId}/fine-tuning/per-period/channel/${pskChannelId}`,
    body,
  );
}
