# Architecture decisions

A log of the significant technical decisions and why they were made. Each entry is
**Accepted** unless marked otherwise. To change a decision, add a new entry that
supersedes the old one; don't edit history.

---

## ADR-001 — Docker Compose on one Lightsail instance, not Kubernetes

**Status:** Accepted (2026-11-14). **This is a deliberate exception to the standing
engineering rule that every service ships with Kubernetes manifests.**

**Context.** The app serves one student, one guardian and one admin. The budget is about £10–15 a month
for hosting. A managed Kubernetes control plane on its own costs more than the whole budget,
and running it would cost more effort than the rest of the system.

**Decision.** Run everything on one AWS Lightsail instance with Docker Compose: `caddy`
(TLS, static app, `/api` reverse proxy), `api`, a one-shot `migrate` job and
`postgres`. The `worker` service will be added in Phase 3.

**Kept from the standing rules**, so a later move to Kubernetes is cheap:
- The services are stateless and containerised. All state lives in Postgres, with no in-process sessions or caches that hold correctness.
- Config comes only from the environment, with nothing baked into images.
- Each container has health endpoints (`/health/live`, `/health/ready`), resource limits, a non-root user, a read-only root filesystem (api) and `no-new-privileges`.
- The API can run as several processes (2 Uvicorn workers today), so rate limits and refresh-token state live in the database.

**Consequences.** There's a single point of failure: it's accepted, mitigated by nightly
`pg_dump` to S3 plus Lightsail snapshots (Phase 8). There's no rolling deploy, so deploys
cause a few seconds of downtime, which is acceptable for this user base.

**Revisit if** there are more than about 50 active users, uptime needs above about 99%, or more than one
host is needed.

---

## ADR-002 — Secrets in a `chmod 600` `.env` file; SSM Parameter Store as the upgrade path

**Status:** Accepted (2026-11-14). This is an exception to the standing "dedicated secrets manager" rule.

**Context.** Lightsail instances can't take an IAM instance role. Reading SSM Parameter Store
from the box would need a long-lived AWS access key stored on the same box. That only
moves the secret: whoever can read `.env` could read the key too.

