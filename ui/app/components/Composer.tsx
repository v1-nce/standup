"use client";

import { IconButton, UpPath } from "@/app/components/IconButton";

export function Composer({ onSend }: { onSend: (request: string) => void }) {
  return (
    <form
      className="flex shrink-0 items-center gap-1 border border-rule p-2 focus-within:border-ink"
      onSubmit={(event) => {
        event.preventDefault();
        const form = event.currentTarget;
        const request = String(new FormData(form).get("request") ?? "").trim();
        if (!request) return;
        onSend(request);
        form.reset();
      }}
    >
      <textarea
        aria-label="What do you need to present?"
        className="max-h-40 flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-relaxed outline-none placeholder:text-muted"
        name="request"
        placeholder="Message Standup…"
        rows={2}
      />
      <IconButton label="Send" type="submit">
        {UpPath}
      </IconButton>
    </form>
  );
}
