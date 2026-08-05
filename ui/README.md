# Standup — UI

GUI source. Next.js (App Router), React, TypeScript, Tailwind.

**This is not a deployed half.** `npm run build` static-exports it and stages the files into
`../src/standup/web/`, which the Python package serves. There is no separate deploy step and no
Node process in the shipped product.

```powershell
npm install
npm run dev      # http://localhost:3000, expects the API on :8000
npm test
npm run build    # export, then stage into the package
```

`output: "export"` in [next.config.ts](next.config.ts) is not optional — no SSR, no server
components, no route handlers. `distDir` can't point outside the project in Next 16, so the
`stage` script copies instead.

API types should be generated from the backend's OpenAPI schema with `openapi-typescript` when
the first screen starts calling it. A hand-written interface mirroring a Pydantic model is a bug.
