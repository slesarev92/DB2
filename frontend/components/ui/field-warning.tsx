import { AlertTriangle } from "lucide-react";

/**
 * Inline non-blocking warning message (amber, AlertTriangle icon).
 * Symmetric to FieldError. Renders nothing if `warning` is falsy.
 */
export function FieldWarning({ warning }: { warning?: string | null }) {
  if (!warning) return null;
  return (
    <p
      className="mt-0.5 flex items-center gap-1 text-xs text-amber-600"
      role="status"
    >
      <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden="true" />
      <span>{warning}</span>
    </p>
  );
}
