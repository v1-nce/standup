"use client";

import { useState } from "react";
import { ChatPanel } from "@/app/components/ChatPanel";
import { Composer } from "@/app/components/Composer";
import { ContextModal } from "@/app/components/ContextModal";
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
  if (picked && !projects.projects.some((p) => p.id === picked)) setPicked(null);
  const selectedId = picked ?? projects.projects[0]?.id ?? null;
  const selectedProject = projects.projects.find((p) => p.id === selectedId);
  const { deck, error, messages, pending, send } = useConversation(selectedId);
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
            <IconButton className="h-10 w-10" label="Open projects" onClick={toggleRail}>
              {MenuPath}
            </IconButton>
          )}
          <div className="flex items-baseline gap-2.5">
            <span aria-hidden className="inline-block h-3 w-3 self-center bg-ink" />
            <h1 className="font-sans text-xl font-black tracking-[0.22em] uppercase">STANDUP</h1>
          </div>
          <IconButton
            className="ml-auto h-10 w-10"
            label={dark ? "Switch to light mode" : "Switch to dark mode"}
            onClick={toggleTheme}
          >
            {dark ? SunPath : MoonPath}
          </IconButton>
        </header>

        <div className="flex min-h-0 flex-1 flex-col gap-4 p-4 lg:flex-row">
          <section className="flex min-h-0 flex-col gap-4 lg:w-96 lg:shrink-0">
            <ChatPanel
              messages={messages}
              onAddContext={selectedId ? () => setContextOpen(true) : undefined}
              pending={pending}
              projectName={selectedProject?.name ?? null}
            />
            {error && (
              <p className="stamp-ink shrink-0 px-3 py-2 font-mono text-xs">{error}</p>
            )}
            <Composer disabled={!selectedId || pending} onSend={send} />
          </section>

          <Slides deck={deck} />
        </div>
      </div>

      {contextOpen && selectedId && (
        <ContextModal onClose={() => setContextOpen(false)} projectId={selectedId} />
      )}
    </div>
  );
}
