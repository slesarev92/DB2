"use client";

import { Popover } from "@base-ui/react/popover";
import { Info } from "lucide-react";

import { PARAMETER_HELP, type ParameterHelp } from "@/lib/parameter-help";
import { cn } from "@/lib/utils";

interface HelpButtonProps {
  /**
   * Параметр справки. Если строка — ищется в PARAMETER_HELP map.
   * Если объект — используется напрямую (для ad-hoc helps).
   */
  help: string | ParameterHelp;
  /**
   * Tailwind-классы для внешнего вида кнопки. По умолчанию — маленькая
   * инлайн-иконка рядом с label.
   */
  className?: string;
  /**
   * Aria-label для screen readers. По умолчанию "Справка по полю {title}".
   */
  ariaLabel?: string;
}

/**
 * Небольшой ? значок рядом с label поля. По клику открывает popover
 * с описанием параметра: что он делает, на что влияет, формула, единицы,
 * default-значение, ссылка на Excel эталон.
 *
 * Источник данных: `frontend/lib/parameter-help.ts` — инлайн TypeScript map.
 * Выбор inline TS над markdown на сервере: нет нового backend endpoint,
 * collocated с UI, type-safe, bundled с фронтом (runtime fetch не нужен).
 */
export function HelpButton({
  help,
  className,
  ariaLabel,
}: HelpButtonProps) {
  const entry: ParameterHelp | null =
    typeof help === "string" ? PARAMETER_HELP[help] ?? null : help;

  if (entry === null) {
    if (process.env.NODE_ENV !== "production") {
      // dev-warning: help ID не найден
      // eslint-disable-next-line no-console
      console.warn(`[HelpButton] unknown help id: "${help}"`);
    }
    return null;
  }

  return (
    <Popover.Root>
      <Popover.Trigger
        className={cn(
          "inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full",
          "text-muted-foreground/70 transition-colors",
          "hover:text-foreground focus-visible:text-foreground",
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          "align-middle",
          className,
        )}
        aria-label={ariaLabel ?? `Справка: ${entry.title}`}
      >
        <Info className="h-3.5 w-3.5" strokeWidth={2} />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner sideOffset={6} className="z-50">
          <Popover.Popup
            className={cn(
              "max-w-sm rounded-md border bg-popover p-3 text-popover-foreground shadow-md",
              "text-sm outline-none",
              "data-[state=open]:animate-in data-[state=closed]:animate-out",
            )}
          >
            <HelpContent entry={entry} />
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  );
}


function HelpContent({ entry }: { entry: ParameterHelp }) {
  return (
    <div className="space-y-2">
      <div className="font-semibold text-sm leading-tight">{entry.title}</div>
      <p className="text-xs text-muted-foreground leading-snug">
        {entry.description}
      </p>
      {entry.impact !== undefined && (
        <div className="text-xs">
          <span className="font-medium text-foreground">Влияет на: </span>
          <span className="text-muted-foreground">{entry.impact}</span>
        </div>
      )}
      {entry.formula !== undefined && (
        <div className="text-xs">
          <div className="font-medium mb-0.5">Формула:</div>
          <code className="block whitespace-pre-wrap rounded bg-muted px-2 py-1 text-[11px] font-mono">
            {entry.formula}
          </code>
        </div>
      )}
      {(entry.range !== undefined ||
        entry.defaultValue !== undefined ||
        entry.units !== undefined) && (
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] pt-1 border-t">
          {entry.units !== undefined && (
            <div>
              <span className="text-muted-foreground">Ед: </span>
              <span className="font-medium">{entry.units}</span>
            </div>
          )}
          {entry.range !== undefined && (
            <div>
              <span className="text-muted-foreground">Диапазон: </span>
              <span className="font-medium">{entry.range}</span>
            </div>
          )}
          {entry.defaultValue !== undefined && (
            <div>
              <span className="text-muted-foreground">Default: </span>
              <span className="font-medium">{entry.defaultValue}</span>
            </div>
          )}
        </div>
      )}
      {entry.excelRef !== undefined && (
        <div className="text-[11px] text-muted-foreground pt-0.5">
          Excel эталон: {entry.excelRef}
        </div>
      )}
    </div>
  );
}
