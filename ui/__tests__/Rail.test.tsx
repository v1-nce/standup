import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { Rail } from "../app/components/Rail";

const project = (id: string, name: string) => ({
  id,
  name,
  created_at: "2026-08-05T00:00:00Z",
  source: { kind: "local", location: "/repo", has_git: true },
});

/** A backend that answers from a list the test can mutate, so re-reads see the change. */
function server(projects: ReturnType<typeof project>[]) {
  return vi.fn((url: string, init?: RequestInit) => {
    const id = url.split("/projects/")[1];
    if (init?.method === "PATCH") {
      const renamed = String(JSON.parse(String(init.body)).name);
      projects = projects.map((p) => (p.id === id ? { ...p, name: renamed } : p));
      return Promise.resolve(new Response("{}", { status: 200 }));
    }
    if (init?.method === "DELETE") {
      projects = projects.filter((p) => p.id !== id);
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    return Promise.resolve(new Response(JSON.stringify(projects), { status: 200 }));
  });
}

beforeEach(() => vi.unstubAllGlobals());

test("lists what the backend returns", async () => {
  vi.stubGlobal("fetch", server([project("a-1", "standup"), project("b-2", "flask")]));
  render(<Rail onToggle={() => {}} open />);

  expect(await screen.findByRole("button", { name: "standup" })).toBeDefined();
  expect(screen.getByRole("button", { name: "flask" })).toBeDefined();
});

test("renaming sends a PATCH and shows the new name", async () => {
  const fetched = server([project("a-1", "standup")]);
  vi.stubGlobal("fetch", fetched);
  render(<Rail onToggle={() => {}} open />);

  fireEvent.click(await screen.findByRole("button", { name: "Rename standup" }));
  fireEvent.change(screen.getByLabelText("Rename standup"), { target: { value: "  weekly  " } });
  fireEvent.keyDown(screen.getByLabelText("Rename standup"), { key: "Enter" });

  await waitFor(() => expect(screen.getByRole("button", { name: "weekly" })).toBeDefined());
  const [url, init] = fetched.mock.calls.find(([, i]) => i?.method === "PATCH") ?? [];
  expect(url).toContain("/projects/a-1");
  expect(JSON.parse(String(init?.body))).toEqual({ name: "weekly" });
});

test("deleting asks first, and a refusal changes nothing", async () => {
  const fetched = server([project("a-1", "standup")]);
  vi.stubGlobal("fetch", fetched);
  vi.stubGlobal("confirm", vi.fn(() => false));
  render(<Rail onToggle={() => {}} open />);

  fireEvent.click(await screen.findByRole("button", { name: "Delete standup" }));
  expect(fetched.mock.calls.some(([, i]) => i?.method === "DELETE")).toBe(false);

  vi.stubGlobal("confirm", vi.fn(() => true));
  fireEvent.click(screen.getByRole("button", { name: "Delete standup" }));

  await waitFor(() => expect(screen.getByText("No projects yet")).toBeDefined());
});

test("a failed read is reported, not swallowed", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify({ detail: "boom" }), { status: 500 })),
    ),
  );
  render(<Rail onToggle={() => {}} open />);

  expect(await screen.findByText("boom")).toBeDefined();
});
