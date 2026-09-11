"use client";

import { useState } from "react";
import type { Project } from "@/app/api/client";
import { ConfirmDialog } from "@/app/components/ConfirmDialog";
import { ErrorBanner } from "@/app/components/ErrorBanner";
import { IconButton, MenuPath } from "@/app/components/IconButton";
import { NewProject } from "@/app/components/NewProject";
import { ProjectRow } from "@/app/components/ProjectRow";
import type { Projects } from "@/app/hooks/useProjects";

/** The project rail. Pushes the layout on desktop, overlays as a drawer below lg. */
export function Rail({
  onSelect,
  onToggle,
  open,
  projects: { create, error, loading, projects, remove, rename },
  selectedId,
}: {
  onSelect: (id: string) => void;
  onToggle: () => void;
  open: boolean;
  projects: Projects;
  selectedId: string | null;
}) {
  const [pendingDelete, setPendingDelete] = useState<Project | null>(null);

  const register = (name: string) =>
    create(name).then((made) => {
      if (made) onSelect(made.id);
      return made;
    });

  return (
    <>
      <aside
        className={`fixed z-30 flex h-dvh flex-col overflow-hidden border-r border-ink transition-[width] duration-200 ease-out lg:static ${
          open ? "w-64" : "w-0"
        }`}
      >
        <div className="flex h-16 shrink-0 items-center gap-2 border-b border-ink px-3">
          <IconButton label="Close projects" onClick={onToggle}>
            {MenuPath}
          </IconButton>
          <span className="label">Projects</span>
        </div>

        <div className="min-w-64 shrink-0 px-3 py-3">
          <NewProject onCreate={register} />
        </div>

        <nav className="scroll-thin flex min-h-0 min-w-64 flex-1 flex-col gap-2 overflow-y-auto px-3 pb-3">
          {error && <ErrorBanner message={error} />}
          {!error && loading && (
            <p className="px-1 py-2 font-mono text-xs text-ink-soft">Loading…</p>
          )}
          {!error && !loading && projects.length === 0 && (
            <p className="px-1 py-2 font-mono text-xs text-ink-soft">No projects yet</p>
          )}
          {projects.map((project) => (
            <ProjectRow
              key={project.id}
              onDelete={() => setPendingDelete(project)}
              onRename={(name) => void rename(project.id, name)}
              onSelect={() => onSelect(project.id)}
              project={project}
              selected={project.id === selectedId}
            />
          ))}
        </nav>
      </aside>

      {pendingDelete && (
        <ConfirmDialog
          confirmLabel="Delete"
          description="Everything derived from it goes too."
          title={`Delete ${pendingDelete.name}?`}
          onClose={() => setPendingDelete(null)}
          onConfirm={() => {
            void remove(pendingDelete.id);
            setPendingDelete(null);
          }}
        />
      )}
    </>
  );
}
