import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import Page from "../app/page";

const status = (configured: boolean) => ({
  provider: configured ? "anthropic" : null,
  model: configured ? "claude-opus-5" : "",
  configured,
  via_gateway: false,
  models: configured ? ["claude-opus-5", "claude-sonnet-5", "claude-haiku-5"] : [],
});

test("a first run shows the connect form and hides it once a key lands", async () => {
  let configured = false;
  const fetched = vi.fn((url: string, init?: RequestInit) => {
    if (url.endsWith("/model/key") && init?.method === "POST") {
      configured = true;
      return Promise.resolve(Response.json(status(true)));
    }
    if (url.endsWith("/model")) return Promise.resolve(Response.json(status(configured)));
    if (url.endsWith("/projects")) return Promise.resolve(Response.json([]));
    if (url.endsWith("/chat")) return Promise.resolve(Response.json([]));
    if (url.endsWith("/deck")) {
      return Promise.resolve(new Response(JSON.stringify({ detail: "No deck yet" }), { status: 404 }));
    }
    return Promise.resolve(Response.json({}));
  });
  vi.stubGlobal("fetch", fetched);

  render(<Page />);

  const input = await screen.findByLabelText("Model API key");
  fireEvent.change(input, { target: { value: "sk-ant-key" } });
  fireEvent.click(screen.getByRole("button", { name: "Connect" }));

  await waitFor(() => expect(screen.queryByLabelText("Model API key")).toBeNull());
  expect(
    fetched.mock.calls.some(([url, init]) => String(url).endsWith("/model/key") && init?.method === "POST"),
  ).toBe(true);
});

test("a rejected key keeps the form and surfaces the error", async () => {
  const fetched = vi.fn((url: string, init?: RequestInit) => {
    if (url.endsWith("/model/key") && init?.method === "POST") {
      return Promise.resolve(
        new Response(JSON.stringify({ detail: "Could not detect the provider from that key." }), {
          status: 400,
        }),
      );
    }
    if (url.endsWith("/model")) return Promise.resolve(Response.json(status(false)));
    if (url.endsWith("/projects")) return Promise.resolve(Response.json([]));
    if (url.endsWith("/chat")) return Promise.resolve(Response.json([]));
    if (url.endsWith("/deck")) {
      return Promise.resolve(new Response(JSON.stringify({ detail: "No deck yet" }), { status: 404 }));
    }
    return Promise.resolve(Response.json({}));
  });
  vi.stubGlobal("fetch", fetched);

  render(<Page />);

  const input = await screen.findByLabelText("Model API key");
  fireEvent.change(input, { target: { value: "nonsense" } });
  fireEvent.click(screen.getByRole("button", { name: "Connect" }));

  expect(await screen.findByText("Could not detect the provider from that key.")).toBeDefined();
  expect(screen.getByLabelText("Model API key")).toBeDefined();
});
