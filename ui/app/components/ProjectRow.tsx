"use client";

import { useRef, useState } from "react";
import type { Project } from "@/app/api/client";
import { IconButton, PencilPath, TrashPath } from "@/app/components/IconButton";

const ACTION = "h-8 w-8 text-muted opacity-0 group-hover:opacity-100 focus-visible:opacity-100";

/** One project in the rail: pick it, rename it in place, or delete it. */
export function ProjectRow({
  onDelete,
  onRename,
  onSelect,
  project,
  selected,
}: {
  onDelete: () => void;
  onRename: (name: string) => void;
  onSelect: () => void;
  project: Project;
  selected: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const cancelling = useRef(false);

  const commit = (value: string) => {
    const name = value.trim();
    if (name && name !== project.name) onRename(name);
    setEditing(false);
  };

  const cancel = () => {
    cancelling.current = true;
    setEditing(false);
  };

  if (editing) {
    return (
      <input
        autoFocus
        aria-label={`Rename ${project.name}`}
        className="field"
        defaultValue={project.name}
        onBlur={(event) => {
          if (cancelling.current) {
            cancelling.current = false;
            return;
          }
          commit(event.currentTarget.value);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") commit(event.currentTarget.value);
          if (event.key === "Escape") cancel();
        }}
      />
    );
  }

  return (
    <div className={`group flex items-center rounded-sm ${selected ? "bg-ink/5" : ""}`}>
      <button
        className={`min-w-0 flex-1 truncate px-3 py-2 text-left font-mono text-sm ${
          selected ? "text-ink" : "text-muted"
        }`}
        onClick={onSelect}
      >
        {project.name}
      </button>

      <IconButton
        className={`${ACTION} hover:text-ink`}
        label={`Rename ${project.name}`}
        onClick={() => setEditing(true)}
      >
        {PencilPath}
      </IconButton>
      <IconButton
        className={`${ACTION} hover:text-accent`}
        label={`Delete ${project.name}`}
        onClick={onDelete}
      >
        {TrashPath}
      </IconButton>
    </div>
  );
}
