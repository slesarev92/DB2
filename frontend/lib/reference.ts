/**
 * API обёртки для read-only справочников (периоды, инфляция, сезонность).
 *
 * RefInflation/RefSeasonality уже есть в lib/projects.ts и lib/channels.ts
 * соответственно — здесь только Period (нужен для AG Grid columns в задаче 4.1).
 */

import { apiGet } from "./api";

import type { Period } from "@/types/api";

export function listPeriods(): Promise<Period[]> {
  return apiGet<Period[]>("/api/periods");
}
