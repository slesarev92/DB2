"use client";

import { useCallback, useMemo, useState } from "react";

export type SortDirection = "asc" | "desc";

export interface SortState<K extends string = string> {
  column: K | null;
  direction: SortDirection;
}

/**
 * Accessor: either a key of T, or a function returning a sortable value.
 * Numbers sort numerically, strings sort via localeCompare("ru").
 */
export type ColumnAccessor<T, K extends string = string> =
  | keyof T
  | ((item: T, key: K) => string | number | null);

export interface SortableColumn<T, K extends string = string> {
  key: K;
  accessor: ColumnAccessor<T, K>;
}

/**
 * Generic sorting hook for CRUD tables.
 *
 * Usage:
 * ```ts
 * const { sorted, sortState, toggleSort, SortHeader } = useSortableTable(items, columns);
 * // In <TableHead>:
 * <SortHeader column="name">Название</SortHeader>
 * // Table body uses `sorted` instead of raw items.
 * ```
 */
export function useSortableTable<T, K extends string = string>(
  items: T[],
  columns: SortableColumn<T, K>[],
) {
  const [sortState, setSortState] = useState<SortState<K>>({
    column: null,
    direction: "asc",
  });

  const toggleSort = useCallback(
    (column: K) => {
      setSortState((prev) => {
        if (prev.column === column) {
          // Cycle: asc → desc → none
          if (prev.direction === "asc") {
            return { column, direction: "desc" };
          }
          return { column: null, direction: "asc" };
        }
        return { column, direction: "asc" };
      });
    },
    [],
  );

  const columnMap = useMemo(() => {
    const m = new Map<K, ColumnAccessor<T, K>>();
    for (const c of columns) {
      m.set(c.key, c.accessor);
    }
    return m;
  }, [columns]);

  const sorted = useMemo(() => {
    if (sortState.column === null) return items;

    const accessor = columnMap.get(sortState.column);
    if (!accessor) return items;

    const getValue = (item: T): string | number | null => {
      if (typeof accessor === "function") {
        return accessor(item, sortState.column!);
      }
      const val = item[accessor as keyof T];
      if (val === null || val === undefined) return null;
      if (typeof val === "number") return val;
      return String(val);
    };

    const dir = sortState.direction === "asc" ? 1 : -1;

    return [...items].sort((a, b) => {
      const va = getValue(a);
      const vb = getValue(b);

      // nulls last
      if (va === null && vb === null) return 0;
      if (va === null) return 1;
      if (vb === null) return -1;

      if (typeof va === "number" && typeof vb === "number") {
        return (va - vb) * dir;
      }

      return String(va).localeCompare(String(vb), "ru") * dir;
    });
  }, [items, sortState, columnMap]);

  return { sorted, sortState, toggleSort };
}

/**
 * CSS class for sort indicator arrow in table header.
 * Returns "" (no sort), "sort-asc", or "sort-desc".
 */
export function sortIndicator<K extends string>(
  state: SortState<K>,
  column: K,
): string {
  if (state.column !== column) return "";
  return state.direction === "asc" ? " \u2191" : " \u2193";
}
