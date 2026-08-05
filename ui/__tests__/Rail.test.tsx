import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { Rail } from "../app/components/Rail";
import type { Projects } from "../app/hooks/useProjects";
import { project } from "./fixtures";

function show(overrides: Partial<Projects> = {}, onSelect = vi.fn()) {
  const projects: Projects = {
    projects: [project("a-1", "standup"), project("b-2", "flask")],
    error: null,
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

test("deleting asks first, and a refusal changes nothing", () => {
  const { projects } = show();

  vi.stubGlobal("confirm", vi.fn(() => false));
  fireEvent.click(screen.getByRole("button", { name: "Delete standup" }));
  expect(projects.remove).not.toHaveBeenCalled();

  vi.stubGlobal("confirm", vi.fn(() => true));
  fireEvent.click(screen.getByRole("button", { name: "Delete standup" }));
  expect(projects.remove).toHaveBeenCalledWith("a-1");
});

test("a failed read is reported, not swallowed", () => {
  show({ projects: [], error: "boom" });
  expect(screen.getByText("boom")).toBeDefined();
});
