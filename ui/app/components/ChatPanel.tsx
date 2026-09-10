"use client";

import { useEffect, useRef } from "react";
import type { ChatMessage } from "@/app/api/client";
import { IconButton, PlusPath } from "@/app/components/IconButton";

const WHO = { user: "you", assistant: "standup" } as const;

export function ChatPanel({
  messages,
  onAddContext,
  pending,
  projectName = null,
}: {
  messages: ChatMessage[];
  onAddContext?: () => void;
  pending: boolean;
  projectName?: string | null;
}) {
  const transcript = useRef<HTMLDivElement>(null);
  // A `command` entry is what a round actually did, kept so the agent can read it back next turn -
  // not something the person typed or read out loud, so it never becomes a chat bubble.
  const said = messages.filter(
    (message): message is ChatMessage & { role: "user" | "assistant" } =>
      message.role !== "command",
  );

  useEffect(() => {
    const view = transcript.current;
    if (view) view.scrollTop = view.scrollHeight;
  }, [said.length, pending]);

  return (
    <div className="flex min-h-48 flex-1 flex-col border border-ink">
      {projectName && (
        <div className="flex h-10 shrink-0 items-center justify-between gap-2 border-b border-ink px-3">
          <span className="min-w-0 flex-1 truncate font-mono text-sm">{projectName}</span>
          <IconButton
            className="h-8 w-8"
            disabled={!onAddContext}
            label="Add context"
            onClick={onAddContext}
          >
            {PlusPath}
          </IconButton>
        </div>
      )}

      <div
        ref={transcript}
        className="scroll-thin flex flex-1 flex-col gap-4 overflow-y-auto overscroll-contain p-4"
      >
        {said.length === 0 && !pending && (
          <p className="text-sm leading-relaxed text-ink-soft">
            Ask for a deck. Standup reads the repository and decides what belongs on it.
          </p>
        )}

        {said.map((message, index) => (
          <div
            key={index}
            className={`flex flex-col gap-1 border-l-2 pl-3 ${
              message.role === "user" ? "border-ink" : "border-transparent"
            }`}
          >
            <span className="label">{WHO[message.role]}</span>
            <p className={`text-sm leading-relaxed ${message.role === "user" ? "" : "text-ink-soft"}`}>
              {message.content}
            </p>
          </div>
        ))}

        {pending && (
          <div className="flex flex-col gap-1 border-l-2 border-transparent pl-3">
            <span className="label">standup</span>
            <p className="animate-pulse text-sm leading-relaxed text-ink-soft">Working…</p>
          </div>
        )}
      </div>
    </div>
  );
}
