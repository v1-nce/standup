"use client";

import { useRef, useState } from "react";
import type { Project } from "@/app/api/client";
import { IconButton, PencilPath, TrashPath } from "@/app/components/IconButton";

const ACTION = "h-8 w-8 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100";

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
    <div className="group flex items-center">
      <button
        className="flex min-w-0 flex-1 items-center gap-2.5 px-2 py-1.5 text-left"
        onClick={onSelect}
      >
        <span
          aria-hidden
          className={`inline-block h-2.5 w-2.5 shrink-0 border border-ink ${
            selected ? "bg-ink" : ""
          }`}
        />
        <span
          className={`min-w-0 flex-1 truncate font-mono text-sm ${
            selected ? "font-bold" : ""
          }`}
        >
          {project.name}
        </span>
      </button>

      <IconButton
        className={ACTION}
        label={`Rename ${project.name}`}
        onClick={() => setEditing(true)}
      >
        {PencilPath}
      </IconButton>
      <IconButton
        className={ACTION}
        label={`Delete ${project.name}`}
        onClick={onDelete}
      >
        {TrashPath}
      </IconButton>
    </div>
  );
}
