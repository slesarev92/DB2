"use client";

/**
 * Freeform chat tab — полная реализация в Phase 7.3 (SSE streaming).
 *
 * В 7.2 — заглушка с описанием будущего функционала. Tab видимый,
 * чтобы пользователь знал что он будет, но нажать ничего нельзя.
 */

export function AIPanelChat() {
  return (
    <div className="space-y-3 text-xs text-muted-foreground">
      <p>
        Свободный чат по проекту появится в Phase 7.3 — можно будет
        задавать произвольные вопросы вроде «почему в Aggressive IRR ниже
        чем в Base?» с SSE streaming ответа.
      </p>
      <p>Пока доступны inline ✨ кнопки на вкладках результатов.</p>
    </div>
  );
}
