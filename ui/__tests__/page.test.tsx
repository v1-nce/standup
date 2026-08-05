import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import Page from "../app/page";
import { deck, project } from "./fixtures";

function server() {
  const state = { messages: [] as { role: string; content: string; at: string }[], deck: null as ReturnType<typeof deck> | null };

  const send = (body: unknown, status = 200) =>
    Promise.resolve(new Response(JSON.stringify(body), { status }));

  const fetched = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST" && url.endsWith("/chat")) {
      const { content } = JSON.parse(String(init.body));
      state.messages = [
        { role: "user", content, at: "2026-08-05T00:00:00Z" },
        { role: "assistant", content: "Three slides on the auth work.", at: "2026-08-05T00:00:01Z" },
      ];
      state.deck = deck("Auth", "Index");
      return send({ id: "job-1", state: "running", step: "thinking" }, 202);
    }
    if (url.includes("/jobs/")) return send({ id: "job-1", state: "done", step: "thinking" });
    if (url.endsWith("/chat")) return send(state.messages);
    if (url.endsWith("/deck")) {
      return state.deck ? send(state.deck) : send({ detail: "No deck yet" }, 404);
    }
    return send([project("a-1", "standup")]);
  });

  return fetched;
}

beforeEach(() => vi.stubGlobal("fetch", server()));

const composer = () => screen.getByLabelText("What do you need to present?");

test("the shell composes a rail toggle, a conversation, a composer and a stage", async () => {
  render(<Page />);

  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("STANDUP");
  expect(screen.getByRole("button", { name: "Open projects" })).toBeDefined();
  expect(await screen.findByText("No deck yet")).toBeDefined();
});

test("sending a message shows the reply and the deck it produced", async () => {
  render(<Page />);
  await screen.findByText("No deck yet");

  fireEvent.change(composer(), { target: { value: "standup tomorrow, the auth work" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));

  expect(await screen.findByText("Three slides on the auth work.")).toBeDefined();
  expect(screen.getByText("standup tomorrow, the auth work")).toBeDefined();
  await waitFor(() => expect(screen.getAllByRole("button", { name: /^Slide \d/ })).toHaveLength(2));
});

test("the composer is shut while a turn is in flight", async () => {
  render(<Page />);
  await screen.findByText("No deck yet");

  fireEvent.change(composer(), { target: { value: "go" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));

  expect(screen.getByText("Working…")).toBeDefined();
  await waitFor(() => expect(composer()).toHaveProperty("disabled", false));
});

test("the composer keeps the arrow keys the deck would otherwise take", async () => {
  render(<Page />);
  await screen.findByText("No deck yet");

  fireEvent.change(composer(), { target: { value: "go" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await screen.findByRole("button", { name: "Slide 2: Index" });

  fireEvent.keyDown(composer(), { key: "ArrowRight" });
  expect(screen.getByRole("heading", { level: 2 }).textContent).toBe("Auth");
});
