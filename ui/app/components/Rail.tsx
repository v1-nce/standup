"use client";

import type { Project } from "@/app/api/client";
import { IconButton, MenuPath } from "@/app/components/IconButton";
import { ProjectRow } from "@/app/components/ProjectRow";
import type { Projects } from "@/app/hooks/useProjects";

/** The project rail. Pushes the layout on desktop, overlays as a drawer below lg. */
export function Rail({
  onSelect,
  onToggle,
  open,
  projects: { error, projects, remove, rename },
  selectedId,
}: {
  onSelect: (id: string) => void;
  onToggle: () => void;
  open: boolean;
  projects: Projects;
  selectedId: string | null;
}) {
  const confirmDelete = (project: Project) => {
    if (!window.confirm(`Delete ${project.name}? Everything derived from it goes too.`)) return;
    void remove(project.id);
  };

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
        {error && <p className="px-3 py-2 font-mono text-xs text-accent">{error}</p>}
        {!error && projects.length === 0 && (
          <p className="px-3 py-2 font-mono text-xs text-muted">No projects yet</p>
        )}
        {projects.map((project) => (
          <ProjectRow
            key={project.id}
            onDelete={() => confirmDelete(project)}
            onRename={(name) => void rename(project.id, name)}
            onSelect={() => onSelect(project.id)}
            project={project}
            selected={project.id === selectedId}
          />
        ))}
      </nav>
    </aside>
  );
}
