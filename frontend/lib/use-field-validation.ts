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
  /**
   * Optional non-blocking warning.
   * Triggers ONLY if no error present and `when(num)` is true.
   * Empty/non-numeric values never produce warnings.
   */
  warn?: {
    when: (n: number) => boolean;
    message: string;
  };
}

/** Map of field names to their validation rules. */
export type ValidationRules<T extends string = string> = Partial<
  Record<T, FieldRule>
>;

/** Map of field names to their current error message (empty = no error). */
export type FieldErrors<T extends string = string> = Partial<Record<T, string>>;

/** Map of field names to their current warning message. */
export type FieldWarnings<T extends string = string> = Partial<
  Record<T, string>
>;

/** Result of validating a single field. */
interface ValidationResult {
  error?: string;
  warning?: string;
}

/** Validate a single field value against a rule. */
function validateField(value: string, rule: FieldRule): ValidationResult {
  const trimmed = value.trim();

  if (rule.required && trimmed === "") {
    return { error: rule.message ?? "Обязательное поле" };
  }

  // Skip numeric checks if field is empty and not required
  if (trimmed === "") return {};

  if (
    rule.numeric ||
    rule.min !== undefined ||
    rule.max !== undefined ||
    rule.warn !== undefined
  ) {
    const num = Number(trimmed.replace(",", "."));
    if (Number.isNaN(num)) {
      return { error: rule.message ?? "Введите число" };
    }
    if (rule.min !== undefined && num < rule.min) {
      return { error: rule.message ?? `Минимум ${rule.min}` };
    }
    if (rule.max !== undefined && num > rule.max) {
      return { error: rule.message ?? `Максимум ${rule.max}` };
    }
    if (rule.warn && rule.warn.when(num)) {
      return { warning: rule.warn.message };
    }
  }

  return {};
}

/**
 * Lightweight field validation hook with non-blocking warnings.
 *
 * Usage:
 * ```ts
 * const { errors, warnings, validateAll, validateOne, clearError } =
 *   useFieldValidation(RULES);
 * // On blur: validateOne("field_name", value);
 * // On submit: if (!validateAll(formState)) return;  // blocks on errors only
 * // In JSX:
 * //   <FieldError error={errors.field_name} />
 * //   <FieldWarning warning={warnings.field_name} />
 * ```
 */
export function useFieldValidation<T extends string>(
  rules: ValidationRules<T>,
) {
  const [errors, setErrors] = useState<FieldErrors<T>>({});
  const [warnings, setWarnings] = useState<FieldWarnings<T>>({});

  /** Validate one field. Returns error message or null. */
  const validateOne = useCallback(
    (field: T, value: string): string | null => {
      const rule = rules[field];
      if (!rule) return null;
      const result = validateField(value, rule);
      setErrors((prev) => {
        if (prev[field] === (result.error ?? undefined)) return prev;
        const next = { ...prev };
        if (result.error) {
          next[field] = result.error;
        } else {
          delete next[field];
        }
        return next;
      });
      setWarnings((prev) => {
        if (prev[field] === (result.warning ?? undefined)) return prev;
        const next = { ...prev };
        if (result.warning) {
          next[field] = result.warning;
        } else {
          delete next[field];
        }
        return next;
      });
      return result.error ?? null;
    },
    [rules],
  );

  /** Validate all fields at once. Returns true if no errors (warnings allowed). */
  const validateAll = useCallback(
    (values: Record<T, string>): boolean => {
      const nextErrors: FieldErrors<T> = {};
      const nextWarnings: FieldWarnings<T> = {};
      let valid = true;
      for (const [field, rule] of Object.entries(rules) as [T, FieldRule][]) {
        const val = values[field] ?? "";
        const result = validateField(val, rule);
        if (result.error) {
          nextErrors[field] = result.error;
          valid = false;
        }
        if (result.warning) {
          nextWarnings[field] = result.warning;
        }
      }
      setErrors(nextErrors);
      setWarnings(nextWarnings);
      return valid;
    },
    [rules],
  );

  /** Clear error for a specific field (e.g., on focus). Warning preserved. */
  const clearError = useCallback((field: T) => {
    setErrors((prev) => {
      if (!(field in prev)) return prev;
      const next = { ...prev };
      delete next[field];
      return next;
    });
  }, []);

  /** Clear all errors and warnings. */
  const clearAll = useCallback(() => {
    setErrors({});
    setWarnings({});
  }, []);

  /** Whether there are any validation errors (warnings do NOT count). */
  const hasErrors = Object.keys(errors).length > 0;

  return {
    errors,
    warnings,
    hasErrors,
    validateOne,
    validateAll,
    clearError,
    clearAll,
  };
}
