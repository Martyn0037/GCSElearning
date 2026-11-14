# End-to-end tests

Playwright tests that drive the real app (Caddy + API + Postgres) in a phone-sized
Chromium window.

## Run locally

1. Start the stack and seed the accounts (see the root `README.md`).
2. Install the browser once:

   ```bash
   npx playwright install chromium
   ```

3. Add the fixed end-to-end questions (test data; refused in production):

   ```bash
   docker compose run --rm api python -m app.cli.seed_test_questions --spec 1MA1 --objective N4
   ```

4. Give the tests the seeded credentials. These are read from the environment and never committed:

   ```bash
   export E2E_STUDENT_USERNAME=sam10 E2E_STUDENT_PASSWORD='…' E2E_ADMIN_EMAIL=you+admin@example.com E2E_ADMIN_PASSWORD='…'
   ```

5. Run them:

   ```bash
   npx playwright test
   ```

`E2E_BASE_URL` defaults to `https://localhost`. The tests are re-runnable: they
set the state they need instead of assuming a fresh database. They do change the
seeded student's subjects, so don't point them at real data.
