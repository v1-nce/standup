import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { Composer } from "../app/components/Composer";

const type = (value: string) =>
  fireEvent.change(screen.getByLabelText("What do you need to present?"), { target: { value } });

test("sending hands over the trimmed request and clears the field", () => {
  const sent = vi.fn();
  render(<Composer onSend={sent} />);

  type("  standup tomorrow  ");
  fireEvent.click(screen.getByRole("button", { name: "Send" }));

  expect(sent).toHaveBeenCalledWith("standup tomorrow");
  expect(screen.getByLabelText("What do you need to present?")).toHaveProperty("value", "");
});

test("an empty request is not sent", () => {
  const sent = vi.fn();
  render(<Composer onSend={sent} />);

  type("   ");
  fireEvent.click(screen.getByRole("button", { name: "Send" }));

  expect(sent).not.toHaveBeenCalled();
});
