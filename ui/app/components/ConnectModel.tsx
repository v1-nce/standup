"use client";

import { useState } from "react";

/** First-run model setup: paste one key; Standup detects the provider and writes ~/.standup/.env. */
export function ConnectModel({
  error,
  onConnect,
}: {
  error: string | null;
  onConnect: (key: string) => Promise<boolean>;
}) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    const ok = await onConnect(key.trim());
    setBusy(false);
    if (ok) setKey("");
  };

  return (
    <div className="flex min-h-dvh items-center justify-center p-4">
      <form
        className="w-full max-w-md border border-ink bg-paper p-6 shadow-hard-lg"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <h1 className="label mb-2">Connect a model</h1>
        <p className="mb-4 font-mono text-xs text-ink-soft">
          Paste one API key. Standup detects the provider and saves it — no .env file to copy.
        </p>
        <input
          autoFocus
          aria-label="Model API key"
          className="field mb-4"
          disabled={busy}
          onChange={(event) => setKey(event.target.value)}
          placeholder="sk-ant-… / AIza… / sk-…"
          type="password"
          value={key}
        />
        <button
          className="press w-full border border-ink bg-paper px-3 py-2 font-mono text-xs font-bold tracking-[0.08em] uppercase shadow-hard enabled:hover:bg-ink enabled:hover:text-paper"
          disabled={busy || !key.trim()}
          type="submit"
        >
          {busy ? "Connecting…" : "Connect"}
        </button>
        {error && (
          <p className="stamp-ink mt-3 px-3 py-2 font-mono text-xs" role="alert">
            {error}
          </p>
        )}
      </form>
    </div>
  );
}
