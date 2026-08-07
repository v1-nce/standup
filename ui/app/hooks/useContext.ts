"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, reason, type Resource } from "@/app/api/client";

/** A project's context: what it may draw on, and the indexing that follows a change. */
export function useProjectContext(projectId: string) {
  const [resources, setResources] = useState<Resource[]>([]);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);
  const leaving = useRef<AbortController>(null);

  useEffect(() => {
    const closing = new AbortController();
    leaving.current = closing;
    return () => closing.abort();
  }, []);

  const list = useCallback(() => {
    const mine = ++latest.current;
    return api
      .listContext(projectId)
      .then((held) => {
        if (mine === latest.current) setResources(held);
      })
      .catch((failure: unknown) => setError(reason(failure)));
  }, [projectId]);

  useEffect(() => void list(), [list]);

  const added = (start: Promise<{ id: string }>) => {
    setError(null);
    return start
      .then((job) => list().then(() => api.awaitJob(job.id, leaving.current?.signal)))
      .then((done) => {
        if (done.state === "failed") setError(done.detail || "Indexing failed");
      })
      .catch((failure: unknown) => setError(reason(failure)))
      .finally(list);
  };

  return {
    resources,
    error,
    addFolder: (location: string) => added(api.addPaths(projectId, [location])),
    addFiles: (files: FileList | File[]) =>
      files.length ? added(api.addFiles(projectId, files)) : Promise.resolve(),
    remove: (resourceId: string) =>
      api
        .removeContext(projectId, resourceId)
        .then(list)
        .catch((failure: unknown) => setError(reason(failure))),
  };
}
