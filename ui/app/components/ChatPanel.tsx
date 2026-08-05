"use client";

import { useEffect, useRef } from "react";
import { IconButton, PlusPath } from "@/app/components/IconButton";

export type Message = { from: "you" | "standup"; text: string };

export function ChatPanel({ messages }: { messages: Message[] }) {
  const transcript = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const view = transcript.current;
    if (view) view.scrollTop = view.scrollHeight;
  }, [messages.length]);

  return (
    <div className="relative flex min-h-48 flex-1 flex-col border border-rule">
      <IconButton
        className="absolute top-2 right-3 z-10 h-8 w-8 bg-paper text-muted hover:text-ink"
        label="New conversation"
      >
        {PlusPath}
      </IconButton>

      <div
        ref={transcript}
        className="scroll-thin flex flex-1 flex-col gap-4 overflow-y-auto overscroll-contain scroll-smooth p-4 pt-12"
      >
        {messages.map((message, index) => (
          <div key={index} className="flex flex-col gap-1">
            <span className="label">{message.from}</span>
            <p
              className={`text-sm leading-relaxed ${
                message.from === "you" ? "text-ink" : "text-muted"
              }`}
            >
              {message.text}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
