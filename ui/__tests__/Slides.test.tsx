import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Slides } from "../app/components/Slides";

const DECK = ["First", "Second", "Third"];
const shown = () => screen.getByRole("heading", { level: 2 }).textContent;

test("a thumbnail jumps straight to its slide", () => {
  render(<Slides slides={DECK} />);

  fireEvent.click(screen.getByRole("button", { name: "Slide 3: Third" }));
  expect(shown()).toBe("Third");
});

test("arrow keys walk the deck and stop at both ends", () => {
  render(<Slides slides={DECK} />);

  fireEvent.keyDown(window, { key: "ArrowLeft" });
  expect(shown()).toBe("First");

  fireEvent.keyDown(window, { key: "ArrowRight" });
  fireEvent.keyDown(window, { key: "ArrowRight" });
  fireEvent.keyDown(window, { key: "ArrowRight" });
  expect(shown()).toBe("Third");
});
