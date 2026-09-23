import type { components } from "@/app/api/schema";

type Schemas = components["schemas"];
export type Project = Schemas["Project"];
export type Resource = Schemas["Resource"];
export type ChatMessage = Schemas["ChatMessage"];
export type Deck = Schemas["Deck"];
export type Job = Schemas["Job"];
export type Scored = Schemas["Scored"];
export type ModelStatus = Schemas["ModelStatus"];

const BASE = process.env.NODE_ENV === "development" ? "http://127.0.0.1:8000" : "";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    detail: string,
  ) {
    super(detail);
  }
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  const json = init?.body !== undefined && !(init.body instanceof FormData);
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: json ? { "content-type": "application/json" } : undefined,
  });
  if (response.ok) return response;

  const body: unknown = await response.json().catch(() => null);
  const detail = body && typeof body === "object" && "detail" in body ? body.detail : null;
  throw new ApiError(response.status, detail ? String(detail) : response.statusText);
}

const project = (id: string) => `/projects/${encodeURIComponent(id)}`;

const POLL_MS = 500;

export const reason = (failure: unknown): string =>
  failure instanceof Error ? failure.message : String(failure);

export const api = {
  listProjects: (): Promise<Project[]> => request("/projects").then((r) => r.json()),

  createProject: (name: string): Promise<Project> =>
    request("/projects", { method: "POST", body: JSON.stringify({ name }) }).then((r) => r.json()),

  renameProject: (id: string, name: string): Promise<Project> =>
    request(project(id), { method: "PATCH", body: JSON.stringify({ name }) }).then((r) => r.json()),

  deleteProject: (id: string): Promise<void> =>
    request(project(id), { method: "DELETE" }).then(() => undefined),

  listContext: (id: string): Promise<Resource[]> =>
    request(`${project(id)}/context`).then((r) => r.json()),

  addPaths: (id: string, locations: string[]): Promise<Job> =>
    request(`${project(id)}/context`, {
      method: "POST",
      body: JSON.stringify({ locations }),
    }).then((r) => r.json()),

  addFiles: (id: string, files: FileList | File[]): Promise<Job> => {
    const form = new FormData();
    for (const file of files) form.append("files", file);
    return request(`${project(id)}/context/files`, { method: "POST", body: form }).then((r) =>
      r.json(),
    );
  },

  removeContext: (id: string, resourceId: string): Promise<void> =>
    request(`${project(id)}/context/${encodeURIComponent(resourceId)}`, {
      method: "DELETE",
    }).then(() => undefined),

  readChat: (id: string): Promise<ChatMessage[]> =>
    request(`${project(id)}/chat`).then((r) => r.json()),

  sendMessage: (id: string, content: string): Promise<Job> =>
    request(`${project(id)}/chat`, { method: "POST", body: JSON.stringify({ content }) }).then(
      (r) => r.json(),
    ),

  awaitJob: async (jobId: string, signal?: AbortSignal): Promise<Job> => {
    const where = `/jobs/${encodeURIComponent(jobId)}`;
    for (;;) {
      const job: Job = await request(where, { signal }).then((r) => r.json());
      if (job.state !== "running" || signal?.aborted) return job;
      await new Promise((wake) => setTimeout(wake, POLL_MS));
    }
  },

  readDeck: (id: string): Promise<Deck | null> =>
    request(`${project(id)}/deck`)
      .then((r) => r.json())
      .catch((failure: unknown) => {
        if (failure instanceof ApiError && failure.status === 404) return null;
        throw failure;
      }),

  getModel: (): Promise<ModelStatus> => request("/model").then((r) => r.json()),

  setModelKey: (apiKey: string): Promise<ModelStatus> =>
    request("/model/key", { method: "POST", body: JSON.stringify({ api_key: apiKey }) }).then(
      (r) => r.json(),
    ),
};
