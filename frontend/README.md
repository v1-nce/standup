# Frontend

Not built. Next.js (App Router), React, TypeScript, Tailwind, shadcn/ui — see
[CLAUDE.md](../CLAUDE.md) § Stack.

API types are **generated** from the backend's OpenAPI schema via `openapi-typescript`. A
hand-written interface mirroring a Pydantic model is a bug.

Open question 1 constrains this before any code is written: if the Python process serves the
frontend so Standup installs in one command, Next.js has to be a static export — no SSR, no
server components, no route handlers.
