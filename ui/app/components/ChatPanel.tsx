"use client";

import { IconButton, PlusPath } from "@/app/components/IconButton";

export type Message = { from: "you" | "standup"; text: string };

export function ChatPanel({ messages }: { messages: Message[] }) {
  return (
    <div className="relative flex min-h-48 flex-1 flex-col gap-4 overflow-y-auto border border-rule p-4 pt-14">
      <IconButton className="absolute top-2 right-2 bg-paper" label="New conversation">
        {PlusPath}
      </IconButton>

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
  );
}
