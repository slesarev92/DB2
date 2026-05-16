"use client";

import { Collapsible as CollapsiblePrimitive } from "@base-ui/react/collapsible";
import { ChevronDown } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface CollapsibleSectionProps {
  /** Стабильный ID для localStorage (kebab-case). Не менять без миграции схемы. */
  sectionId: string;
  /** Заголовок секции (string | JSX). Рисуется внутри clickable button. */
  title: ReactNode;
  /** Controlled state: true = раскрыта. */
  isOpen: boolean;
  /** Toggle handler — обычно из useCollapseState. */
  onToggle: () => void;
  /** Контент секции. */
  children: ReactNode;
  /** Доп. классы на корневой div. */
  className?: string;
}

/**
 * Section-level collapse/expand wrapper для табов группы «Анализ».
 *
 * Controlled-компонент: open и onToggle обязательны. Bulk toggle
 * («Свернуть всё / Развернуть всё») требует централизованного state,
 * поэтому defaultOpen намеренно НЕ поддерживается.
 *
 * Анимация — height-transition через CSS var --collapsible-panel-height
 * от base-ui Panel. keepMounted=true: контент остаётся в DOM при collapse
 * (важно для AI-секций с локальным state и кэшем).
 */
export function CollapsibleSection({
  sectionId,
  title,
  isOpen,
  onToggle,
  children,
  className,
}: CollapsibleSectionProps): JSX.Element {
  return (
    <CollapsiblePrimitive.Root
      data-slot="collapsible-section"
      data-section-id={sectionId}
      open={isOpen}
      onOpenChange={(open) => {
        if (open !== isOpen) onToggle();
      }}
      className={cn("space-y-2", className)}
    >
      <CollapsiblePrimitive.Trigger
        data-slot="collapsible-trigger"
        className="group flex w-full items-center justify-between gap-2 rounded-md text-left text-sm font-semibold text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
      >
        <span>{title}</span>
        <ChevronDown
          aria-hidden
          className="size-4 shrink-0 -rotate-90 transition-transform duration-200 group-data-[panel-open]:rotate-0"
        />
      </CollapsiblePrimitive.Trigger>
      <CollapsiblePrimitive.Panel
        data-slot="collapsible-panel"
        keepMounted
        className="h-[var(--collapsible-panel-height)] overflow-hidden transition-[height] duration-150 ease-out data-[starting-style]:h-0 data-[ending-style]:h-0"
      >
        <div className="pt-1">{children}</div>
      </CollapsiblePrimitive.Panel>
    </CollapsiblePrimitive.Root>
  );
}
