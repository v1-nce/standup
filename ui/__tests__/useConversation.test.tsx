import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { useConversation } from "../app/hooks/useConversation";

const emptyDeck = { selection: { request: "", scope: {}, chosen: [], cut: [] }, slides: null };

function server(onChat: () => unknown = () => []) {
  return vi.fn((path: string) => {
    if (path.endsWith("/chat")) return Promise.resolve(Response.json(onChat()));
    if (path.endsWith("/deck")) return Promise.resolve(Response.json(emptyDeck));
    return Promise.resolve(new Response(null, { status: 404 }));
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", server());
});

test("a send that never reaches the server does not leave a stale optimistic bubble", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string, init?: RequestInit) => {
      if (path.endsWith("/chat") && init?.method === "POST") {
        return Promise.resolve(new Response(JSON.stringify({ detail: "already working" }), { status: 409 }));
      }
      if (path.endsWith("/chat")) return Promise.resolve(Response.json([{ role: "user", content: "real one", at: "2026-08-14T00:00:00Z" }]));
      if (path.endsWith("/deck")) return Promise.resolve(Response.json(emptyDeck));
      return Promise.resolve(new Response(null, { status: 404 }));
    }),
  );

  const { result } = renderHook(() => useConversation("p-1"));
  await waitFor(() => expect(result.current.messages).toHaveLength(1));

  await act(() => result.current.send("dropped on the floor"));

  await waitFor(() => expect(result.current.error).toBeTruthy());
  // Resynced with the server's actual history, not left holding the never-sent optimistic bubble.
  expect(result.current.messages.map((m) => m.content)).toEqual(["real one"]);
});
