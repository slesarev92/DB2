"use client";

import { Tooltip as BaseTooltip } from "@base-ui/react/tooltip";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

type Side = "top" | "right" | "bottom" | "left";

interface TooltipProps {
  /** Текст/узел, показываемый в tooltip-e. Если null/undefined/"" — children рендерятся без обёртки. */
  content: ReactNode;
  children: ReactNode;
  side?: Side;
  /** Доп. tailwind-классы на popup. */
  className?: string;
}

/**
 * Унифицированный tooltip для UI (truncate с полным именем, hint'ы на кнопках).
 *
 * Использует `@base-ui/react/tooltip`. `Root` рендерится автономно; для группо-
 * вой задержки можно обернуть дерево в `<Tooltip.Provider delay={150}>`
 * (base-ui docs).
 */
export function Tooltip({
  content,
  children,
  side = "top",
  className,
}: TooltipProps) {
  if (content === null || content === undefined || content === "") {
    return <>{children}</>;
  }
  return (
    <BaseTooltip.Root>
      <BaseTooltip.Trigger render={<span className="inline-block" />}>
        {children}
      </BaseTooltip.Trigger>
      <BaseTooltip.Portal>
        <BaseTooltip.Positioner side={side} sideOffset={6}>
          <BaseTooltip.Popup
            className={cn(
              "z-50 max-w-xs rounded-md border bg-popover px-2 py-1 text-xs text-popover-foreground shadow-md",
              "data-[state=open]:animate-in data-[state=closed]:animate-out",
              className,
            )}
          >
            {content}
          </BaseTooltip.Popup>
        </BaseTooltip.Positioner>
      </BaseTooltip.Portal>
    </BaseTooltip.Root>
  );
}