**Decision.** Keep secrets in `.env` next to `docker-compose.yml`, owned by the deploy
user, with `chmod 600`. Never commit it (it's in `.gitignore`); `.env.example` documents
every variable. The API refuses to start if `JWT_SECRET` or `AUDIT_IP_SALT` is shorter than
32 characters, so placeholder values can't reach production.

**Upgrade path.** Move to SSM Parameter Store (SecureString) if the app moves to EC2/ECS
with an instance or task role. The code needs no change, because settings are read from the environment.

**Rotation.**
- `JWT_SECRET`: rotating it signs everyone out, and nothing else.
- `AUDIT_IP_SALT`: rotating it breaks correlation with older audit rows, which is acceptable.
- Postgres password: rotate it with `ALTER USER`, then update `.env`.

---

## ADR-003 — Postgres-backed job queue (no Redis)

**Status:** Accepted (2026-11-14); implementation lands in Phase 3.

**Decision.** Use a small `jobs` table that the worker claims from with
`SELECT … FOR UPDATE SKIP LOCKED`. It has retries with exponential backoff and a dead-letter status for
jobs that keep failing. About 200 lines that we own and test.

**Trade-offs.**
- (+) No extra service to run or back up.
- (+) Jobs are transactional with the data they relate to.
- (+) One database driver.
- (−) The worker checks for jobs every few seconds. That's negligible at one student, and
  `LISTEN/NOTIFY` can be added if latency matters.
- (−) We maintain the queue ourselves.

**Rejected alternatives.**
- `procrastinate`: mature, but needs a second driver (psycopg 3) and its own schema.
- ARQ + Redis: another stateful service.

---

## ADR-004 — Rate limiting with fixed-window counters in Postgres

**Status:** Accepted (2026-11-14). Implemented in Phase 1.

**Decision.** `rate_limit_counters(key, window_start, count)` is incremented with one atomic
`INSERT … ON CONFLICT DO UPDATE … RETURNING count`. The increment commits immediately,
so a rejected request still counts.

**Limits in force.**
- Login: 10 per minute per IP, plus 20 per hour per identifier.
- Refresh: 30 per minute per IP.
- An account locks for 15 minutes after 5 failed logins.

**Trade-offs.**
- (+) Limits are shared across API processes and survive restarts.
- (−) Fixed windows allow up to 2× the limit across a window boundary. That's acceptable
  for brute-force protection when combined with account lockout.
- (−) One extra write per limited request.
- Old windows are purged by `rate_limit.purge_expired`, which the worker will run on a schedule (Phase 3).

---

## ADR-005 — Mastery with Bayesian Knowledge Tracing, kept separate from the level ladder

**Status:** Accepted (2026-11-14); implementation lands in Phase 3/4.

**Decision.** Use BKT with fixed default parameters for each difficulty level (no fitting) to estimate
P(mastered) per learning objective. This drives the mastery rings and "exam ready".

The **level ladder** is a separate rule-based state machine:
- Up a level after 3 correct in a row, or 80% of the last 5.
- Down a level after 2 misses in a row at the same level.

**Why.**
- BKT updates with a simple formula, so tests can assert exact hand-calculated values.
- It's easy to explain: "85% sure he's got this".
- Elo would also rate question difficulty, but one student never produces enough attempts
  for question ratings to settle.

---

## ADR-006 — Fixed-interval review scheduler behind an interface

**Status:** Accepted (2026-11-14); implementation lands in Phase 4.

**Decision.** A `ReviewScheduler` protocol, with `FixedIntervalScheduler` as the first implementation:
- It brings a mistake back after 1, 3, 7 and 14 days.
- The mistake is resolved after 2 correct answers in a row.
- Days are calendar days in Europe/London.

FSRS (`py-fsrs`) can be swapped in later without changing the code that uses the scheduler.

---

## ADR-007 — Students sign in with a username; no student email

**Status:** Accepted (2026-11-14).

**Context.** The student is a minor. The UK GDPR and the Age Appropriate Design Code
favour data minimisation.

**Decision.**
- Students have a username and password, and no email is stored.
- Guardians and admins sign in with email.
- A database `CHECK` constraint enforces this split, and that usernames and emails are stored lower-case.
- Student password resets are done by the admin (`POST /api/v1/admin/students/{id}/password`). A reset also signs the student out on every device.

---

## ADR-008 — Grades shown only as a band

**Status:** Accepted (2026-11-14); used from Phase 5.

**Decision.** An admin-editable `grade_boundaries` table is filled from the exam board's published boundaries.
- Estimates are always shown as a band ("around 5–6"), never a single grade, and labelled as an estimate.
- Until boundaries exist, the app shows a percentage and "secure / developing / not yet".

---

## ADR-009 — Right-sized observability

**Status:** Accepted (2026-11-14). This is a partial exception to the standing observability rules.

**Kept:**
- Structured JSON logs on stdout with `timestamp`, `level`, `service`, `environment`, `trace_id` and `span_id`.
- A trace ID from `X-Trace-Id`/`X-Request-ID` if it's well-formed, otherwise generated. It's returned on every response and included in every error body.
- Redaction of sensitive keys, including passwords, tokens, cookies, emails and the student's answers.
- Prometheus `/metrics` with request count and latency by route template, DB pool saturation and login outcomes.
- `/health/live` and `/health/ready`.

**Skipped:** an OpenTelemetry collector and distributed tracing backend. With only one service
calling Claude, trace IDs in logs are enough.

**Retention:**
- Docker `json-file` rotation (20 MB × 10 files per service) keeps more than 30 days at this volume.
- Database backups are kept for 30 days in S3 (Phase 8).
- The audit log stays in Postgres.

---

## ADR-010 — Session tokens in httpOnly cookies, with CSRF double-submit

**Status:** Accepted (2026-11-14). Implemented in Phase 1.

**Decision.**
- **Access token:** a JWT (HS256) that lasts 15 minutes. Its signature, expiry, issuer and audience are checked on every request, and the user is re-loaded so deactivation takes effect immediately. Cookie: `gc_access`, `Path=/api`.
- **Refresh token:** 256 random bits that last 14 days. Only its SHA-256 is stored. Cookie: `gc_refresh`, `Path=/api/v1/auth`.
  - It rotates on every use.
  - Presenting an already-rotated token revokes the whole token family (theft detection).
  - Reuse within 10 seconds of a rotation is treated as a two-tab race (`REFRESH_RACE`) and doesn't revoke anything.
- **CSRF token:** the `gc_csrf` cookie is readable by JavaScript, and the client echoes it in `X-CSRF-Token` on every non-GET request.
- All cookies are `Secure` and `SameSite=Strict`.

**Trade-off.** Access JWTs are stateless, so logout can't kill an access token that has already been issued.
It stays valid for up to 15 minutes. Deactivating an account cuts access immediately, because the user is re-checked on every request.

---

## ADR-011 — OpenAPI-generated client (Orval) with runtime Zod validation

**Status:** Accepted (2026-11-14).

**Decision.**
- The backend's OpenAPI document is exported to `frontend/openapi.json`. Orval generates TanStack Query hooks and Zod schemas from it into `src/api/generated/`.
- The single fetch client, `src/api/http.ts`, validates every response against its schema. It also handles CSRF, the shared refresh-and-retry, timeouts and the `ApiError` type.
- CI fails if either generated artefact is out of date.

**Trade-off.** It adds one dev dependency (Orval, which is actively maintained) but removes hand-written
API types that could drift from the backend.

---

## ADR-012 — Student chooses subjects and set texts; no questions without an imported spec

**Status:** Accepted (2026-11-14); implementation lands in Phase 2.

**Context.** The student should choose his own subjects, add ones that aren't listed,
and name the books he's studying. The brief's core accuracy rule (section 4) says
curriculum content comes only from the exam board's spec, never from model knowledge.

**Decision (option A).**
- On first login, a setup screen asks for:
  - his subjects, from a catalogue, plus an "Other" free-text box
  - the board and tier for each subject, picked from lists, or "I don't know"
  - for English Literature, his set texts, picked from the board's official set-text lists, plus "Other"
- Anything that can't be matched to an imported spec becomes a **pending request** in the admin area. This covers "Other" subjects, texts not on a list and unknown boards.
  - The subject or text shows as "being set up" to the student.
  - **No questions are generated for it** until the admin imports that spec (or set-text list) and confirms the match.
- Questions are always generated per learning objective. For set texts, objectives are scoped to his chosen texts, using text names from the spec and never invented plot or quotation content.

**Rejected (option B).** Letting typed-in subjects and texts be used straight away from model knowledge, labelled "unverified". It's faster, but questions could drift off-spec or be wrong, which undermines the app's core promise.

**Consequences.** Each extra subject means the admin loads one spec PDF. Claude can usually fetch it from the board's site, but the admin checks the version. The student can wait a little for an unusual subject.

---

## ADR-013 — Curriculum as versioned YAML, imported idempotently on every start

**Status:** Accepted (2026-11-14). Implemented in Phase 2.

**Decision.**
- Each spec version is one YAML file under `curriculum/specs/`, with the exact version
  string printed in the PDF footer. Specs are unique by (board, code, version). Only one version per board and code is *current*.
- The `migrate` job runs `python -m app.cli.import_curriculum /app/curriculum` after the Alembic migrations on every start.
  - Every file is validated first. If any file is invalid, nothing is written.
  - Re-running changes nothing.
- Statements removed from a file are **retired** (`retired_at`), not deleted, because later phases' attempts and mistakes reference them.
- A student's subject is pinned to the spec version it was matched to. A new current version applies to new and pending subjects only; the admin moves existing ones explicitly.
- Validation enforces "nothing invented":
  - every keyword must appear in the statement's own wording
  - `TODO` anywhere in a file blocks the import
  - Higher wording is stored only where it differs from Foundation
- Tiers are derived by comparing the Foundation and Higher sections of the PDF, because text extraction loses the bold that marks Higher-only content.

**Trade-offs.**
- (+) Content changes are reviewable diffs in git, and deploys can't half-apply them.
- (+) The app always matches the repo.
- (−) Editing content needs a commit and a restart rather than an admin web form. That's acceptable for one admin; an upload form can be added later and would reuse the same importer.

---

## ADR-014 — Question pipeline: constrained generation, independent verification, bank first

**Status:** Accepted (2026-11-14). Implemented in Phase 3.

**Decision.**
- **Generation** (`claude-haiku-5-5`, set in config):
  - Each call covers one learning objective at one difficulty and one question type.
  - The prompt holds only curriculum facts from the repo: the objective's wording for the student's tier, keywords, out-of-scope notes, the difficulty description and allowed command words. No student data is ever sent.
  - Output is structured JSON, checked by Pydantic and by rules, with up to 2 retries. The rules cover the type's fields, four hints, hints 1–3 not containing the answer, no HTML, an allowed command word, and 1–6 marks.
- **Verification** (a second Haiku call):
  - It solves the question *before* reading the key, then checks correctness, scope, tier, difficulty, hints and mark-scheme consistency, and gives a confidence.
  - The app also compares the verifier's own answer with the key, regardless of its yes/no verdict.
- **SymPy** re-computes numeric answers from a `check_expression`. The expression must match an allowlist (digits, operators, `sqrt`, `pi`) and runs in an isolated `python -I` subprocess with a 5-second timeout, because the expression comes from the model.
- A question goes **live** only if every check passes and confidence ≥ 0.8 (configurable).
  - Strict mode holds new questions for admin approval.
  - Rejected questions are kept, but never served, for the evaluation report.
- **The bank comes first.** Students are served from stored questions. The worker tops up each objective the student can practise (current level and the next) to 3 unseen questions. On-the-spot generation happens only when the bank is empty, limited to 25 seconds.
  - Without a key, over budget, or with the circuit open, the app serves the bank only. If the bank is empty it says "preparing questions" and queues the work.
- **Spending:**
  - Each call reserves its worst-case cost under a Postgres advisory lock before running.
  - Daily and monthly caps are set in pounds and converted to dollars at a deliberately high rate.
  - Every call is recorded (tokens, cost, request ID); prompts and answers are never stored.
- **Marking** of multiple choice, numeric (with tolerance, fractions and units) and short text is deterministic: no AI is involved in marking these types.
- **Maths display:** KaTeX in MathML mode with `trust: false`.
  - Browsers render MathML natively, so the CSP needs no inline-style exception and no fonts.
  - Plain text is escaped by React.
  - The practice screen is code-split, so KaTeX loads only when needed.

**Trade-offs.**
- Two model calls per question roughly doubles generation cost, but on Haiku 5.5 it's around a tenth of a penny per question.
- A strict verifier rejects some good questions, so the bank fills more slowly, which pre-generation hides.
- MathML rendering is slightly less polished than KaTeX's HTML mode.

---

## ADR-015 — Mistakes, explanations and review

**Status:** Accepted (2026-11-14). Implemented in Phase 4.

**Decision.**
- **One `mistakes` row per open student-and-question pair** (a partial unique index).
  - A wrong or full-solution answer opens one.
  - Missing the same question again re-opens it with a fresh schedule rather than duplicating it.
  - The review schedule is stored on the mistake, because each mistake has exactly one schedule. That replaces the separate `review_schedule` table in the brief's data model.
- **Reviews** use the `ReviewScheduler` interface (ADR-006): 1, 3, 7 and 14 London calendar days, fixed after two right in a row, back to tomorrow when wrong.
  - A review re-asks the same question.
  - Review answers update mastery but not the difficulty ladder.
- **"Where it went wrong"** explanations are written by Sonnet in a background job, so marking stays instant. The screen checks for the explanation every 2 seconds and stops after 20 checks.
  - Prompt-injection hygiene: the student's answer (at most 200 characters, angle brackets and control characters stripped) is the only student text sent. It's placed inside `<student_answer>` tags, which the system prompt says are data, never instructions.
  - No name, username or other personal data is included.
  - The output is checked for length and markup before it's shown.
  - Misconception labels are lower-cased and the student's earlier labels are offered for reuse, so grouping stays consistent.
  - Without Claude, the status is `unavailable` and the worked solution still shows.
- **BKT mastery** is stored on `objective_progress` (one row per student and objective, so no separate `mastery` table). It's kept between 0.01 and 0.99; at exactly 0 or 1 the formula can never move again.
- **Progress** figures (attempts, accuracy, daily activity) come from the answer records themselves, so the charts always agree with each other.
- **Charts:**
  - Topic mastery is shown as accessible HTML progress bars.
  - Daily activity is stacked columns (right / not right) in palette slots 1 and 2. The pair is validated for colour-blind separation, normal-vision separation and contrast. There's one y-axis, a legend, a hover tooltip, a table view, and no animation.
  - Recharts loads only on the progress page.

## ADR-016 — Gamification: XP, streaks, rings, badges, challenges and boss battles

**Status:** Accepted (2026-11-15). Implemented in Phase 5.

**Decision.**
- **XP** is stored as events (`xp_events`), never as a running total, so nothing is lost and totals are a simple sum.
  - `(user, source, ref)` is unique: a retried answer or a repeated "finish" can never pay twice. This backs up the answer idempotency key.
  - A correct answer earns 10 × difficulty, minus a quarter per hint (hints 1–3). After the full solution it earns 2 XP. Wrong answers earn nothing and never lose XP.
  - Bonuses: 50 XP for completing the daily challenge; 20 + up to 80 for a boss battle, by score.
- **Levels** come from total XP. Each level costs 50 XP more than the one before: level 2 at 100 XP, 3 at 300, 5 at 1,000, 10 at 4,500.
- **Streaks** count London calendar days with at least one answer (`streaks`, one row per student).
  - One missed day a week is covered automatically by that week's freeze (weeks start Monday). There's nothing to buy back and no guilt messaging.
  - Missing two or more days restarts the streak from 1.
  - The streak shown is worked out when read, so a broken streak shows 0 without a background job.
  - Tested across BST/GMT changes and midnight.
- **Mastery rings** use the topic's average BKT mastery on the student's tier, with unpractised skills at the 0.2 prior: bronze from 0.4, silver from 0.6, gold from 0.8.
  - "Exam ready" also needs a boss battle score of 70% or more, so it's proven under exam conditions.
- **Badges** reward behaviour that matters: fixing mistakes, streaks, a level-5 question with no hints, daily challenges, boss battles and exam-ready topics. Never logging in.
  - The catalogue is in code. Migration 0005 inserts the same rows into `badges` (a test checks they match), and the test suite keeps that reference table between tests.
  - `user_badges` is unique per badge, so a badge is granted once.
- **Challenges** (`challenges`) are made of ordinary practice items (`challenge_id`, `position`). Marking, mistakes, reviews, mastery, idempotency and XP therefore work unchanged.
  - **Daily:** one per London day (partial unique index), up to 5 questions.
    - Up to 2 due reviews first.
    - Then weak skills across every unlocked topic: practised but below gold, weakest first; then new skills; then strong ones.
    - At most 2 from one topic before repeating a topic, so it's mixed.
  - **Boss battle:** opens once half a topic's skills have been practised.
    - Up to 6 questions spread through the topic, one level above the student's own and at least level 3.
    - Timed at 1.5 minutes a mark, with at least 5 minutes and a 30-second grace for slow networks.
    - No hints, and results only at the end.
    - Answers don't move the difficulty ladder. They do update mastery and record mistakes.
    - Time up is enforced by the server: late answers get 409 `TIME_UP` and the battle is scored.
    - The best earlier score is shown as a personal best. There's no leaderboard.
- **Grade estimates** come from admin-entered boundaries (`grade_boundaries`: percentage per grade, per spec and tier). Entry is through the API now; the admin screen comes in Phase 7.
  - They're always shown as a two-grade band ("around 5–6") labelled as an estimate from one short test.
  - Without boundaries, only the percentage and "secure / developing / not yet" are shown.
- **Home** loads one `/me/dashboard` request: Continue (today's unfinished challenge, then due reviews, then the last topic practised, then the first unlocked topic), level, streak, today's challenge, XP this week and last week, and badges. It's refetched every time home opens.
- **Sounds** are generated with Web Audio (no files), muted by default, and the setting is kept on the device. The "+XP" animation is skipped for users who ask for reduced motion.

**Trade-offs.**
- Summing XP events on each request is cheap at this scale (indexed by student); a cached total can be added if needed.
- A fixed streak freeze is simpler than earned freezes, and it can't become a dark pattern.
- Boss battles need questions at levels 3–5 in the bank. Without Claude, they can only be started on topics whose bank is already stocked.

## ADR-017 — Importing every subject's specification

**Status:** Accepted (2026-11-15).

**Context.** The student picks his own subjects (ADR-012), so every subject in the catalogue needs its spec on the most common board. Copying 1,250 statements by hand isn't practical, and the content rule forbids writing them from memory.

**Decision.**
- **Each spec is extracted from the official PDF's text layer** by a short script written for that board's layout, then checked by eye and by the importer's validation.
  - Two-column layouts are split by word position (the content column only, or both columns where they pair, as in Geography's key ideas).
  - Wording stays as printed, including the spec's own typos.
  - The extraction scripts aren't committed: each spec is a one-off import, and the YAML is the reviewed source of truth.
- **One statement per natural unit of each spec:**
  - AQA science content units (4.1.1.1).
  - Geography key ideas.
  - History strands.
  - RS bullets.
  - OCR sub topics.
  - Language theme topics and grammar blocks.
  - English skills bullets.
- **Tiering:**
  - Science paragraphs and units marked (HT only) are left out of the Foundation wording.
  - Language grammar listed under "Higher tier" is Higher only.
- **Maths and equations:**
  - Typeset fractions and powers that the text layer loses are transcribed by hand into LaTeX. Every replacement is listed in the extraction script and checked against the PDF layout.
  - Sub- and superscripts are written as Unicode (CO₂, m/s²).
- **What's left out, and said so in each file:**
  - Diagrams, structural formulae and tables printed as images.
  - The science "skills development" column.
  - Practical-activity administration notes.
  - Language vocabulary lists.
  - Texts whose last exam is before 2028.
- **OCR's "Not required" guidance** becomes `out_of_scope`, which the question generator already uses to keep questions inside the spec.
- **Options are all included.** Which ones the student studies is managed through "covered at school" on the topic map, not by leaving content out.
- **The wording limit is raised to 8,000 characters,** because two AQA physics units are over 4,000. The database columns are unlimited `text`.

**Trade-offs.**
- Image content is missing from a few statements (e.g. the charges of subatomic particles table). Questions on those points rely on the surrounding text and the verifier.
- Statements without codes get positional refs (3.1.1a, B4.2.3). A new spec issue that reorders them would retire and re-add statements rather than update them in place.

## ADR-018 — Extended answers, the scoped tutor and learn cards

**Status:** Accepted (2026-11-15). Implemented in Phase 6.

**Decision.**
- **Extended questions** are a fourth question type, generated with a mark scheme:
  - marking points (each with its marks and AO1–AO4);
  - for 6+ marks, level descriptors covering every mark without gaps;
  - a model answer.

  Validation rejects schemes that don't add up. The verifier judges the scheme instead of comparing a single answer.
- **Which types a subject gets:**
  - Maths, the sciences and Computer Science keep numeric-heavy questions, with extended answers at level 5.
  - English, the humanities and languages use multiple choice and short answers at levels 1–2, and extended answers from level 3.
- **Marking** is done by Sonnet in three steps:
  1. Lock the item, record "marking started" and commit.
  2. Call Claude with no transaction or lock held.
  3. Lock again and apply the result.

  A second request during step 2 gets 409 `MARKING_IN_PROGRESS`. A marking attempt older than 3 minutes is treated as lost.
- **Marking rules:**
  - Claude's marking is accepted only if it fits the scheme: real points, no duplicates, marks within the level and the total.
  - 70% or more counts as "right" for mastery, the ladder and mistakes.
  - XP is scaled by the share of marks earned.
  - Boss battles score written answers by the marks awarded.
- **If Claude can't mark an answer** (no key, budget, outage), the answer is kept and the mark scheme and model answer are shown. Nothing changes mastery, the ladder, mistakes or XP; only the streak counts the activity.
- **The tutor** ("Ask about this question") is scoped to the current question and its objective, and Socratic.
  - Sonnet returns `{reply, on_topic}`. Off-topic replies are replaced by a fixed redirect, so the refusal is deterministic and testable.
  - Before the question is answered, the tutor is told not to give the answer away.
  - Limits: 12 student messages per question, 8 a minute and 120 a day per student, all inside the AI budget.
  - Messages are ordered by an explicit position assigned under a row lock.
  - No connection is held while Claude replies.
- **Learn cards** (one explanation and one worked example per objective and tier) are written by Haiku in a background job, cached, and held for admin review in strict mode.
- **Prompt-injection hygiene** is the same as for explanations: student text (essays up to 4,000 characters, tutor messages up to 500) is stripped of angle brackets and control characters and wrapped in tags the system prompt declares to be data. No personal data is sent.

**Trade-offs.**
- Marking synchronously keeps the result screen simple, but the student waits up to about a minute (the UI says so). A background job would need polling.
- A model-judged "on topic" can be fooled. The fixed redirect, the per-question cap and the budget bound the damage, and every tutor message is stored for the admin.

## ADR-019 — Guardian dashboard, consent, data rights and admin tools

**Status:** Accepted (2026-11-15). Implemented in Phase 7.

**Decision.**
- **The guardian dashboard is read-only**, scoped to linked students (anything else is 404). It shows a weekly summary in London weeks, up to 12 weeks back:
  - questions answered and right;
  - minutes practising, with each question capped at 10 minutes so one left open doesn't inflate it;
  - active days, XP, streak, mistakes fixed, badges and boss battles;
  - the weakest practised topics per subject, with their rings.
- **Consent** is recorded against a versioned plain-language privacy notice (`PRIVACY_POLICY_VERSION`). Withdrawing keeps the record, marked withdrawn. Both are audited.
  - Consent is recorded and shown but does **not** yet block the student: the account is set up by the family, and blocking needs a decision about what the student sees meanwhile.
  - Making it a hard gate later is a small change (a check in `require_roles` for students).
- **Data rights:**
  - **Export:** a guardian can download everything stored about the student as JSON (UK GDPR access).
  - **Deletion:** a guardian can permanently delete the account. It needs the guardian's password and the typed word "DELETE", is rate-limited, cascades through every table, and is audited with IDs only.
- **Admin review queue:** pending questions (strict mode) and flagged ones, with the key, solution, hints, verifier notes and the student's reasons. The decisions are:
  - approve, which serves the question;
  - reject;
  - retire.

  Every decision resolves the question's flags and is audited.
- **Learn cards** are approved or rejected. Rejecting deletes the card so a fresh one can be written.
- **Cost dashboard:** today and this month in pounds (London periods, rounded half up) against the caps, by purpose, and the last 30 days, from `ai_usage`.
- **Grade boundaries** get an admin form per spec and tier, using the Phase 5 API.

**Trade-offs.** The privacy notice says Anthropic doesn't train on API data and that backups are kept for 30 days. Both must stay true: the first depends on Anthropic's commercial terms (check before going live), and the second is set in Phase 8.

## ADR-020 — Production: backups, restore tests, PWA and hardening

**Status:** Accepted (2026-11-15). Implemented in Phase 8.

**Decision.**
- **Backups** run in a small `backup` container: Postgres 16 tools plus the AWS CLI, running as a non-root user, read-only, with no capabilities.
  - `pg_dump` runs in custom format every night at 02:30 London time. Copies are kept 7 days on the server.
  - Copies are optionally uploaded with SSE to S3, using an IAM key that can only `PutObject` under one prefix. The server can't read or delete backups, and a bucket lifecycle rule expires them after 30 days.
  - The health check fails if there's been no successful backup for 26 hours.
- **The restore test** loads the newest dump into a scratch database and checks it has the same schema version, at least one user and at least one learning objective, then drops it. It runs every Sunday and in CI after the end-to-end tests.
- **PWA:**
  - A web manifest and icons make the app installable.
  - A hand-written service worker (no new dependency) caches content-hashed `/assets` forever and serves the cached app shell when offline (network first, so updates show at once).
  - It never touches `/api`: answers, marks and progress always come from the server.
  - It's registered only in production builds.
- **Hardening:**
  - In production, settings validation also refuses insecure cookies and a shared JWT secret and IP salt (short secrets were already refused).
  - Caddy now allows 90 seconds for API responses, because marking written answers and tutor replies can take up to a minute.
  - `/healthz` exposes readiness only, for an external uptime monitor; liveness and `/metrics` stay internal.
- **Deployment** is documented step by step in `DEPLOY.md`: Lightsail in London, a firewall allowing only 80, 443 and SSH from your own IP, key-only SSH, unattended upgrades, `.env` at mode 600, and monitoring through an uptime check plus Lightsail alarms.

**Trade-offs.**
- Logical dumps are simple and portable, but restoring loses anything written after the last nightly dump (at most a day of practice). Point-in-time recovery would need WAL archiving, which isn't worth it at this scale.
- A hand-written service worker is ~60 lines with no build step. A plugin (Workbox) would add precaching of every asset, at the cost of a dependency.
