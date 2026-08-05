import { fireEvent, render, screen } from "@testing-library/react";
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
  expect(screen.getByText("First changed")).toBeDefined();
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
