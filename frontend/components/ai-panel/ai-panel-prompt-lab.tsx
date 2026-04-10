"use client";

/**
 * A/B Prompt Lab (dev-only, Phase 7.2 решение #10).
 *
 * Позволяет итерировать промпты без перезапуска backend'а:
 * 1. Два textarea — версия A и версия B системного промпта
 * 2. "Run both" запускает explain-kpi на текущем контексте с override
 * 3. Side-by-side результаты + cost каждой версии
 *
 * В 7.2 — UI skeleton без реальных вызовов. Для реального запуска
 * нужен debug-endpoint (`POST /api/projects/{id}/ai/explain-kpi/debug`
 * с `prompt_override` в body), который добавим в 7.3 вместе с
 * sensitivity interpretation когда будет нужен для следующей итерации
 * промптов. Сейчас — заглушка, но скрывается в production.
 */

import { useState } from "react";

export function AIPanelPromptLab() {
  const [promptA, setPromptA] = useState("");
  const [promptB, setPromptB] = useState("");

  return (
    <div className="space-y-3 text-xs">
      <div className="rounded-md border border-amber-300 bg-amber-50 p-2 text-[11px] text-amber-900">
        🧪 Dev-only. Невидимо в production. Реальный debug endpoint
        добавится в 7.3 — сейчас только UI skeleton.
      </div>

      <section>
        <label
          htmlFor="prompt-a"
          className="block font-medium text-muted-foreground"
        >
          Версия A
        </label>
        <textarea
          id="prompt-a"
          value={promptA}
          onChange={(e) => setPromptA(e.target.value)}
          rows={6}
          className="mt-1 w-full rounded-md border bg-background p-2 font-mono text-[10px]"
          placeholder="system prompt version A..."
        />
      </section>

      <section>
        <label
          htmlFor="prompt-b"
          className="block font-medium text-muted-foreground"
        >
          Версия B
        </label>
        <textarea
          id="prompt-b"
          value={promptB}
          onChange={(e) => setPromptB(e.target.value)}
          rows={6}
          className="mt-1 w-full rounded-md border bg-background p-2 font-mono text-[10px]"
          placeholder="system prompt version B..."
        />
      </section>

      <button
        type="button"
        disabled
        className="w-full rounded-md bg-primary px-3 py-2 text-xs font-medium text-primary-foreground opacity-50"
      >
        Run both (доступно в 7.3)
      </button>

      <p className="text-muted-foreground">
        Когда debug endpoint подключится — здесь будут side-by-side
        результаты с confidence/cost каждой версии промпта.
      </p>
    </div>
  );
}
