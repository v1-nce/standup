"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type Project } from "@/app/api/client";

/** The project list. */
export function useProjects() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState<string | null>(null);
  
  const after = useCallback(
    (action: Promise<unknown> = Promise.resolve()) =>
      action
        .then(api.listProjects)
        .then((found) => {
          setProjects(found);
          setError(null);
        })
        .catch((failure: Error) => setError(failure.message)),
    [],
  );

  useEffect(() => void after(), [after]);

  return {
    projects,
    error,
    rename: (id: string, name: string) => after(api.renameProject(id, name)),
    remove: (id: string) => after(api.deleteProject(id)),
  };
}
