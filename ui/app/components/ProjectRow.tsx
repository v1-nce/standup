"use client";

import type { Project } from "@/app/api/client";
import { IconButton, PencilPath, TrashPath } from "@/app/components/IconButton";
import { useInlineEdit } from "@/app/hooks/useInlineEdit";

const ACTION = "opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100";

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
  const { editing, fieldProps, open } = useInlineEdit((name) => {
    if (name !== project.name) onRename(name);
  });

  if (editing) {
    return (
      <input
        autoFocus
        aria-label={`Rename ${project.name}`}
        className="field"
        defaultValue={project.name}
        {...fieldProps}
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
        onClick={open}
        size="sm"
      >
        {PencilPath}
      </IconButton>
      <IconButton
        className={ACTION}
        label={`Delete ${project.name}`}
        onClick={onDelete}
        size="sm"
      >
        {TrashPath}
      </IconButton>
    </div>
  );
}
