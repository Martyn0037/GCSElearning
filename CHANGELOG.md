# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
