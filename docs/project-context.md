# Project context — GCSE Coach

## Goal
An AI tutor that guides, helps, tests and remembers for one Year 10 student in England
(exams summer 2028). It works on his current reformed (9–1) GCSE specifications, each pinned
to an exact spec code and version. It's mobile-first, and he should be answering a question
within 2 taps of logging in.

## Users
- **Student**: first name or nickname only, and a username login (no email).
- **Guardian**: a read-only progress dashboard, linked to the student.
- **Admin**: curriculum import, review queue and costs. Resets the student's password.

## Student and syllabus (to be filled in before Phase 2)
| Item | Value |
|---|---|
| Display name | _TBD_ |
| Subjects (board, spec code, version, tier) | _TBD_ |
| English Literature set texts | _TBD_ |
| Primary device | _TBD_ (default: mobile-first, works on laptop) |
| Budget | £25/month for the Claude API, about £10–15 for hosting |

The student picks his own subjects, boards, tiers and set texts on first login
(ADR-012). Anything not matched to an imported spec waits for the admin; no
questions are generated for it until then.

Curriculum content comes **only** from the board's spec PDFs, copied word for word with
references. Anything unclear is marked `TODO`; nothing is invented.

## Stack
- **Backend:**
  - Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 (async, asyncpg), Alembic, PostgreSQL 16
  - argon2-cffi, PyJWT, prometheus-client
  - `uv` for dependencies, with `uv.lock` committed
- **Frontend:**
  - React 19, TypeScript (strict), Vite, React Router, TanStack Query 5, Zod 4, Tailwind CSS 4
  - Orval-generated API client
- **Claude (from Phase 3):**
  - The official `anthropic` SDK. `claude-haiku-5-5` handles generation and verification; `claude-sonnet-5-5` handles marking, explanations and chat. Model names are set in config.
- **Hosting:** one Lightsail instance running Docker Compose (Caddy, api, migrate, Postgres, plus the worker from Phase 3).

## Conventions
- Every file starts with a comment giving its path.
- Python: `mypy --strict` and ruff must pass. Docstrings are Google style.
- TypeScript: `strictTypeChecked` ESLint and Prettier (width 100) must pass.
- API:
  - Everything lives under `/api/v1`.
  - The wire format is camelCase.
  - Unknown fields are rejected.
  - Errors use one shape: `{"error": {"code", "message", "traceId"}}`.
  - Unauthorised reads of another user's data return **404**, not 403.
- Each service method is a unit of work and commits explicitly, so security state persists even when the request fails.
- Time comes from an injectable `Clock`, so tests stay deterministic.
- Tests:
  - Names describe behaviour, and each test follows Arrange / Act / Assert.
  - Every test file starts with a comment block listing the scenarios it covers.
  - Backend unit tests sit in `backend/tests/unit`, integration tests in `backend/tests/integration` (real Postgres), and shared factories in `backend/tests/fixtures`.
  - Frontend tests sit next to the code they test (`*.test.ts(x)`).
- Coverage gates: backend 90% lines (branch coverage on). Frontend 90% lines and 85% branches.

## Build phases
1. Foundations ✅
2. Curriculum
3. Question engine
4. Memory and mistakes
5. Gamification
6. Extended answers and tutor chat
7. Guardian and admin tools
8. Production

See `docs/architecture-decisions.md` for the decisions behind all of this.
