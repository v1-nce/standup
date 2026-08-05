import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import Page from "../app/page";

test("the shell composes a rail toggle, a conversation, a composer and a deck", () => {
  render(<Page />);

  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("STANDUP");
  expect(screen.getByRole("button", { name: "Open projects" })).toBeDefined();
  expect(screen.getByLabelText("What do you need to present?")).toBeDefined();
  expect(screen.getAllByRole("button", { name: /^Slide \d/ })).toHaveLength(4);
});

test("sending a request adds it to the conversation", () => {
  render(<Page />);
  const composer = screen.getByLabelText("What do you need to present?");

  fireEvent.change(composer, { target: { value: "demo on Thursday" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));

  expect(screen.getByText("demo on Thursday")).toBeDefined();
});

test("the composer keeps the arrow keys the deck would otherwise take", () => {
  render(<Page />);

  fireEvent.keyDown(screen.getByLabelText("What do you need to present?"), {
    key: "ArrowRight",
  });
  expect(screen.getByRole("heading", { level: 2 }).textContent).toBe("Auth refactor");
});
