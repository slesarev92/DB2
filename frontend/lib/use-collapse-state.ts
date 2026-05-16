"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

export type AnalysisTabKey =
  | "results"
  | "sensitivity"
  | "pricing"
  | "value-chain"
  | "pnl";

export interface CollapseStateApi {
  /** true если секция раскрыта. Default = true для отсутствующих в LS. */
  isOpen: (sectionId: string) => boolean;
  /** Переключает один section ID. */
  toggle: (sectionId: string) => void;
  /** Все sectionIds → закрыты. */
  collapseAll: () => void;
  /** Удаляет запись таба → всё default open. */
  expandAll: () => void;
  /** true если все sectionIds открыты (для лейбла bulk-кнопки). */
  allOpen: boolean;
}

const STORAGE_KEY = "db2:analysis-collapse:v1";

interface StorageRoot {
  schema_version: 1;
  by_project: Record<
    string, // String(projectId)
    Partial<Record<AnalysisTabKey, Record<string, false>>>
  >;
}

function readStorage(): StorageRoot | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === null) return null;
    const parsed = JSON.parse(raw) as StorageRoot;
    if (parsed.schema_version !== 1) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeStorage(root: StorageRoot): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(root));
  } catch {
    // QuotaExceededError / SecurityError → silent (см. spec §11)
  }
}

/**
 * Хук для управления collapse-state секций одного таба.
 *
 * Persistence: localStorage по ключу `db2:analysis-collapse:v1`.
 * Структура — см. spec §7.1.
 *
 * Хранятся только closed-секции (для compactness). isOpen() возвращает
 * true для всего, чего нет в LS-записи. expandAll() удаляет запись.
 */
export function useCollapseState(
  projectId: number,
  tabKey: AnalysisTabKey,
  sectionIds: readonly string[],
): CollapseStateApi {
  const projectKey = String(projectId);

  // Локально храним set closed-секций как { id: true } для O(1) checks.
  const [closed, setClosed] = useState<Record<string, true>>(() => {
    const root = readStorage();
    const stored = root?.by_project[projectKey]?.[tabKey] ?? {};
    const result: Record<string, true> = {};
    for (const id of Object.keys(stored)) {
      result[id] = true;
    }
    return result;
  });

  // Persist на каждое изменение.
  useEffect(() => {
    const root: StorageRoot = readStorage() ?? {
      schema_version: 1,
      by_project: {},
    };
    const project = root.by_project[projectKey] ?? {};

    if (Object.keys(closed).length === 0) {
      // Все открыты → удаляем запись таба
      delete project[tabKey];
    } else {
      const tabRecord: Record<string, false> = {};
      for (const id of Object.keys(closed)) {
        tabRecord[id] = false;
      }
      project[tabKey] = tabRecord;
    }

    if (Object.keys(project).length === 0) {
      delete root.by_project[projectKey];
    } else {
      root.by_project[projectKey] = project;
    }

    writeStorage(root);
  }, [closed, projectKey, tabKey]);

  const isOpen = useCallback(
    (sectionId: string): boolean => !(sectionId in closed),
    [closed],
  );

  const toggle = useCallback((sectionId: string) => {
    setClosed((prev) => {
      const next = { ...prev };
      if (sectionId in next) {
        delete next[sectionId];
      } else {
        next[sectionId] = true;
      }
      return next;
    });
  }, []);

  const collapseAll = useCallback(() => {
    setClosed(() => {
      const next: Record<string, true> = {};
      for (const id of sectionIds) {
        next[id] = true;
      }
      return next;
    });
  }, [sectionIds]);

  const expandAll = useCallback(() => {
    setClosed({});
  }, []);

  const allOpen = useMemo(() => Object.keys(closed).length === 0, [closed]);

  return { isOpen, toggle, collapseAll, expandAll, allOpen };
}
