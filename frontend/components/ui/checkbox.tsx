"use client";

import { Checkbox as CheckboxPrimitive } from "@base-ui/react/checkbox";
import { Check } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * C #16: shadcn-style Checkbox обёртка над `@base-ui/react/checkbox`.
 *
 * API похож на shadcn (`checked`, `onCheckedChange`, `disabled`, `id`).
 * Visual — square + Check icon когда checked.
 */
interface CheckboxProps {
  id?: string;
  checked?: boolean;
  defaultChecked?: boolean;
  disabled?: boolean;
  onCheckedChange?: (checked: boolean) => void;
  className?: string;
  "aria-label"?: string;
}

export function Checkbox({
  id,
  checked,
  defaultChecked,
  disabled,
  onCheckedChange,
  className,
  "aria-label": ariaLabel,
}: CheckboxProps): JSX.Element {
  return (
    <CheckboxPrimitive.Root
      id={id}
      checked={checked}
      defaultChecked={defaultChecked}
      disabled={disabled}
      onCheckedChange={(value) => {
        if (onCheckedChange) onCheckedChange(value === true);
      }}
      aria-label={ariaLabel}
      className={cn(
        "peer inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-sm border border-input bg-transparent shadow-sm outline-none transition-colors",
        "data-[checked]:border-primary data-[checked]:bg-primary data-[checked]:text-primary-foreground",
        "focus-visible:ring-2 focus-visible:ring-ring/50",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
    >
      <CheckboxPrimitive.Indicator className="flex items-center justify-center text-current">
        <Check className="size-3" strokeWidth={3} aria-hidden />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}
