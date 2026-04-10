/**
 * Inline field validation error message.
 * Renders nothing if `error` is falsy.
 */
export function FieldError({ error }: { error?: string | null }) {
  if (!error) return null;
  return (
    <p className="mt-0.5 text-xs text-destructive" role="alert">
      {error}
    </p>
  );
}
