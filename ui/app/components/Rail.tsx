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

      <div className="min-w-60 shrink-0 px-3 pb-3">
        <button className="w-full border border-ink px-3 py-2 text-center font-mono text-xs transition-colors hover:bg-ink/5">
          + Register a project
        </button>
      </div>

      <nav className="scroll-thin flex min-h-0 min-w-60 flex-1 flex-col gap-0.5 overflow-y-auto px-2 pb-3">
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
    </aside>
  );
}
