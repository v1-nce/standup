"use client";

import { useState } from "react";
import { ChatPanel } from "@/app/components/ChatPanel";
import { Composer } from "@/app/components/Composer";
import { ContextModal } from "@/app/components/ContextModal";
import { IconButton, MenuPath } from "@/app/components/IconButton";
import { Rail } from "@/app/components/Rail";
import { Slides } from "@/app/components/Slides";
import { useConversation } from "@/app/hooks/useConversation";
import { useProjects } from "@/app/hooks/useProjects";

export default function Home() {
  const [railOpen, setRailOpen] = useState(false);
  const [contextOpen, setContextOpen] = useState(false);
  const [picked, setPicked] = useState<string | null>(null);

  const projects = useProjects();
  if (picked && !projects.projects.some((p) => p.id === picked)) setPicked(null);
  const selectedId = picked ?? projects.projects[0]?.id ?? null;
  const { deck, error, messages, pending, send } = useConversation(selectedId);

  const toggleRail = () => setRailOpen((open) => !open);

  return (
    <div className="flex h-dvh overflow-hidden">
      <div
        aria-hidden
        className={`fixed inset-0 z-20 bg-ink/20 transition-opacity lg:hidden ${
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
        <header className="flex h-14 shrink-0 items-center gap-1 border-b border-rule px-2">
          {!railOpen && (
            <IconButton label="Open projects" onClick={toggleRail}>
              {MenuPath}
            </IconButton>
          )}
          <h1 className="pl-3 font-mono text-sm tracking-[0.18em]">STANDUP</h1>
        </header>

        <div className="flex min-h-0 flex-1 flex-col gap-3 p-3 lg:flex-row">
          <section className="flex min-h-0 flex-col gap-3 lg:w-96 lg:shrink-0">
            <ChatPanel
              messages={messages}
              onAddContext={selectedId ? () => setContextOpen(true) : undefined}
              pending={pending}
            />
            {error && <p className="shrink-0 font-mono text-xs text-accent">{error}</p>}
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
