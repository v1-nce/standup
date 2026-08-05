"use client";

import { useState } from "react";
import type { Project } from "@/app/api/client";

export function NewProject({ onCreate }: { onCreate: (name: string) => Promise<Project | null> }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = (value: string) => {
    const name = value.trim();
    if (!name) return setOpen(false);
    setBusy(true);
    void onCreate(name).then((made) => {
      setBusy(false);
      setOpen(!made);
    });
  };

  if (!open) {
    return (
      <button
        className="w-full border border-ink px-3 py-2 text-center font-mono text-xs transition-colors hover:bg-ink/5"
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
      onKeyDown={(event) => {
        if (event.key === "Enter") submit(event.currentTarget.value);
        if (event.key === "Escape") setOpen(false);
      }}
    />
  );
}
