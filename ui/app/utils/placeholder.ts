/**
 * Stand-in content until the API is wired. Delete this file at that point — nothing else
 * holds sample data, so there is exactly one thing to remove.
 */

import type { Message } from "@/app/components/ChatPanel";

export const SLIDES = ["Auth refactor", "Index rebuild", "Selection weights", "API surface"];

export const MESSAGES: Message[] = [
  { from: "you", text: "standup tomorrow, the auth work — three slides" },
  {
    from: "standup",
    text: "47 files changed since Monday. Three carry the week: the session rewrite, the index rebuild it forced, and the new weights table. Everything else is routine.",
  },
  { from: "you", text: "drop the weights one, add whatever touched the API" },
  { from: "standup", text: "Done. Slide 3 is now the API surface — rebuilt without a model call." },
];
