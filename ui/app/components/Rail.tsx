"use client";

import { IconButton, MenuPath } from "@/app/components/IconButton";
import { PROJECTS } from "@/app/utils/placeholder";

/** The project rail. Pushes the layout on desktop, overlays as a drawer below lg. */
export function Rail({ onToggle, open }: { onToggle: () => void; open: boolean }) {
  return (
    <aside
      className={`fixed z-30 flex h-dvh flex-col overflow-hidden border-r border-rule bg-paper transition-[width] duration-200 ease-out lg:static ${
        open ? "w-60" : "w-0"
      }`}
    >
      <div className="flex h-14 shrink-0 items-center gap-1 px-2">
        <IconButton label="Close projects" onClick={onToggle}>
          {MenuPath}
        </IconButton>
        <span className="label pl-1">Projects</span>
      </div>

      <nav className="flex min-w-60 flex-col gap-0.5 px-2">
        {PROJECTS.map((project, index) => (
          <button
            key={project}
            className={`truncate rounded-sm px-3 py-2 text-left font-mono text-sm transition-colors hover:bg-ink/5 ${
              index === 0 ? "text-ink" : "text-muted"
            }`}
          >
            {project}
          </button>
        ))}
      </nav>

      <button className="mt-auto mb-3 min-w-60 px-5 py-2 text-left font-mono text-xs text-muted transition-colors hover:text-ink">
        + Register a project
      </button>
    </aside>
  );
}
