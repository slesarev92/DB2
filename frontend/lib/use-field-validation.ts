"use client";

import { useCallback, useState } from "react";

/** Validation rule for a single field. */
export interface FieldRule {
  /** Field is required (non-empty string). */
  required?: boolean;
  /** Minimum numeric value (inclusive). */
  min?: number;
  /** Maximum numeric value (inclusive). */
  max?: number;
  /** Field must parse as a number. */
  numeric?: boolean;
  /** Custom error message override. */
  message?: string;
}

/** Map of field names to their validation rules. */
export type ValidationRules<T extends string = string> = Partial<
  Record<T, FieldRule>
>;

/** Map of field names to their current error message (empty = no error). */
export type FieldErrors<T extends string = string> = Partial<Record<T, string>>;

/** Validate a single field value against a rule. Returns error message or null. */
function validateField(value: string, rule: FieldRule): string | null {
  const trimmed = value.trim();

  if (rule.required && trimmed === "") {
    return rule.message ?? "Обязательное поле";
  }

  // Skip numeric checks if field is empty and not required
  if (trimmed === "") return null;

  if (rule.numeric || rule.min !== undefined || rule.max !== undefined) {
    const num = Number(trimmed.replace(",", "."));
    if (Number.isNaN(num)) {
      return rule.message ?? "Введите число";
    }
    if (rule.min !== undefined && num < rule.min) {
      return rule.message ?? `Минимум ${rule.min}`;
    }
    if (rule.max !== undefined && num > rule.max) {
      return rule.message ?? `Максимум ${rule.max}`;
    }
  }

  return null;
}

/**
 * Lightweight field validation hook.
 *
 * Usage:
 * ```ts
 * const { errors, validateAll, validateOne, clearError } = useFieldValidation(RULES);
 * // On blur: validateOne("field_name", value);
 * // On submit: if (!validateAll(formState)) return;
 * // In JSX: <Input aria-invalid={!!errors.field_name} />
 * //         {errors.field_name && <p className="text-xs text-destructive">{errors.field_name}</p>}
 * ```
 */
export function useFieldValidation<T extends string>(
  rules: ValidationRules<T>,
) {
  const [errors, setErrors] = useState<FieldErrors<T>>({});

  /** Validate one field. Returns error message or null. */
  const validateOne = useCallback(
    (field: T, value: string): string | null => {
      const rule = rules[field];
      if (!rule) return null;
      const err = validateField(value, rule);
      setErrors((prev) => {
        if (prev[field] === (err ?? undefined)) return prev;
        const next = { ...prev };
        if (err) {
          next[field] = err;
        } else {
          delete next[field];
        }
        return next;
      });
      return err;
    },
    [rules],
  );

  /** Validate all fields at once. Returns true if valid. */
  const validateAll = useCallback(
    (values: Record<T, string>): boolean => {
      const next: FieldErrors<T> = {};
      let valid = true;
      for (const [field, rule] of Object.entries(rules) as [T, FieldRule][]) {
        const val = values[field] ?? "";
        const err = validateField(val, rule);
        if (err) {
          next[field] = err;
          valid = false;
        }
      }
      setErrors(next);
      return valid;
    },
    [rules],
  );

  /** Clear error for a specific field (e.g., on focus). */
  const clearError = useCallback((field: T) => {
    setErrors((prev) => {
      if (!(field in prev)) return prev;
      const next = { ...prev };
      delete next[field];
      return next;
    });
  }, []);

  /** Clear all errors. */
  const clearAll = useCallback(() => setErrors({}), []);

  /** Whether there are any validation errors. */
  const hasErrors = Object.keys(errors).length > 0;

  return { errors, hasErrors, validateOne, validateAll, clearError, clearAll };
}
