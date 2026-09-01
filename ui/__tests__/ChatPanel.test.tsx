import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { ChatPanel } from "../app/components/ChatPanel";

test("a command entry is not shown as something someone said", () => {
  render(
    <ChatPanel
      messages={[
        { role: "user", content: "drop the second slide", at: "2026-08-14T00:00:00Z" },
        { role: "command", content: "keep(['a']) -> 1 chosen, all written", at: "2026-08-14T00:00:01Z" },
        { role: "assistant", content: "Done.", at: "2026-08-14T00:00:02Z" },
      ]}
      pending={false}
    />,
  );

  expect(screen.getByText("drop the second slide")).toBeDefined();
  expect(screen.getByText("Done.")).toBeDefined();
  expect(screen.queryByText(/keep\(/)).toBeNull();
});
