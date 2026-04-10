"use client";

import { useEffect, useMemo, useState } from "react";

import { getFinancialPlan } from "@/lib/financial-plan";
import {
  SECTION_GROUPS,
  SECTION_LABELS,
  type GroupProgress,
  type TabValue,
} from "@/lib/project-nav-context";
import { listProjectScenarios, listScenarioResults } from "@/lib/scenarios";
import { listProjectSkus } from "@/lib/skus";
import { listProjectSkuChannels } from "@/lib/channels";

import type { ProjectRead } from "@/types/api";

/** Per-section filled state. */
type FilledMap = Record<TabValue, boolean>;

/**
 * Computes progress indicators for all 12 project sections.
 *
 * Makes lightweight API calls on mount (parallel) to determine:
 * - SKU count, channel presence, financial plan data, calculation status
 * Does NOT require new backend endpoints.
 */
export function useProjectProgress(
  projectId: number,
  project: ProjectRead | null,
): { groups: GroupProgress[]; loading: boolean } {
  const [filled, setFilled] = useState<FilledMap>({
    overview: true,
    content: false,
    "financial-plan": false,
    skus: false,
    ingredients: false,
    channels: false,
    akb: false,
    obppc: false,
    periods: false,
    scenarios: true,
    results: false,
    sensitivity: false,
    pricing: false,
    "value-chain": false,
    pnl: false,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!project) return;
    let cancelled = false;
    const proj = project; // narrow for closure

    async function compute() {
      const next: FilledMap = {
        overview: true,        // always filled — project exists
        content: false,
        "financial-plan": false,
        skus: false,
        ingredients: false,    // always empty — optional/global
        channels: false,
        akb: false,            // always empty — optional
        obppc: false,          // always empty — optional
        periods: false,        // always empty — deep-nested check too expensive
        scenarios: true,       // always filled — auto-created
        results: false,
        sensitivity: false,    // always empty — on-demand
        pricing: false,        // derived from channels — on-demand
        "value-chain": false,  // derived from channels — on-demand
        pnl: false,            // derived from pipeline — on-demand
      };

      // Content: ≥3 of key fields filled
      const contentFields = [
        proj.gate_stage,
        proj.description,
        proj.project_goal,
      ];
      const contentFilled = contentFields.filter(
        (v) => v !== null && v !== undefined && String(v).trim() !== "",
      ).length;
      next.content = contentFilled >= 2;

      try {
        // Parallel API calls
        const [skus, finPlan, scenarios] = await Promise.all([
          listProjectSkus(projectId),
          getFinancialPlan(projectId),
          listProjectScenarios(projectId),
        ]);

        if (cancelled) return;

        // SKUs
        next.skus = skus.length > 0;

        // Financial plan: any non-zero CAPEX or OPEX
        next["financial-plan"] = finPlan.some(
          (fp) => Number(fp.capex) > 0 || Number(fp.opex) > 0,
        );

        // Channels: check first SKU
        if (skus.length > 0) {
          try {
            const channels = await listProjectSkuChannels(skus[0].id);
            if (!cancelled) {
              next.channels = channels.length > 0;
            }
          } catch {
            // non-critical
          }
        }

        // Results: check base scenario
        const baseScenario = scenarios.find((s) => s.type === "base");
        if (baseScenario) {
          try {
            const results = await listScenarioResults(baseScenario.id);
            if (!cancelled) {
              next.results = results.length > 0;
            }
          } catch {
            // 404 = never calculated — leave as false
          }
        }
      } catch {
        // API errors non-critical for progress indicators
      }

      if (!cancelled) {
        setFilled(next);
        setLoading(false);
      }
    }

    setLoading(true);
    void compute();
    return () => { cancelled = true; };
  }, [projectId, project]);

  const groups = useMemo<GroupProgress[]>(() => {
    return SECTION_GROUPS.map((group) => {
      const sections = group.tabs.map((tab) => ({
        key: tab,
        label: SECTION_LABELS[tab],
        filled: filled[tab],
      }));
      return {
        group,
        sections,
        filledCount: sections.filter((s) => s.filled).length,
        totalCount: sections.length,
      };
    });
  }, [filled]);

  return { groups, loading };
}
