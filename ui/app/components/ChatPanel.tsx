"use client";

import { useEffect, useRef } from "react";
import type { ChatMessage } from "@/app/api/client";
import { IconButton, PlusPath } from "@/app/components/IconButton";

const WHO = { user: "you", assistant: "standup" } as const;

export function ChatPanel({
  messages,
  pending,
}: {
  messages: ChatMessage[];
  pending: boolean;
}) {
  const transcript = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const view = transcript.current;
    if (view) view.scrollTop = view.scrollHeight;
  }, [messages.length, pending]);

  return (
    <div className="relative flex min-h-48 flex-1 flex-col border border-rule">
      <IconButton
        className="absolute top-2 right-3 z-10 h-8 w-8 bg-paper text-muted"
        disabled
        label="Add context — not built yet"
      >
        {PlusPath}
      </IconButton>

      <div
        ref={transcript}
        className="scroll-thin flex flex-1 flex-col gap-4 overflow-y-auto overscroll-contain scroll-smooth p-4 pt-12"
      >
        {messages.length === 0 && !pending && (
          <p className="text-sm leading-relaxed text-muted">
            Ask for a deck. Standup reads the repository and decides what belongs on it.
          </p>
        )}

        {messages.map((message, index) => (
          <div key={index} className="flex flex-col gap-1">
            <span className="label">{WHO[message.role]}</span>
            <p
              className={`text-sm leading-relaxed ${
                message.role === "user" ? "text-ink" : "text-muted"
              }`}
            >
              {message.content}
            </p>
          </div>
        ))}

        {pending && (
          <div className="flex flex-col gap-1">
            <span className="label">standup</span>
            <p className="animate-pulse text-sm leading-relaxed text-muted">Working…</p>
          </div>
        )}
      </div>
    </div>
  );
}
