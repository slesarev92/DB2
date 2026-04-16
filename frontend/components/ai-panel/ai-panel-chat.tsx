"use client";

/**
 * Freeform AI chat — SSE streaming + DB persistence (Phase 7.3).
 *
 * Features:
 * - Messages persisted to DB (chat_conversations + chat_messages)
 * - Conversation list sidebar for switching between past chats
 * - SSE streaming: assistant message appears token-by-token
 * - Input Enter = send, Shift+Enter = newline
 * - Abort controller for canceling streaming
 * - Tier toggle Standard / Deep
 * - "New conversation" and "Delete conversation" buttons
 */

import { MessageSquarePlus, Send, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";

import { useAIPanel } from "./ai-panel-context";

import {
  deleteConversation,
  formatCostRub,
  getConversation,
  listConversations,
  streamChat,
} from "@/lib/ai";
import { cn } from "@/lib/utils";

import type {
  AIChatSSEEvent,
  AIModelTier,
} from "@/types/api";
import type {
  ChatConversationItem,
  ChatMessageItem,
} from "@/lib/ai";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  costRub?: string;
  model?: string;
}

function TypingDots() {
  return (
    <div
      className="flex items-center gap-1 py-1"
      role="status"
      aria-label="AI печатает"
    >
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:-0.2s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:-0.1s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60" />
    </div>
  );
}

