"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";
import type { GroupProgress, TabValue } from "@/lib/project-nav-context";

interface ProjectSidebarNavProps {
  projectName: string;
  activeTab: TabValue;
  onTabChange: (tab: TabValue) => void;
  groups: GroupProgress[];
  collapsed: boolean;
}

/** Progress dots: ●●○ */
function ProgressDots({ filled, total }: { filled: number; total: number }) {
  return (
    <span className="ml-auto flex gap-0.5">
      {Array.from({ length: total }, (_, i) => (
        <span
          key={i}
          className={cn(
            "inline-block h-1.5 w-1.5 rounded-full",
            i < filled ? "bg-foreground" : "border border-muted-foreground/50",
          )}
        />
      ))}
    </span>
  );
}

/**
 * Project-specific sidebar navigation.
 *
 * Shows 5 numbered groups with progress indicators.
 * Each group expands to show section items.
 * Active section is highlighted.
 */
export function ProjectSidebarNav({
  projectName,
  activeTab,
  onTabChange,
  groups,
  collapsed,
}: ProjectSidebarNavProps) {
  // Which group contains the active tab?
  const activeGroupKey = groups.find((g) =>
    g.sections.some((s) => s.key === activeTab),
  )?.group.key;

  if (collapsed) {
    return (
      <nav className="flex flex-1 flex-col items-center gap-1 px-1 py-4">
        <Link
          href="/projects"
          className="mb-2 flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-sidebar-accent/50"
          title="Все проекты"
        >
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div className="mb-2 h-px w-6 bg-border" />
        {groups.map((g) => {
          const isActive = g.group.key === activeGroupKey;
          const firstTab = g.sections[0].key;
          return (
            <button
              key={g.group.key}
              onClick={() => onTabChange(firstTab)}
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-md text-sm transition-colors",
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-muted-foreground hover:bg-sidebar-accent/50",
              )}
              title={`${g.group.label} (${g.filledCount}/${g.totalCount})`}
            >
              {g.group.number}
            </button>
          );
        })}
      </nav>
    );
  }

  return (
    <nav className="flex flex-1 flex-col overflow-y-auto px-2 py-4">
      {/* Back link */}
      <Link
        href="/projects"
        className="mb-2 flex items-center gap-2 rounded-md px-3 py-1.5 text-xs text-muted-foreground hover:bg-sidebar-accent/50"
      >
        <ArrowLeft className="h-3 w-3" />
        Все проекты
      </Link>

      {/* Project name */}
      <div className="mb-3 border-b px-3 pb-3">
        <p className="truncate text-sm font-medium" title={projectName}>
          {projectName}
        </p>
      </div>

      {/* Groups + sections */}
      {groups.map((g) => (
        <div key={g.group.key} className="mb-2">
          {/* Group header */}
          <div className="flex items-center gap-1.5 px-3 py-1">
            <span className="text-xs text-muted-foreground">
              {g.group.number}
            </span>
            <span className="text-xs font-medium text-muted-foreground">
              {g.group.label}
            </span>
            <ProgressDots filled={g.filledCount} total={g.totalCount} />
          </div>

          {/* Section items */}
          {g.sections.map((s) => {
            const isActive = s.key === activeTab;
            return (
              <button
                key={s.key}
                onClick={() => onTabChange(s.key)}
                className={cn(
                  "flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-sm transition-colors",
                  "pl-8", // indent under group header
                  isActive
                    ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                    : "text-foreground/70 hover:bg-sidebar-accent/50",
                )}
              >
                <span
                  className={cn(
                    "inline-block h-1.5 w-1.5 shrink-0 rounded-full",
                    s.filled
                      ? "bg-foreground"
                      : "border border-muted-foreground/40",
                  )}
                />
                {s.label}
              </button>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
