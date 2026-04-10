"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError } from "@/lib/api";
import { listProjectSkuChannels } from "@/lib/channels";
import {
  listChannelDeltas,
  listProjectScenarios,
  putChannelDeltas,
} from "@/lib/scenarios";
import { listProjectSkus } from "@/lib/skus";

import type {
  ChannelDeltaItem,
  ProjectSKUChannelRead,
  ScenarioRead,
} from "@/types/api";

interface ChannelDeltasEditorProps {
  projectId: number;
}

interface DeltaDraft {
  delta_nd: string;
  delta_offtake: string;
}

function pctToFraction(s: string): string {
  const num = Number(s.trim().replace(",", "."));
  if (Number.isNaN(num)) return "0";
  return (num / 100).toString();
}

function fractionToPct(s: string): string {
  const num = Number(s);
  if (Number.isNaN(num)) return "0";
  const pct = num * 100;
  return pct === 0 ? "" : pct.toString();
}

/**
 * Редактор per-channel delta overrides (B-06).
 *
 * Таблица: строки = каналы проекта, колонки = ND% / Offtake% per scenario
 * (только Conservative + Aggressive). Пустые поля → fallback к глобальной
 * дельте сценария.
 */
export function ChannelDeltasEditor({
  projectId,
}: ChannelDeltasEditorProps) {
  const [channels, setChannels] = useState<ProjectSKUChannelRead[]>([]);
  const [scenarios, setScenarios] = useState<ScenarioRead[]>([]);
  // scenarioId → { pskChannelId → DeltaDraft }
  const [drafts, setDrafts] = useState<
    Record<number, Record<number, DeltaDraft>>
  >({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<Date | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // Load all PSK channels for the project
        const psks = await listProjectSkus(projectId);
        if (cancelled) return;
        const allChannels: ProjectSKUChannelRead[] = [];
        for (const psk of psks) {
          const chs = await listProjectSkuChannels(psk.id);
          if (cancelled) return;
          allChannels.push(...chs);
        }
        setChannels(allChannels);

        const sList = await listProjectScenarios(projectId);
        if (cancelled) return;
        const nonBase = sList.filter((s) => s.type !== "base");
        setScenarios(nonBase);

        const newDrafts: Record<number, Record<number, DeltaDraft>> = {};
        for (const s of nonBase) {
          const items = await listChannelDeltas(s.id);
          if (cancelled) return;
          const map: Record<number, DeltaDraft> = {};
          for (const ch of allChannels) {
            const existing = items.find(
              (i) => i.psk_channel_id === ch.id,
            );
            map[ch.id] = {
              delta_nd: existing ? fractionToPct(existing.delta_nd) : "",
              delta_offtake: existing
                ? fractionToPct(existing.delta_offtake)
                : "",
            };
          }
          newDrafts[s.id] = map;
        }
        setDrafts(newDrafts);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiError
              ? err.detail ?? err.message
              : "Ошибка загрузки",
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  function updateDraft(
    scenarioId: number,
    pscId: number,
    field: keyof DeltaDraft,
    value: string,
  ) {
    setDrafts((prev) => ({
      ...prev,
      [scenarioId]: {
        ...prev[scenarioId],
        [pscId]: {
          ...(prev[scenarioId]?.[pscId] ?? {
            delta_nd: "",
            delta_offtake: "",
          }),
          [field]: value,
        },
      },
    }));
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      for (const s of scenarios) {
        const chMap = drafts[s.id] ?? {};
        const items: ChannelDeltaItem[] = [];
        for (const ch of channels) {
          const draft = chMap[ch.id];
          if (!draft) continue;
          // Only include if user set non-empty values
          if (draft.delta_nd === "" && draft.delta_offtake === "") continue;
          items.push({
            psk_channel_id: ch.id,
            delta_nd: pctToFraction(draft.delta_nd || "0"),
            delta_offtake: pctToFraction(draft.delta_offtake || "0"),
          });
        }
        await putChannelDeltas(s.id, { items });
      }
      setSavedAt(new Date());
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.detail ?? err.message
          : "Ошибка сохранения",
      );
    } finally {
      setSaving(false);
    }
  }

  if (channels.length === 0) return null;

  const SCENARIO_LABELS: Record<string, string> = {
    conservative: "Conservative",
    aggressive: "Aggressive",
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div>
            <CardTitle className="text-base">
              Per-channel дельты (B-06)
            </CardTitle>
            <CardDescription>
              Индивидуальные отклонения ND/offtake для каждого канала.
              Пустые поля = используется глобальная дельта сценария.
              Сохранённые значения применяются при пересчёте.
            </CardDescription>
          </div>
          <div className="flex items-center gap-3">
            {savedAt !== null && !saving && error === null && (
              <span className="text-xs text-muted-foreground">
                Сохранено {savedAt.toLocaleTimeString("ru-RU")}
              </span>
            )}
            <Button size="sm" onClick={handleSave} disabled={saving}>
              {saving ? "Сохранение..." : "Сохранить дельты"}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {error !== null && (
          <p className="mb-3 text-sm text-destructive" role="alert">
            {error}
          </p>
        )}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Канал</TableHead>
              {scenarios.map((s) => (
                <TableHead key={s.id} colSpan={2} className="text-center">
                  {SCENARIO_LABELS[s.type] ?? s.type}
                </TableHead>
              ))}
            </TableRow>
            <TableRow>
              <TableHead />
              {scenarios.map((s) => (
                <>
                  <TableHead
                    key={`${s.id}-nd`}
                    className="text-xs text-muted-foreground"
                  >
                    ND, %
                  </TableHead>
                  <TableHead
                    key={`${s.id}-off`}
                    className="text-xs text-muted-foreground"
                  >
                    Offtake, %
                  </TableHead>
                </>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {channels.map((ch) => (
              <TableRow key={ch.id}>
                <TableCell className="font-medium text-sm">
                  {ch.channel.code}
                </TableCell>
                {scenarios.map((s) => {
                  const draft = drafts[s.id]?.[ch.id];
                  return (
                    <>
                      <TableCell key={`${s.id}-${ch.id}-nd`}>
                        <Input
                          type="number"
                          step="0.1"
                          placeholder="—"
                          value={draft?.delta_nd ?? ""}
                          onChange={(e) =>
                            updateDraft(
                              s.id,
                              ch.id,
                              "delta_nd",
                              e.target.value,
                            )
                          }
                          disabled={saving}
                          className="w-20 text-sm"
                        />
                      </TableCell>
                      <TableCell key={`${s.id}-${ch.id}-off`}>
                        <Input
                          type="number"
                          step="0.1"
                          placeholder="—"
                          value={draft?.delta_offtake ?? ""}
                          onChange={(e) =>
                            updateDraft(
                              s.id,
                              ch.id,
                              "delta_offtake",
                              e.target.value,
                            )
                          }
                          disabled={saving}
                          className="w-20 text-sm"
                        />
                      </TableCell>
                    </>
                  );
                })}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
