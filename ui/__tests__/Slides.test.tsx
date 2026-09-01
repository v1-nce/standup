import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test } from "vitest";
import { Slides } from "../app/components/Slides";
import { deck } from "./fixtures";

const DECK = deck("First", "Second", "Third");
const shown = () => screen.getByRole("heading", { level: 2 }).textContent;

test("a thumbnail jumps straight to its slide", () => {
  render(<Slides deck={DECK} />);

  fireEvent.click(screen.getByRole("button", { name: "Slide 3: Third" }));
  expect(shown()).toBe("Third");
});

test("arrow keys walk the deck and stop at both ends", () => {
  render(<Slides deck={DECK} />);

  fireEvent.keyDown(window, { key: "ArrowLeft" });
  expect(shown()).toBe("First");

  fireEvent.keyDown(window, { key: "ArrowRight" });
  fireEvent.keyDown(window, { key: "ArrowRight" });
  fireEvent.keyDown(window, { key: "ArrowRight" });
  expect(shown()).toBe("Third");
});

test("a slide shows the bullets behind it", () => {
  render(<Slides deck={DECK} />);
  // Thumbnails render the same faces, so scope to the stage — the only one in the a11y tree.
  expect(within(screen.getByRole("article")).getByText("First changed")).toBeDefined();
});

test("the preview reflects semantic topology and deck art direction", () => {
  const designed = deck("Compare");
  designed.design.theme = "dark";
  designed.slides![0] = {
    ...designed.slides![0],
    layout: "two_column",
    bullets: ["Session lookup"],
    secondary_title: "After",
    secondary_bullets: ["Signed token"],
  };

  render(<Slides deck={designed} />);

  const stage = screen.getByRole("article");
  expect(stage.style.backgroundColor).toBe("rgb(11, 16, 32)");
  expect(within(stage).getByText("Session lookup")).toBeDefined();
  expect(within(stage).getByText("Signed token")).toBeDefined();
});

test("a composed canvas renders agent-positioned layers instead of a template", () => {
  const composed = deck("Canvas");
  composed.slides![0].elements = [
    {
      id: "accent-panel",
      kind: "shape",
      x: 4,
      y: 8,
      width: 36,
      height: 84,
      text: "",
      shape: "rounded",
      fill: "accent",
      stroke: "transparent",
      stroke_width: 0,
      color: "text",
      font_size: 20,
      font_weight: "regular",
      align: "left",
      valign: "top",
      rotation: -3,
    },
    {
      id: "headline",
      kind: "text",
      x: 46,
      y: 24,
      width: 46,
      height: 38,
      text: "Build momentum",
      shape: "rectangle",
      fill: "transparent",
      stroke: "transparent",
      stroke_width: 0,
      color: "text",
      font_size: 48,
      font_weight: "bold",
      align: "left",
      valign: "middle",
      rotation: 0,
    },
  ];

  render(<Slides deck={composed} />);

  const layer = within(screen.getByRole("article")).getByText("Build momentum");
  expect(layer.style.position).toBe("absolute");
  expect(layer.style.left).toBe("46%");
});

test("a thumbnail is a miniature of its slide, not a placeholder", () => {
  render(<Slides deck={DECK} />);

  const thumb = screen.getByRole("button", { name: "Slide 2: Second" });
  expect(thumb.textContent).toContain("Second changed");
});

test("a shorter deck cannot strand the pick past its end", () => {
  const view = render(<Slides deck={DECK} />);
  fireEvent.click(screen.getByRole("button", { name: "Slide 3: Third" }));

  view.rerender(<Slides deck={deck("First", "Second")} />);

  expect(shown()).toBe("Second");
  // Only the current thumbnail is tabbable, so a stranded pick would leave the strip unreachable.
  expect(screen.getByRole("button", { name: "Slide 2: Second" }).tabIndex).toBe(0);
});

test("a project with no deck says so instead of rendering an empty stage", () => {
  render(<Slides deck={null} />);
  expect(screen.getByText("No deck yet")).toBeDefined();
  expect(screen.queryAllByRole("button", { name: /^Slide \d/ })).toHaveLength(0);
});

test("scrolling over the thumbnail strip moves between slides too, not only over the stage", () => {
  render(<Slides deck={DECK} />);
  const strip = screen.getByRole("button", { name: "Slide 1: First" }).parentElement;
  if (!strip) throw new Error("strip not found");

  fireEvent.wheel(strip, { deltaY: 150 });
  expect(shown()).toBe("Second");
});

test("the section can shrink below its thumbnail strip, so the strip scrolls instead of the page", () => {
  const { container } = render(<Slides deck={DECK} />);
  expect(container.querySelector("section")?.className).toContain("min-w-0");
});
