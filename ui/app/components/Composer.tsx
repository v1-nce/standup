"use client";

import { IconButton, UpPath } from "@/app/components/IconButton";

export function Composer({
  disabled = false,
  onSend,
}: {
  disabled?: boolean;
  onSend: (request: string) => void;
}) {
  return (
    <form
      className="flex shrink-0 items-end gap-4 border border-ink p-3"
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
        className="scroll-thin max-h-40 min-h-11 flex-1 resize-none border-b border-ink bg-transparent text-sm leading-relaxed outline-none transition-colors placeholder:text-ink-faint focus:border-b-2 disabled:cursor-not-allowed disabled:opacity-40"
        disabled={disabled}
        name="request"
        onKeyDown={(event) => {
          if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
          event.preventDefault();
          event.currentTarget.form?.requestSubmit();
        }}
        placeholder="Message Standup…"
        rows={2}
      />
      <IconButton disabled={disabled} label="Send" size="lg" type="submit" variant="ink">
        {UpPath}
      </IconButton>
    </form>
  );
}
