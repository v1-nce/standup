"use client";

import { useState } from "react";
import type { Project } from "@/app/api/client";
import { useInlineEdit } from "@/app/hooks/useInlineEdit";

export function NewProject({ onCreate }: { onCreate: (name: string) => Promise<Project | null> }) {
  const [busy, setBusy] = useState(false);
  const { editing, fieldProps, open } = useInlineEdit((name) => {
    setBusy(true);
    return onCreate(name)
      .then((made) => made !== null)
      .finally(() => setBusy(false));
  });

  if (!editing) {
    return (
      <button
        className="press w-full border border-ink bg-paper px-3 py-2 font-mono text-xs font-bold tracking-[0.08em] uppercase shadow-hard enabled:hover:bg-ink enabled:hover:text-paper"
        onClick={open}
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
      {...fieldProps}
    />
  );
}
