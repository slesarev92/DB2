"use client";

import { useEffect } from "react";

/**
 * Keyboard shortcut descriptor.
 * `ctrl` means Ctrl on Windows / Cmd on Mac.
 */
interface Shortcut {
  key: string;
  ctrl?: boolean;
  /** Handler. Return `false` to skip preventDefault. */
  handler: () => void | false;
  /** Only fire when AI panel is open (for Escape). */
  whenAIPanelOpen?: boolean;
}

/**
 * Centralized keyboard shortcuts hook.
 * Register all shortcuts in one place to avoid listener conflicts.
 *
 * Note: Ctrl+K (AI panel) and Ctrl+B (sidebar) are registered in their
 * own components — this hook handles project-page shortcuts only.
 */
export function useKeyboardShortcuts(
  shortcuts: Shortcut[],
  enabled = true,
) {
  useEffect(() => {
    if (!enabled || shortcuts.length === 0) return;

    function onKeyDown(e: KeyboardEvent) {
      // Skip if user is typing in an input/textarea/contenteditable
      const tag = (e.target as HTMLElement)?.tagName;
      const isEditable =
        tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" ||
        (e.target as HTMLElement)?.isContentEditable;

      for (const s of shortcuts) {
        const ctrlMatch = s.ctrl
          ? e.ctrlKey || e.metaKey
          : !e.ctrlKey && !e.metaKey;
        const keyMatch = e.key === s.key;

        if (!ctrlMatch || !keyMatch) continue;

        // Ctrl+shortcuts work even in inputs; plain keys (Escape) don't
        // need the editable check since Escape is safe in inputs too
        if (!s.ctrl && s.key !== "Escape" && isEditable) continue;

        e.preventDefault();
        s.handler();
        return;
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [shortcuts, enabled]);
}
