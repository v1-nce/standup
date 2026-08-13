import type { Deck, Project } from "../app/api/client";

export const project = (id: string, name: string): Project => ({
  id,
  name,
  created_at: "2026-08-05T00:00:00Z",
  resources: [],
});

export const deck = (...titles: string[]): Deck => ({
  selection: {
    request: "standup tomorrow",
    scope: { paths: [], keywords: [], slide_budget: titles.length },
    chosen: titles.map((title) => ({
      candidate: { id: `src/${title}.py`, title, paths: [], commits: [] },
      signals: {},
      score: 1,
    })),
    cut: [],
  },
  slides: titles.map((title) => ({
    candidate_id: `src/${title}.py`,
    free: false,
    title,
    bullets: [`${title} changed`],
  })),
});
