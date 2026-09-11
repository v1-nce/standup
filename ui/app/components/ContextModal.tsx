"use client";

import { useEffect, useRef, useState } from "react";
import { ClosePath, IconButton, TrashPath } from "@/app/components/IconButton";
import { ErrorBanner } from "@/app/components/ErrorBanner";
import { useProjectContext } from "@/app/hooks/useContext";

const CONTROL =
  "press border border-ink bg-paper px-3 py-1.5 font-mono text-xs font-bold uppercase tracking-[0.08em] shadow-hard enabled:hover:bg-ink enabled:hover:text-paper disabled:pointer-events-none disabled:opacity-50";

/** What a project may draw on. A folder is named by its path; a document is handed over whole,
 *  because a page is never told where a dropped file lives. */
export function ContextModal({ onClose, projectId }: { onClose: () => void; projectId: string }) {
  const { addFiles, addFolder, busy, error, remove, resources } = useProjectContext(projectId);
  const frame = useRef<HTMLDialogElement>(null);
  const chooser = useRef<HTMLInputElement>(null);
  const [path, setPath] = useState("");
  const [over, setOver] = useState(false);

  useEffect(() => {
    const dialog = frame.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);

  return (
    <dialog
      ref={frame}
      className="m-auto flex max-h-[85vh] w-[min(36rem,92vw)] flex-col border border-ink bg-paper p-0 text-ink shadow-hard backdrop:bg-ink-faint"
      onClose={onClose}
    >
      <div className="flex shrink-0 items-center justify-between border-b border-ink px-4 py-3">
        <span className="label">Context</span>
        <IconButton label="Close context" onClick={onClose} size="sm">
          {ClosePath}
        </IconButton>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-4 p-4">
        <form
          className="flex shrink-0 items-end gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (!path.trim()) return;
            void addFolder(path.trim());
            setPath("");
          }}
        >
          <input
            className="field min-w-0 flex-1 text-xs disabled:opacity-50"
            aria-label="Folder path"
            disabled={busy}
            placeholder="Add folder (path)"
            value={path}
            onChange={(event) => setPath(event.target.value)}
          />
          <button className={CONTROL} disabled={busy} type="submit">
            Add
          </button>
        </form>

        <div
          aria-busy={busy}
          className={`flex shrink-0 flex-col items-center gap-3 border border-dashed p-6 transition-colors ${
            over ? "border-ink bg-ink text-paper" : "border-ink-faint"
          }`}
          onDragLeave={() => setOver(false)}
          onDragOver={(event) => {
            if (busy) return;
            event.preventDefault();
            setOver(true);
          }}
          onDrop={(event) => {
            event.preventDefault();
            setOver(false);
            if (!busy) void addFiles(event.dataTransfer.files);
          }}
        >
          <p className={`text-sm ${over ? "text-paper" : "text-ink-soft"}`}>
            {busy ? "Indexing…" : "Drop documents here"}
          </p>
          <button className={CONTROL} disabled={busy} onClick={() => chooser.current?.click()}>
            Add file
          </button>
          <input
            ref={chooser}
            className="hidden"
            type="file"
            multiple
            disabled={busy}
            onChange={(event) => {
              if (event.target.files?.length) void addFiles(event.target.files);
              event.target.value = "";
            }}
          />
        </div>

        {error && <ErrorBanner message={error} />}

        <ul className="scroll-thin min-h-0 flex-1 overflow-y-auto">
          {resources.map((resource) => (
            <li key={resource.id} className="group flex items-center gap-2 border-b border-ink-ghost py-2">
              <span className="stamp shrink-0">{resource.kind}</span>
              <span className="min-w-0 flex-1 truncate font-mono text-sm" title={resource.location}>
                {resource.name}
              </span>
              <IconButton
                className="shrink-0 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                disabled={busy}
                label={`Remove ${resource.name}`}
                onClick={() => void remove(resource.id)}
                size="sm"
              >
                {TrashPath}
              </IconButton>
            </li>
          ))}
        </ul>
      </div>
    </dialog>
  );
}
