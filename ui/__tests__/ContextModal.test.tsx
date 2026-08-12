import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { ContextModal } from "../app/components/ContextModal";

const held = [
  { id: "app-1", kind: "folder", name: "standup", location: "/dev/standup", added_at: "2026-08-06T00:00:00Z" },
  { id: "spec-2", kind: "file", name: "spec.pdf", location: "/ctx/spec.pdf", added_at: "2026-08-06T00:00:00Z" },
];

const seen: { path: string; init?: RequestInit }[] = [];

function server() {
  return vi.fn((path: string, init?: RequestInit) => {
    seen.push({ path, init });
    if (path.endsWith("/context") && init?.method === "POST")
      return Promise.resolve(Response.json({ id: "job-1", state: "running", step: "indexing" }));
    if (path.includes("/context/files"))
      return Promise.resolve(Response.json({ id: "job-1", state: "running", step: "indexing" }));
    if (path.startsWith("/jobs/"))
      return Promise.resolve(Response.json({ id: "job-1", state: "done", step: "indexing" }));
    if (init?.method === "DELETE") return Promise.resolve(new Response(null, { status: 204 }));
    return Promise.resolve(Response.json(held));
  });
}

beforeEach(() => {
  seen.length = 0;
  HTMLDialogElement.prototype.showModal = vi.fn();
  HTMLDialogElement.prototype.close = vi.fn();
  vi.stubGlobal("fetch", server());
});

test("it lists what the project already draws on", async () => {
  render(<ContextModal onClose={vi.fn()} projectId="p-1" />);

  expect(await screen.findByText("standup")).toBeDefined();
  expect(screen.getByText("spec.pdf")).toBeDefined();
});

test("a typed folder path is attached as a location, and the field clears", async () => {
  render(<ContextModal onClose={vi.fn()} projectId="p-1" />);
  const field = await screen.findByLabelText("Folder path");

  fireEvent.change(field, { target: { value: "  C:/Dev/forge  " } });
  fireEvent.click(screen.getByText("Add"));

  await waitFor(() => {
    const posted = seen.find((call) => call.path.endsWith("/context") && call.init?.method === "POST");
    expect(JSON.parse(String(posted?.init?.body))).toEqual({ locations: ["C:/Dev/forge"] });
  });
  expect((field as HTMLInputElement).value).toBe("");
});

test("an empty path asks the backend for nothing", async () => {
  render(<ContextModal onClose={vi.fn()} projectId="p-1" />);

  fireEvent.change(await screen.findByLabelText("Folder path"), { target: { value: "   " } });
  fireEvent.click(screen.getByText("Add"));

  expect(seen.some((call) => call.init?.method === "POST")).toBe(false);
});

test("chosen documents are uploaded as multipart, without a content-type we invented", async () => {
  const { container } = render(<ContextModal onClose={vi.fn()} projectId="p-1" />);
  await screen.findByText("Add file");
  const chooser = container.querySelector("input[type=file]");

  fireEvent.change(chooser!, { target: { files: [new File(["# Notes"], "notes.md")] } });

  await waitFor(() => expect(seen.some((call) => call.path.endsWith("/context/files"))).toBe(true));
  const upload = seen.find((call) => call.path.endsWith("/context/files"));
  expect(upload?.init?.body).toBeInstanceOf(FormData);
  expect(upload?.init?.headers).toBeUndefined();
});

test("dropped documents take the same path as chosen ones", async () => {
  render(<ContextModal onClose={vi.fn()} projectId="p-1" />);
  const zone = await screen.findByText("Drop documents here");

  fireEvent.drop(zone.parentElement!, {
    dataTransfer: { files: [new File(["# Notes"], "notes.md", { type: "text/markdown" })] },
  });

  await waitFor(() => expect(seen.some((call) => call.path.endsWith("/context/files"))).toBe(true));
});

test("the add controls are shut while an add is indexing", async () => {
  render(<ContextModal onClose={vi.fn()} projectId="p-1" />);
  const field = await screen.findByLabelText("Folder path");

  fireEvent.change(field, { target: { value: "C:/Dev/forge" } });
  fireEvent.click(screen.getByText("Add"));

  expect(screen.getByText("Add")).toHaveProperty("disabled", true);
  expect(screen.getByLabelText("Folder path")).toHaveProperty("disabled", true);

  await waitFor(() => expect(screen.getByText("Add")).toHaveProperty("disabled", false));
});

test("removing something asks the backend to detach it", async () => {
  render(<ContextModal onClose={vi.fn()} projectId="p-1" />);

  fireEvent.click(await screen.findByLabelText("Remove spec.pdf"));

  await waitFor(() =>
    expect(seen.some((call) => call.path.endsWith("/context/spec-2"))).toBe(true),
  );
});

test("removing something clears a stale error left by an earlier failed add", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string, init?: RequestInit) => {
      if (path.endsWith("/context") && init?.method === "POST") {
        return Promise.resolve(new Response(JSON.stringify({ detail: "not a directory" }), { status: 400 }));
      }
      if (init?.method === "DELETE") return Promise.resolve(new Response(null, { status: 204 }));
      return Promise.resolve(Response.json(held));
    }),
  );

  render(<ContextModal onClose={vi.fn()} projectId="p-1" />);
  const field = await screen.findByLabelText("Folder path");

  fireEvent.change(field, { target: { value: "C:/nope" } });
  fireEvent.click(screen.getByText("Add"));
  expect(await screen.findByText("not a directory")).toBeDefined();

  fireEvent.click(await screen.findByLabelText("Remove spec.pdf"));
  await waitFor(() => expect(screen.queryByText("not a directory")).toBeNull());
});

test("the close control reports it, rather than closing behind the caller's back", async () => {
  const onClose = vi.fn();
  render(<ContextModal onClose={onClose} projectId="p-1" />);

  fireEvent.click(await screen.findByLabelText("Close context"));
  expect(onClose).toHaveBeenCalled();
});
