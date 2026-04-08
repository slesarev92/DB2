/**
 * API обёртки для Scenario / ScenarioResult.
 *
 * Backend endpoints:
 *   GET   /api/projects/{project_id}/scenarios → 3 сценария в порядке Base/Cons/Aggr
 *   GET   /api/scenarios/{id}                  → один сценарий
 *   PATCH /api/scenarios/{id}                  → обновить дельты + notes
 *   GET   /api/scenarios/{id}/results          → 3 ScenarioResult по 3 скоупам
 */

import { apiGet, apiPatch } from "./api";

import type {
  ScenarioRead,
  ScenarioResultRead,
  ScenarioUpdate,
} from "@/types/api";

export function listProjectScenarios(
  projectId: number,
): Promise<ScenarioRead[]> {
  return apiGet<ScenarioRead[]>(`/api/projects/${projectId}/scenarios`);
}

export function getScenario(scenarioId: number): Promise<ScenarioRead> {
  return apiGet<ScenarioRead>(`/api/scenarios/${scenarioId}`);
}

export function updateScenario(
  scenarioId: number,
  data: ScenarioUpdate,
): Promise<ScenarioRead> {
  return apiPatch<ScenarioRead>(`/api/scenarios/${scenarioId}`, data);
}

export function listScenarioResults(
  scenarioId: number,
): Promise<ScenarioResultRead[]> {
  return apiGet<ScenarioResultRead[]>(
    `/api/scenarios/${scenarioId}/results`,
  );
}
