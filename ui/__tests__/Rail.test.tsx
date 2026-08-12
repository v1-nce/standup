import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { Rail } from "../app/components/Rail";
import type { Projects } from "../app/hooks/useProjects";
import { project } from "./fixtures";

function show(overrides: Partial<Projects> = {}, onSelect = vi.fn()) {
  const projects: Projects = {
    projects: [project("a-1", "standup"), project("b-2", "flask")],
    error: null,
    create: vi.fn(() => Promise.resolve(project("c-3", "flask"))),
    rename: vi.fn(() => Promise.resolve()),
    remove: vi.fn(() => Promise.resolve()),
    ...overrides,
  };
  render(
    <Rail onSelect={onSelect} onToggle={vi.fn()} open projects={projects} selectedId="a-1" />,
  );
  return { projects, onSelect };
}

beforeEach(() => vi.unstubAllGlobals());

test("lists what it was given and reports the picked one", () => {
  const { onSelect } = show();

  expect(screen.getByRole("button", { name: "flask" })).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "flask" }));
  expect(onSelect).toHaveBeenCalledWith("b-2");
});

test("renaming hands over the trimmed name", () => {
  const { projects } = show();

  fireEvent.click(screen.getByRole("button", { name: "Rename standup" }));
  fireEvent.change(screen.getByLabelText("Rename standup"), { target: { value: "  weekly  " } });
  fireEvent.keyDown(screen.getByLabelText("Rename standup"), { key: "Enter" });

  expect(projects.rename).toHaveBeenCalledWith("a-1", "weekly");
});

test("escape abandons a rename", () => {
  const { projects } = show();

  fireEvent.click(screen.getByRole("button", { name: "Rename standup" }));
  fireEvent.change(screen.getByLabelText("Rename standup"), { target: { value: "nope" } });
  fireEvent.keyDown(screen.getByLabelText("Rename standup"), { key: "Escape" });

  expect(projects.rename).not.toHaveBeenCalled();
});

test("the blur a real browser fires when escape unmounts the field doesn't resurrect the rename", () => {
  const { projects } = show();

  fireEvent.click(screen.getByRole("button", { name: "Rename standup" }));
  const field = screen.getByLabelText("Rename standup");
  fireEvent.change(field, { target: { value: "nope" } });
  fireEvent.keyDown(field, { key: "Escape" });
  fireEvent.blur(field);

  expect(projects.rename).not.toHaveBeenCalled();
});

test("deleting asks first, and a refusal changes nothing", () => {
  const { projects } = show();

  vi.stubGlobal("confirm", vi.fn(() => false));
  fireEvent.click(screen.getByRole("button", { name: "Delete standup" }));
  expect(projects.remove).not.toHaveBeenCalled();

  vi.stubGlobal("confirm", vi.fn(() => true));
  fireEvent.click(screen.getByRole("button", { name: "Delete standup" }));
  expect(projects.remove).toHaveBeenCalledWith("a-1");
});

const startNaming = () => {
  fireEvent.click(screen.getByRole("button", { name: "+ New project" }));
  return screen.getByLabelText("Name the new project");
};

test("creating hands over the trimmed name and opens what it made", async () => {
  const { onSelect, projects } = show();

  const field = startNaming();
  fireEvent.change(field, { target: { value: "  Sprint demo  " } });
  fireEvent.keyDown(field, { key: "Enter" });

  expect(projects.create).toHaveBeenCalledWith("Sprint demo");
  await waitFor(() => expect(onSelect).toHaveBeenCalledWith("c-3"));
});

test("escape abandons naming", () => {
  const { projects } = show();

  fireEvent.keyDown(startNaming(), { key: "Escape" });

  expect(projects.create).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "+ New project" })).toBeDefined();
});

test("the blur a real browser fires when escape unmounts the field doesn't resurrect the create", () => {
  const { projects } = show();

  const field = startNaming();
  fireEvent.change(field, { target: { value: "nope" } });
  fireEvent.keyDown(field, { key: "Escape" });
  fireEvent.blur(field);

  expect(projects.create).not.toHaveBeenCalled();
});

test("a name the backend rejects stays on screen to be corrected", async () => {
  const { projects } = show({ create: vi.fn(() => Promise.resolve(null)) });

  const field = startNaming();
  fireEvent.change(field, { target: { value: "nope" } });
  fireEvent.keyDown(field, { key: "Enter" });

  expect(projects.create).toHaveBeenCalledWith("nope");
  await waitFor(() =>
    expect(screen.getByLabelText("Name the new project")).toHaveProperty("value", "nope"),
  );
});

test("a failed read is reported, not swallowed", () => {
  show({ projects: [], error: "boom" });
  expect(screen.getByText("boom")).toBeDefined();
});