export function AIPanelChat() {
  const params = useParams();
  const projectId = params?.id ? Number(params.id) : null;

  const { pushHistory, refreshUsage } = useAIPanel();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [tier, setTier] = useState<AIModelTier>("balanced");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Conversation list
  const [conversations, setConversations] = useState<ChatConversationItem[]>([]);
  const [showList, setShowList] = useState(false);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [messages]);

  // Load conversations list on mount
  useEffect(() => {
    if (projectId === null) return;
    listConversations(projectId)
      .then((data) => {
        setConversations(data);
        // Auto-load last conversation if no active one
        if (data.length > 0 && !conversationId) {
          void loadConversation(data[0].id);
        }
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const loadConversation = useCallback(
    async (convId: number) => {
      if (projectId === null) return;
      try {
        const detail = await getConversation(projectId, convId);
        setConversationId(String(detail.id));
        setMessages(
          detail.messages.map((m: ChatMessageItem) => ({
            role: m.role,
            content: m.content,
            costRub: m.cost_rub ?? undefined,
            model: m.model ?? undefined,
          })),
        );
        setShowList(false);
        setError(null);
      } catch {
        setError("Не удалось загрузить разговор");
      }
    },
    [projectId],
  );

  const refreshConversations = useCallback(() => {
    if (projectId === null) return;
    listConversations(projectId)
      .then(setConversations)
      .catch(() => {});
  }, [projectId]);

  const handleSend = useCallback(async () => {
    if (!input.trim() || streaming || projectId === null) return;

    const question = input.trim();
    setInput("");
    setError(null);

    setMessages((prev) => [...prev, { role: "user", content: question }]);

    setStreaming(true);
    const controller = new AbortController();
    abortRef.current = controller;

    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    let localConvId = conversationId;
    let lastCost = "";
    let lastModel = "";
    const startedAt = Date.now();

    try {
      await streamChat(
        projectId,
        {
          question,
          conversation_id: localConvId,
          tier_override: tier === "balanced" ? null : tier,
        },
        (event: AIChatSSEEvent) => {
          switch (event.type) {
            case "conversation_id":
              localConvId = event.id;
              setConversationId(event.id);
              break;
            case "token":
              setMessages((prev) => {
                const copy = [...prev];
                const last = copy[copy.length - 1];
                if (last?.role === "assistant") {
                  copy[copy.length - 1] = {
                    ...last,
                    content: last.content + event.content,
                  };
                }
                return copy;
              });
              break;
            case "done":
              lastCost = event.cost_rub;
              lastModel = event.model;
              setMessages((prev) => {
                const copy = [...prev];
                const last = copy[copy.length - 1];
                if (last?.role === "assistant") {
                  copy[copy.length - 1] = {
                    ...last,
                    costRub: event.cost_rub,
                    model: event.model,
                  };
                }
                return copy;
              });
              break;
            case "error":
              setError(event.message);
              break;
          }
        },
        { signal: controller.signal },
      );

      if (lastModel) {
        refreshUsage();
        refreshConversations();
        pushHistory({
          timestamp: new Date().toISOString(),
          feature: "freeform_chat",
          model: lastModel,
          cost_rub: lastCost,
          latency_ms: Date.now() - startedAt,
          project_id: projectId,
          project_name: "Проект",
          cached: false,
        });
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        setMessages((prev) => {
          const copy = [...prev];
          const last = copy[copy.length - 1];
          if (last?.role === "assistant") {
            copy[copy.length - 1] = {
              ...last,
              content: last.content + "\n\n[Прервано]",
            };
          }
          return copy;
        });
      } else {
        setError(err instanceof Error ? err.message : "Ошибка");
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }, [input, streaming, projectId, conversationId, tier, pushHistory, refreshUsage, refreshConversations]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        void handleSend();
      }
    },
    [handleSend],
  );

  const handleNewConversation = useCallback(() => {
    setMessages([]);
    setConversationId(null);
    setError(null);
    setShowList(false);
  }, []);

  const handleDeleteConversation = useCallback(
    async (convId: number) => {
      if (projectId === null) return;
      try {
        await deleteConversation(projectId, convId);
        if (conversationId === String(convId)) {
          setMessages([]);
          setConversationId(null);
        }
        refreshConversations();
      } catch {
        setError("Не удалось удалить разговор");
      }
    },
    [projectId, conversationId, refreshConversations],
  );

  if (projectId === null) {
    return (
      <p className="text-xs text-muted-foreground">
        Откройте проект чтобы начать чат.
      </p>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-1 pb-2 text-xs">
        <div className="flex items-center gap-1">
          <div className="flex overflow-hidden rounded-md border">
            <button
              type="button"
              onClick={() => setTier("balanced")}
              className={cn(
                "px-2 py-1",
                tier === "balanced"
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-muted",
              )}
            >
              Обычный
            </button>
            <button
              type="button"
              onClick={() => setTier("heavy")}
              className={cn(
                "px-2 py-1",
                tier === "heavy"
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-muted",
              )}
            >
              Глубокий
            </button>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setShowList((v) => !v)}
            className={cn(
              "rounded px-2 py-1",
              showList ? "bg-muted" : "hover:bg-muted",
              "text-muted-foreground hover:text-foreground",
            )}
            title="История разговоров"
          >
            {conversations.length > 0 ? `${conversations.length}` : "0"}
          </button>
          <button
            type="button"
            onClick={handleNewConversation}
            className="flex items-center gap-1 text-muted-foreground hover:text-foreground"
            title="Новый разговор"
          >
            <MessageSquarePlus className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Conversation list (slide-in) */}
      {showList && (
        <div className="mb-2 max-h-40 space-y-1 overflow-y-auto rounded-md border p-2">
          {conversations.length === 0 && (
            <p className="text-[10px] text-muted-foreground">Нет разговоров</p>
          )}
          {conversations.map((c) => (
            <div
              key={c.id}
              className={cn(
                "flex items-center justify-between rounded px-2 py-1 text-[11px]",
                conversationId === String(c.id)
                  ? "bg-primary/10 font-medium"
                  : "hover:bg-muted cursor-pointer",
              )}
            >
              <button
                type="button"
                className="flex-1 truncate text-left"
                onClick={() => void loadConversation(c.id)}
              >
                {c.title}
              </button>
              <button
                type="button"
                className="ml-1 shrink-0 text-muted-foreground hover:text-destructive"
                onClick={() => void handleDeleteConversation(c.id)}
                title="Удалить"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Messages area */}
      <div
        ref={scrollRef}
        className="flex-1 space-y-3 overflow-y-auto pb-2"
      >
        {messages.length === 0 && (
          <p className="text-xs text-muted-foreground">
            Задайте вопрос по проекту. Например: «Почему NPV
            отрицательный на Y1-Y3?» или «Сравни Base и Conservative».
          </p>
        )}
        {messages.map((msg, idx) => {
          const isLast = idx === messages.length - 1;
          const isPendingAssistant =
            msg.role === "assistant" && streaming && isLast && msg.content === "";
          return (
            <div
              key={idx}
              className={cn(
                "rounded-md p-2 text-xs",
                msg.role === "user"
                  ? "ml-8 bg-primary/10"
                  : "mr-4 bg-muted/50",
              )}
            >
              {isPendingAssistant ? (
                <TypingDots />
              ) : (
                <div className="whitespace-pre-wrap">
                  {msg.content || "..."}
                </div>
              )}
              {msg.role === "assistant" && msg.costRub && (
                <div className="mt-1 text-[10px] text-muted-foreground">
                  {msg.model} · {formatCostRub(msg.costRub)}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Error */}
      {error !== null && (
        <div className="mb-2 rounded-md border border-destructive bg-destructive/5 p-2 text-xs text-destructive">
          {error}
        </div>
      )}

      {/* Input area */}
      <div className="flex items-end gap-2 border-t pt-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Задайте вопрос..."
          rows={2}
          disabled={streaming}
          className="flex-1 resize-none rounded-md border bg-background p-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
        />
        {streaming ? (
          <button
            type="button"
            onClick={() => abortRef.current?.abort()}
            className="rounded-md border border-red-300 p-2 text-red-600 hover:bg-red-50"
            title="Прервать"
          >
            <X className="h-4 w-4" />
          </button>
        ) : (
          <button
            type="button"
            onClick={handleSend}
            disabled={!input.trim()}
            className="rounded-md bg-primary p-2 text-primary-foreground disabled:opacity-50"
            title="Отправить (Enter)"
          >
            <Send className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
}
