"use client";

import { useState } from "react";
import { ChatPanel } from "@/app/components/ChatPanel";
import { Composer } from "@/app/components/Composer";
import { IconButton, MenuPath } from "@/app/components/IconButton";
import { Rail } from "@/app/components/Rail";
import { Slides } from "@/app/components/Slides";
import { MESSAGES, SLIDES } from "@/app/utils/placeholder";

export default function Home() {
  const [railOpen, setRailOpen] = useState(false);
  const [messages, setMessages] = useState(MESSAGES);
  const toggleRail = () => setRailOpen((open) => !open);
  const send = (request: string) =>
    setMessages((sent) => [...sent, { from: "you", text: request }]);

  return (
    <div className="flex h-dvh overflow-hidden">
      <div
        aria-hidden
        className={`fixed inset-0 z-20 bg-ink/20 transition-opacity lg:hidden ${
          railOpen ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={() => setRailOpen(false)}
      />

      <Rail onToggle={toggleRail} open={railOpen} />

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
            <ChatPanel messages={messages} />
            <Composer onSend={send} />
          </section>

          <Slides slides={SLIDES} />
        </div>
      </div>
    </div>
  );
}
