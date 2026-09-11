"use client";

import { useState } from "react";
import { ChatPanel } from "@/app/components/ChatPanel";
import { Composer } from "@/app/components/Composer";
import { ContextModal } from "@/app/components/ContextModal";
import { ErrorBanner } from "@/app/components/ErrorBanner";
import { IconButton, MenuPath, MoonPath, SunPath } from "@/app/components/IconButton";
import { Rail } from "@/app/components/Rail";
import { Slides } from "@/app/components/Slides";
import { useConversation } from "@/app/hooks/useConversation";
import { useProjects } from "@/app/hooks/useProjects";
import { useTheme } from "@/app/hooks/useTheme";

export default function Home() {
  const [railOpen, setRailOpen] = useState(false);
  const [contextOpen, setContextOpen] = useState(false);
  const [picked, setPicked] = useState<string | null>(null);

  const projects = useProjects();
  // A picked project that no longer exists (deleted elsewhere, or not yet loaded) falls back
  // to the first project below - clearing it here, during render, is the set-during-render
  // pattern React re-runs before commit, not a bug.
  if (picked && !projects.projects.some((p) => p.id === picked)) setPicked(null);
  const selectedId = picked ?? projects.projects[0]?.id ?? null;
  const selectedProject = projects.projects.find((p) => p.id === selectedId);
  const { deck, error, loading, messages, pending, send } = useConversation(selectedId);
  const { dark, toggle: toggleTheme } = useTheme();

  const toggleRail = () => setRailOpen((open) => !open);

  return (
    <div className="flex h-dvh overflow-hidden">
      <div
        aria-hidden
        className={`fixed inset-0 z-20 bg-ink-faint transition-opacity lg:hidden ${
          railOpen ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={() => setRailOpen(false)}
      />

      <Rail
        onSelect={setPicked}
        onToggle={toggleRail}
        open={railOpen}
        projects={projects}
        selectedId={selectedId}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 shrink-0 items-center gap-3 border-b border-ink px-3">
          {!railOpen && (
            <IconButton label="Open projects" onClick={toggleRail}>
              {MenuPath}
            </IconButton>
          )}
          {/* eslint-disable-next-line @next/next/no-img-element -- a static public asset in a static export; no image optimizer to use */}
          <img src="/standup.png" alt="Standup" className="h-14 w-14 object-contain" />
          <IconButton
            className="ml-auto"
            label={dark ? "Switch to light mode" : "Switch to dark mode"}
            onClick={toggleTheme}
          >
            {dark ? SunPath : MoonPath}
          </IconButton>
        </header>

        <div className="flex min-h-0 flex-1 flex-col gap-4 p-4 lg:flex-row">
          <section className="flex min-h-0 flex-col gap-4 lg:w-96 lg:shrink-0">
            <ChatPanel
              loading={loading}
              messages={messages}
              onAddContext={selectedId ? () => setContextOpen(true) : undefined}
              pending={pending}
              projectName={selectedProject?.name ?? null}
            />
            {error && <ErrorBanner message={error} />}
            <Composer disabled={!selectedId || pending} onSend={send} />
          </section>

          <Slides deck={deck} pending={pending} />
        </div>
      </div>

      {contextOpen && selectedId && (
        <ContextModal onClose={() => setContextOpen(false)} projectId={selectedId} />
      )}
    </div>
  );
}
