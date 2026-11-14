# GCSE Coach

An AI tutor that guides, tests and remembers for one Year 10 student, built on the
current reformed (9–1) GCSE specifications. See [`docs/project-context.md`](docs/project-context.md)
for goals and conventions, and [`docs/architecture-decisions.md`](docs/architecture-decisions.md)
for the decisions behind the design.

```
backend/    FastAPI API, Alembic migrations, CLI commands          → backend/README.md
frontend/   React + TypeScript app (served by Caddy in production) → frontend/README.md
infra/      Caddy configuration (backup scripts arrive in Phase 8)
docs/       Project context, architecture decisions
```

## Run the whole stack locally (closest to production)

You need Docker with the Compose plugin.

1. Create your environment file:

   ```bash
   cp .env.example .env
   ```

2. Fill in `POSTGRES_PASSWORD`, `JWT_SECRET` and `AUDIT_IP_SALT` in `.env`. Generate each value with this command:

   ```bash
   openssl rand -base64 48
   ```

3. Restrict who can read the file:

   ```bash
   chmod 600 .env
   ```

4. Build and start everything:

   ```bash
   docker compose up -d --build
   ```

5. Create the admin, guardian and student accounts. The seed command reads the three passwords (at least 10 characters each) from environment variables, so they never appear in shell history or in `.env`. Enter each one at a prompt:

   ```bash
   read -rsp "Admin password: " SEED_ADMIN_PASSWORD && echo && export SEED_ADMIN_PASSWORD
   ```

   ```bash
   read -rsp "Guardian password: " SEED_GUARDIAN_PASSWORD && echo && export SEED_GUARDIAN_PASSWORD
   ```

   ```bash
   read -rsp "Student password: " SEED_STUDENT_PASSWORD && echo && export SEED_STUDENT_PASSWORD
   ```

   Then run the seed command:

   ```bash
   docker compose run --rm -e SEED_ADMIN_PASSWORD -e SEED_GUARDIAN_PASSWORD -e SEED_STUDENT_PASSWORD api python -m app.cli.seed_users --admin-email you@example.com --guardian-email guardian@example.com --guardian-name Alex --student-username sam10 --student-name Sam
   ```

   Running it again updates the same accounts; it never creates duplicates.

6. Open <https://localhost> and sign in. Your browser will warn about Caddy's local certificate the first time; that's expected for `localhost`.

## Develop with hot reload

Run the API and the frontend separately. See [`backend/README.md`](backend/README.md) and
[`frontend/README.md`](frontend/README.md). The Vite dev server proxies `/api` to the API on
port 8000, so cookies behave the same as in production.

## Tests

| Where | Command | What runs |
|---|---|---|
| `backend/` | `uv run pytest --cov` | Unit and integration tests (real Postgres via testcontainers); 90% coverage gate |
| `frontend/` | `npm run test:coverage` | Vitest + React Testing Library; 90% lines / 85% branches gate |

CI (`.github/workflows/ci.yml`) also runs lint, type checks, OpenAPI and client drift checks,
the image build, and a Trivy scan.
