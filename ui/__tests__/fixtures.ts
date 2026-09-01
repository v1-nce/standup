import type { Deck, Project, Scored } from "../app/api/client";

export const project = (id: string, name: string): Project => ({
  id,
  name,
  created_at: "2026-08-05T00:00:00Z",
  resources: [],
});

export const scored = (title: string, extra: Partial<Scored> = {}): Scored => ({
  candidate: { id: `src/${title}.py`, paths: [], commits: [] },
  signals: {},
  score: 1,
  ...extra,
});

export const deck = (...titles: string[]): Deck => ({
  design: {
    theme: "technical",
    heading_font: "Aptos Display",
    body_font: "Aptos",
  },
  selection: {
    request: "standup tomorrow",
    scope: { paths: [], keywords: [], slide_budget: titles.length },
    chosen: titles.map((title) => scored(title)),
    cut: [],
  },
  slides: titles.map((title) => ({
    candidate_id: `src/${title}.py`,
    free: false,
    title,
    subtitle: "",
    bullets: [`${title} changed`],
    secondary_title: "",
    secondary_bullets: [],
    layout: "auto",
    speaker_notes: "",
    elements: [],
  })),
});
