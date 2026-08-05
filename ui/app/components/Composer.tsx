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
      className="flex shrink-0 items-center gap-3 border border-rule bg-surface p-3 transition-colors focus-within:border-ink"
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
        className="scroll-thin max-h-40 flex-1 resize-none bg-transparent text-sm leading-relaxed outline-none placeholder:text-muted disabled:cursor-not-allowed"
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
      <IconButton
        className="h-11 w-11 bg-ink text-paper hover:bg-ink/80"
        disabled={disabled}
        label="Send"
        type="submit"
      >
        {UpPath}
      </IconButton>
    </form>
  );
}
