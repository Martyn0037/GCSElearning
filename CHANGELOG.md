# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added — Phase 4 (Memory and mistakes)
- **Mistakes:** every wrong or full-solution answer creates (or re-opens) a mistake, with his answer, the correct answer and a review schedule.
- **"Where it went wrong":**
  - A Sonnet explanation that refers to his actual answer, with a misconception label.
  - Written in the background and shown within seconds.
  - His answer is sent only as delimited data, with no personal data.
- **"Try a similar one":** straight after a wrong answer, another question on the same skill.
- **Spaced review:** mistakes return after 1, 3, 7 and 14 days (London calendar days) until right twice in a row. The home page shows "Review N mistakes" and there's a review mode.
- **BKT mastery** per skill, updated on every answer.
- **"My mistakes" page:** counts by topic and misconception; each mistake with its explanation and next review date; paging; a Fixed tab.
- **Progress page:** mastery by topic, a 30-day activity chart with a table view, and the strongest skills and skills to work on.
- **Docs:** ADR-015; migration 0004; the end-to-end test now covers "My mistakes" and the progress page.

### Fixed
- Token times are now judged by the app's clock throughout. PyJWT's own issued-at check used the system clock.
- Mastery can no longer get stuck at 100%, where wrong answers would have stopped counting.
- Topic accuracy now comes from the answer records, so it can't disagree with the activity chart.

### Added — Phase 3 (Question engine)
- **Claude gateway:**
  - Structured output checked with Pydantic plus rules, retried up to twice.
  - A per-process circuit breaker.
  - A daily and monthly budget in pounds, using reserve-then-settle with an advisory lock.
  - An `ai_usage` table recording tokens and cost for every call.
- **Question generation** (Haiku 5.5): one objective at one difficulty, with a marking key, worked solution and four-level hint ladder.
  - A second Haiku call independently verifies each question.
  - Numeric answers are re-computed by SymPy in a sandboxed subprocess.
  - Only questions that pass every check go live; strict mode holds them for admin approval.
- **Question bank and worker:**
  - A Postgres job queue with deduplication, backoff, dead letters and recovery of stuck jobs.
  - A `worker` Compose service with a heartbeat health check.
  - A periodic top-up keeps 3 unseen questions ready per objective and level.
  - Serving falls back to the bank only when Claude is unavailable or over budget.
- **Practice API:**
  - "Next question" resumes the open item and is safe to repeat.
  - The "I'm stuck" hint ladder; the fourth hint is the full solution, after which the answer counts as assisted.
  - Deterministic marking; answers are idempotent via `Idempotency-Key`.
  - The difficulty ladder (ADR-005).
  - "This looks wrong" flags hide a question.
- **Question screen:** maths rendered by KaTeX as MathML; big tap targets; hints; results with the worked solution and level changes; a reporting control. It's lazy-loaded.
- **Tools and tests:**
  - An evaluation command (`app.cli.eval_questions`) reports pass rates and rejected questions for spot-checking.
  - The Anthropic adapter is tested against recorded-style API responses.
  - Playwright covers login → answer → hint → wrong answer → next question.
- **Docs:** ADR-014; `.env.example` gains `ANTHROPIC_API_KEY`, budget caps and strict mode.

### Fixed
- An empty `ANTHROPIC_API_KEY=` now means "not configured" rather than a blank key.

### Added — Phase 2 (Curriculum)
- **Curriculum format:** `curriculum/` holds YAML files: a catalogue of boards and subjects, and one file per spec version. There's a template and a README on how to copy content from a spec PDF.
- **Worked example:** Pearson Edexcel GCSE Maths 1MA1 (Issue 2, June 2015), topic 1 Number (N1–N16). It's copied word for word, with the Foundation and Higher wording kept separately.
- **Import command:** `app.cli.import_curriculum`.
  - Strict validation, including keywords copied from the wording, a `TODO` block and reference checks.
  - Idempotent; removed statements are retired, not deleted.
  - Spec versions are pinned.
  - Pending subjects are switched on when their spec arrives.
  - It runs automatically in the `migrate` job.
- **Setup screen:** the student picks subjects from the catalogue, or types one in.
  - Each subject has a board (most common pre-selected, or "I don't know"), a tier ("Not sure" means Higher) and set texts (from the board's list, or typed).
  - Anything without an imported spec shows as "being set up" (ADR-012).
- **Student home and topic map:** subjects are listed with their status.
  - Topics are shown in study order and locked until covered at school.
  - Skill counts respect the student's tier.
- **Admin screen:**
  - subjects needing attention, with plain-language reasons and cursor paging
  - confirming or correcting board, tier and spec
  - converting typed-in subjects
  - matching or removing typed-in set texts
  - "covered at school" ticks and topic order
  - a list of imported specs
- **Testing:** Playwright end-to-end tests against the real stack, and a CI job that runs them.
- **Docs:** ADR-013 (curriculum versioning and import).

### Fixed
- After saving the setup screen, the app now goes to the home page instead of bouncing back to setup.

### Changed
- The seed command asks for any password not set in the environment, at a hidden prompt with confirmation, so seeding works the same in any shell (zsh, bash, PowerShell).

### Added — Phase 1 (Foundations)
- **Backend:** a FastAPI service under `/api/v1`.
  - Consistent error shape with trace IDs, structured JSON logging with redaction, and security headers.
  - Strict CORS allowlist; Prometheus `/metrics`; `/health/live` and `/health/ready`.
- **Auth:**
  - Students sign in with a username; guardians and admins with email.
  - Argon2id password hashing.
  - 15-minute JWT access tokens and rotating refresh tokens that detect reuse, all in httpOnly `SameSite=Strict` cookies, with CSRF double-submit.
  - Account lockout; per-IP and per-identifier login rate limits.
  - An audit log that stores IPs only as hashes.
- **Access rules:** roles (`student`, `guardian`, `admin`) are enforced on every endpoint.
  - Guardians can read only the students they're linked to.
  - Other users' data returns 404.
  - Admins can reset a student's password, which signs the student out everywhere.
- **Database:** Alembic migration `0001` creates `users`, `guardian_links`, `refresh_tokens`, `rate_limit_counters`, `audit_log` and `consents`.
- **Commands:** an idempotent account seed command, and an OpenAPI export command.
- **Frontend:** a React 19 + TypeScript + Tailwind shell.
  - Accessible login page and role-based routing.
  - Placeholder home pages for each role.
  - An Orval-generated client with runtime Zod validation, a shared refresh-and-retry, and timeouts.
- **Infrastructure:**
  - Docker Compose with Caddy (automatic TLS, CSP, and a SPA fallback), api, a migration job and Postgres 16.
  - Non-root, resource-limited containers with bounded log rotation.
- **CI:** lint, type-check, tests with coverage gates, OpenAPI and client drift checks, image build and Trivy scan. Dependabot.
- **Docs:** `docs/architecture-decisions.md` (ADR-001 to ADR-011) and `docs/project-context.md`.

### Security
- `.trivyignore` accepts CVE-2026-78661 (`golang.org/x/net/html` inside Caddy 2.11.9) until 2027-01-31. It isn't reachable, because templates and markdown are disabled.
- The API image upgrades OS packages at build time and removes `pip`, whose bundled libraries carry CVEs.
