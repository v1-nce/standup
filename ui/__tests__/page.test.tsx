import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import type { ChatMessage } from "../app/api/client";
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

beforeEach(() => {
  vi.stubGlobal("fetch", server());
  HTMLDialogElement.prototype.showModal = vi.fn();
  HTMLDialogElement.prototype.close = vi.fn();
});

const composer = () => screen.getByLabelText("What do you need to present?");

test("the shell composes a rail toggle, a conversation, a composer and a stage", async () => {
  render(<Page />);

  expect(screen.getByRole("img", { name: "Standup" })).toBeDefined();
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

test("a slow send left behind on the old project doesn't leave the new one stuck disabled", async () => {
  const state = { projects: [project("a-1", "standup"), project("b-2", "flask")] };
  const control: { resolveSlowJob?: () => void } = {};

  const fetched = vi.fn((url: string, init?: RequestInit) => {
    if (url.endsWith("/projects")) return Promise.resolve(Response.json(state.projects));
    if (url.endsWith("/deck")) {
      return Promise.resolve(new Response(JSON.stringify({ detail: "No deck yet" }), { status: 404 }));
    }
    if (init?.method === "POST" && url.includes("a-1/chat")) {
      return Promise.resolve(Response.json({ id: "job-a", state: "running", step: "thinking" }, { status: 202 }));
    }
    if (url.includes("/jobs/job-a")) {
      return new Promise((resolve) => {
        control.resolveSlowJob = () => resolve(Response.json({ id: "job-a", state: "done", step: "thinking" }));
      });
    }
    return Promise.resolve(Response.json([]));
  });
  vi.stubGlobal("fetch", fetched);

  render(<Page />);
  await screen.findByText("No deck yet");

  fireEvent.change(composer(), { target: { value: "go" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(screen.getByText("Working…")).toBeDefined();

  fireEvent.click(await screen.findByRole("button", { name: "flask" }));
  expect(composer()).toHaveProperty("disabled", false);

  // A's send only resolves now, well after B became the active project.
  control.resolveSlowJob?.();
  await waitFor(() => expect(fetched.mock.calls.some(([u]) => String(u).includes("jobs/job-a"))).toBe(true));

  expect(composer()).toHaveProperty("disabled", false);
});

test("deleting the active project falls back to another instead of dying on the dead id", async () => {
  const state = { projects: [project("a-1", "standup"), project("b-2", "flask")] };
  const fetched = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "DELETE") {
      state.projects = state.projects.filter((p) => p.id !== "b-2");
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    if (url.endsWith("/chat")) return Promise.resolve(Response.json([]));
    if (url.endsWith("/deck")) {
      return Promise.resolve(new Response(JSON.stringify({ detail: "No deck yet" }), { status: 404 }));
    }
    if (url.endsWith("/projects")) return Promise.resolve(Response.json(state.projects));
    return Promise.resolve(Response.json({}));
  });
  vi.stubGlobal("fetch", fetched);

  render(<Page />);
  fireEvent.click(await screen.findByRole("button", { name: "flask" }));
  fireEvent.click(screen.getByRole("button", { name: "Delete flask" }));
  fireEvent.click(screen.getByText("Delete"));

  await waitFor(() => expect(screen.queryByRole("button", { name: "flask" })).toBeNull());
  expect(screen.getByRole("button", { name: "standup" })).toBeDefined();
});

test("switching projects while the old one is still loading leaves no stale message behind", async () => {
  const state: { projects: ReturnType<typeof project>[]; chats: Record<string, ChatMessage[]> } = {
    projects: [project("a-1", "standup"), project("b-2", "flask")],
    chats: { "a-1": [{ role: "assistant", content: "About standup", at: "2026-08-05T00:00:00Z" }], "b-2": [] },
  };
  const control: { resolveSlowChat?: () => void } = {};

  const fetched = vi.fn((url: string) => {
    if (url.endsWith("/projects")) return Promise.resolve(Response.json(state.projects));
    if (url.endsWith("/deck")) {
      return Promise.resolve(new Response(JSON.stringify({ detail: "No deck yet" }), { status: 404 }));
    }
    if (url.includes("a-1/chat")) {
      return new Promise((resolve) => {
        control.resolveSlowChat = () => resolve(Response.json(state.chats["a-1"]));
      });
    }
    if (url.includes("b-2/chat")) return Promise.resolve(Response.json(state.chats["b-2"]));
    return Promise.resolve(Response.json({}));
  });
  vi.stubGlobal("fetch", fetched);

  render(<Page />);
  fireEvent.click(await screen.findByRole("button", { name: "flask" }));

  control.resolveSlowChat?.();

  await waitFor(() => expect(fetched.mock.calls.some(([u]) => String(u).includes("b-2/chat"))).toBe(true));
  expect(screen.queryByText("About standup")).toBeNull();
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
