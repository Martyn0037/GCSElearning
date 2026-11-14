# GCSE Coach — frontend

React 19, TypeScript (strict), Vite, React Router, TanStack Query, Zod and Tailwind CSS 4.
Mobile-first.

## Layout
```
src/
  api/http.ts         the one HTTP client: CSRF, refresh-and-retry, timeouts, Zod validation, ApiError
  api/generated/      Orval output from openapi.json — never edit by hand
  app/                routes, query client
  auth/               session hooks, route guard, role → home mapping
  components/         shared UI
  setup/              subject setup screen (choices model + UI)
  subjects/           student home and topic map
  admin/              admin screen
  pages/              login, guardian placeholder, not found
  test/               test setup, fake API, render helpers
```

## Local setup

1. Install dependencies:

   ```bash
   npm ci
   ```

2. Start the dev server on <http://localhost:5173>:

   ```bash
   npm run dev
   ```

The dev server proxies `/api` to `http://localhost:8000`, so start the backend first (see `backend/README.md`). To point it somewhere else, set `VITE_API_PROXY_TARGET`.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_PROXY_TARGET` | `http://localhost:8000` | Dev-server proxy target for `/api` (development only) |

Nothing secret is ever built into the frontend.

## Tests and checks

| Command | What it does |
|---|---|
| `npm test` | Vitest + React Testing Library |
| `npm run test:coverage` | The same, with the coverage gate (90% lines, 85% branches) |
| `npm run lint` | ESLint (`strictTypeChecked`) |
| `npm run typecheck` | TypeScript, no emit |
| `npm run build` | Production build into `dist/` |
| `npm run test:e2e` | Playwright end-to-end tests against the running stack (see `e2e/README.md`) |

## API client

After the backend's endpoints change, export `openapi.json` from the backend (see `backend/README.md`), then regenerate the client:

```bash
npm run api:generate
```

CI runs `npm run api:check` and fails if the generated client is stale.
