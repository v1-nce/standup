"use client";

import { useRef, useState } from "react";
import type { Project } from "@/app/api/client";

export function NewProject({ onCreate }: { onCreate: (name: string) => Promise<Project | null> }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const cancelling = useRef(false);

  const submit = (value: string) => {
    const name = value.trim();
    if (!name) return setOpen(false);
    setBusy(true);
    void onCreate(name)
      .then((made) => setOpen(!made))
      .finally(() => setBusy(false));
  };

  const cancel = () => {
    cancelling.current = true;
    setOpen(false);
  };

  if (!open) {
    return (
      <button
        className="press w-full border border-ink bg-paper px-3 py-2 font-mono text-xs font-bold tracking-[0.08em] uppercase shadow-hard enabled:hover:bg-ink enabled:hover:text-paper"
        onClick={() => setOpen(true)}
      >
        + New project
      </button>
    );
  }

  return (
    <input
      autoFocus
      aria-busy={busy}
      aria-label="Name the new project"
      className="field"
      disabled={busy}
      placeholder="Project name"
      onBlur={(event) => {
        if (cancelling.current) {
          cancelling.current = false;
          return;
        }
        if (!busy) submit(event.currentTarget.value);
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter") submit(event.currentTarget.value);
        if (event.key === "Escape") cancel();
      }}
    />
  );
}
