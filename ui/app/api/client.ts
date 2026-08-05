import type { components } from "@/app/api/schema";

export type Project = components["schemas"]["Project"];

const BASE = process.env.NODE_ENV === "development" ? "http://127.0.0.1:8000" : "";

async function request(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: init?.body ? { "content-type": "application/json" } : undefined,
  });
  if (response.ok) return response;

  const body: unknown = await response.json().catch(() => null);
  const detail = body && typeof body === "object" && "detail" in body ? body.detail : null;
  throw new Error(detail ? String(detail) : response.statusText);
}

export const api = {
  listProjects: (): Promise<Project[]> => request("/projects").then((r) => r.json()),

  renameProject: (id: string, name: string): Promise<Project> =>
    request(`/projects/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }).then((r) =>
      r.json(),
    ),

  deleteProject: (id: string): Promise<void> =>
    request(`/projects/${id}`, { method: "DELETE" }).then(() => undefined),
};
