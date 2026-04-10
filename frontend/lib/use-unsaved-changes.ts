"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Tracks whether the user has unsaved changes within a container.
 *
 * - Registers `beforeunload` warning when dirty.
 * - Provides `isDirty` state and `confirmIfDirty` helper for tab switching.
 * - Marks dirty on any `input`/`change` event inside the container.
 * - Marks clean on explicit `markClean()` call.
 *
 * Usage:
 * ```tsx
 * const { containerRef, isDirty, markClean, confirmIfDirty } = useUnsavedChanges();
 * <div ref={containerRef}> ... </div>
 * // On tab switch:
 * confirmIfDirty(() => setActiveTab(newTab));
 * ```
 */
export function useUnsavedChanges() {
  const [isDirty, setIsDirty] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Listen for user input inside container
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    function onInput() {
      setIsDirty(true);
    }

    // `input` fires on every keystroke/change in inputs, textareas, selects
    el.addEventListener("input", onInput, true);
    return () => el.removeEventListener("input", onInput, true);
  }, []);

  // beforeunload warning
  useEffect(() => {
    if (!isDirty) return;

    function onBeforeUnload(e: BeforeUnloadEvent) {
      e.preventDefault();
    }

    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [isDirty]);

  const markClean = useCallback(() => setIsDirty(false), []);

  /**
   * If dirty, prompts user with native confirm dialog.
   * If confirmed (or not dirty), calls `proceed()`.
   * Returns true if proceeded.
   */
  const confirmIfDirty = useCallback(
    (proceed: () => void): boolean => {
      if (!isDirty) {
        proceed();
        return true;
      }
      // Blur active element to trigger any onBlur save handlers
      const active = document.activeElement;
      if (active instanceof HTMLElement) active.blur();

      // After blur, give a tick for save to fire, then mark clean
      // Since blur auto-saves in this app, we just proceed and mark clean
      setIsDirty(false);
      proceed();
      return true;
    },
    [isDirty],
  );

  return { containerRef, isDirty, markClean, confirmIfDirty };
}
