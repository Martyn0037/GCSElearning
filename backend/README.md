# GCSE Coach — backend

FastAPI service exposing `/api/v1`. Python 3.12+, async SQLAlchemy on PostgreSQL 16,
Alembic migrations, dependencies managed with [uv](https://docs.astral.sh/uv/).

## Layout
```
app/
  core/     config, logging, errors, middleware, metrics, clock, shared schemas
  db/       declarative base, engine/session
  models/   ORM models (users, refresh_tokens, rate_limit_counters, audit_log, consents)
  auth/     passwords, tokens, cookies, rate limiting, audit, service, router
  users/    /users endpoints (ownership rules)
  admin/    /admin endpoints (admin role only)
  health/   /health/live, /health/ready, /metrics (internal only)
  cli/      seed_users, export_openapi
alembic/    migrations
tests/      unit/, integration/ (real Postgres), fixtures/
```

## Local setup

1. Install dependencies, including the dev tools:

   ```bash
   uv sync
   ```

2. Start a throwaway Postgres for development:

   ```bash
   docker run -d --name gc-dev-pg -e POSTGRES_USER=gcse -e POSTGRES_PASSWORD=devpass -e POSTGRES_DB=gcse -p 5432:5432 postgres:16-alpine
   ```

3. Create `backend/.env` (it's git-ignored) with these values:

   ```
   ENVIRONMENT=development
   DATABASE_URL=postgresql+asyncpg://gcse:devpass@localhost:5432/gcse
   JWT_SECRET=<openssl rand -base64 48>
   AUDIT_IP_SALT=<openssl rand -base64 48>
   COOKIE_SECURE=true
   CORS_ORIGINS=http://localhost:5173
   ```

   `COOKIE_SECURE=true` is fine on `http://localhost`: browsers treat localhost as a secure context.

4. Run the migrations:

   ```bash
   uv run alembic upgrade head
   ```

5. Seed the accounts. It asks for each password at a hidden prompt, unless `SEED_ADMIN_PASSWORD`, `SEED_GUARDIAN_PASSWORD` or `SEED_STUDENT_PASSWORD` is set:

   ```bash
   uv run python -m app.cli.seed_users --admin-email you@example.com --guardian-email guardian@example.com --guardian-name Alex --student-username sam10 --student-name Sam
   ```

6. Start the API with auto-reload:

   ```bash
   uv run uvicorn app.main:create_app --factory --reload
   ```

Interactive API docs are at <http://localhost:8000/api/docs> outside production.

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | yes | — | `postgresql+asyncpg://…` |
| `JWT_SECRET` | yes | — | Signs access tokens (at least 32 characters) |
| `AUDIT_IP_SALT` | yes | — | Key for hashing IPs in the audit log (at least 32 characters) |
| `ENVIRONMENT` | no | `development` | `development` / `test` / `production`; production turns off the API docs |
| `CORS_ORIGINS` | no | none | Comma-separated exact origins; `*` is rejected |
| `COOKIE_SECURE` | no | `true` | `Secure` attribute on auth cookies |
| `LOG_LEVEL` | no | `INFO` | Root log level |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | no | `5` / `5` | Connection pool per process |
| `DB_STATEMENT_TIMEOUT_MS` | no | `5000` | Server-side statement timeout |
| `ACCESS_TOKEN_TTL_SECONDS` | no | `900` | Access token lifetime |
| `REFRESH_TOKEN_TTL_SECONDS` | no | `1209600` | Refresh token lifetime (14 days) |
| `LOGIN_MAX_FAILURES` / `LOGIN_LOCKOUT_SECONDS` | no | `5` / `900` | Account lockout |
| `LOGIN_IP_LIMIT_PER_MINUTE` | no | `10` | Login attempts per IP per minute |

## Tests

Run everything with the coverage gate (90%, branch coverage on):

```bash
uv run pytest --cov
```

Run only the unit tests (no database needed):

```bash
uv run pytest tests/unit
```

Integration tests start a Postgres container with testcontainers, which needs Docker. To reuse an existing database instead, set `TEST_DATABASE_URL`. Every table in it is truncated between tests, so point it at a database you can wipe:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://gcse:devpass@localhost:5432/gcse_test uv run pytest
```

Run the formatter, linter and type checker:

```bash
uv run ruff format . && uv run ruff check . && uv run mypy
```

## Migrations

Create a new migration after changing models, then review the generated file by hand:

```bash
uv run alembic revision --autogenerate -m "describe change" --rev-id 0002
```

Every migration needs a working `downgrade()`. An integration test checks the round trip, and checks that the models match the migrated schema.

## OpenAPI

The frontend generates its client from `frontend/openapi.json`. Regenerate it whenever endpoints change (CI fails if it's stale):

```bash
uv run python -m app.cli.export_openapi ../frontend/openapi.json
```
