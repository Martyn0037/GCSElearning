# Deploying GCSE Coach

This puts the app on one AWS Lightsail server with your own domain, HTTPS, nightly backups and basic monitoring. It takes about an hour the first time. Every command is run on the server unless it says otherwise.

## What you need

- An AWS account (for Lightsail, and S3 for off-site backups).
- A domain or subdomain you can add DNS records to, e.g. `coach.example.com`.
- An Anthropic API key, from <https://console.anthropic.com>. Without one, the app serves only questions already in the bank.
- About £10–15 a month for the server, plus the Claude budget you set (default £25 a month cap).

## 1. Create the server

1. In the Lightsail console, create an instance:
   - **Region:** London (eu-west-2).
   - **Platform and blueprint:** Linux, OS only, Ubuntu 24.04 LTS.
   - **Plan:** 2 GB RAM. The containers are limited to well under that.
   - Name it `gcse-coach`.
2. **Networking:** attach a **static IP**.
3. **Firewall** (IPv4 and IPv6):
   - Allow **HTTP (80)** and **HTTPS (443)**.
   - Allow **SSH (22)** from your own IP address only.
   - Remove anything else.
4. **DNS:** at your domain provider, add an **A record** for your domain pointing at the static IP. Wait until `dig +short coach.example.com` shows it.

## 2. Prepare the server

SSH in with the Lightsail key (from your own computer):

```bash
ssh -i LightsailDefaultKey-eu-west-2.pem ubuntu@coach.example.com
```

Apply updates, and switch on automatic security updates:

```bash
sudo apt-get update && sudo apt-get -y upgrade && sudo apt-get -y install unattended-upgrades
```

Install Docker Engine and the Compose plugin from Docker's repository:

```bash
curl -fsSL https://get.docker.com | sudo sh
```

```bash
sudo usermod -aG docker ubuntu
```

Log out and back in so the group change applies. Then make sure SSH accepts keys only:

```bash
sudo sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config && sudo systemctl reload ssh
```

## 3. Get the code

Clone the repository. For a private repo, use a read-only deploy key or a fine-grained token with read access.

```bash
git clone https://github.com/Martyn0037/GCSElearning.git ~/gcse-coach && cd ~/gcse-coach
```

## 4. Configure

```bash
cp .env.example .env && chmod 600 .env
```

Generate the secrets, then paste each into `.env`:

```bash
for name in POSTGRES_PASSWORD JWT_SECRET AUDIT_IP_SALT; do echo "$name=$(openssl rand -hex 32)"; done
```

Edit `.env` (for example with `nano .env`) and set:

| Setting | Value |
|---|---|
| `DOMAIN` | your domain, e.g. `coach.example.com` |
| `ENVIRONMENT` | `production` |
| `POSTGRES_PASSWORD`, `JWT_SECRET`, `AUDIT_IP_SALT` | the generated values, all different |
| `ANTHROPIC_API_KEY` | your key |
| `AI_MONTHLY_BUDGET_GBP` / `AI_DAILY_BUDGET_GBP` | the caps; Claude isn't called past either |
| `QUESTION_STRICT_MODE` | `true` for the first couple of weeks, so you approve new questions and learn cards in Admin; `false` after that |

The app refuses to start in production if a secret is short, if `JWT_SECRET` and `AUDIT_IP_SALT` are the same, or if secure cookies are off.

`.env` must never be committed. It's in `.gitignore`.

## 5. Start it

```bash
docker compose up -d --build --wait
```

This builds the images, runs the database migrations, imports the curriculum, and starts the API, the worker, the backup service and Caddy. Caddy gets an HTTPS certificate from Let's Encrypt automatically.

Check every service says `healthy`:

```bash
docker compose ps
```

Then open `https://coach.example.com`.

## 6. Create the accounts

This asks for each password at a hidden prompt (at least 10 characters each):

```bash
docker compose run --rm api python -m app.cli.seed_users --admin-email you@example.com --guardian-email you+parent@example.com --guardian-name Alex --student-username sam10 --student-name Sam
```

Then:

1. Sign in as the **student** on their phone and choose their subjects. Add the app to the home screen: Share → "Add to Home Screen" on iPhone, or the install prompt on Android.
2. Sign in as the **guardian** and agree to the privacy notice.
3. Sign in as the **admin**. Confirm the student's boards and tiers, and tick the topics already covered at school. Practice opens topic by topic.

## 7. Off-site backups (recommended)

The `backup` service dumps the database every night at 02:30 (UK time) and keeps 7 days on the server. It tests a restore every Sunday. To also keep 30 days of copies off the server:

1. **Create an S3 bucket:**
   - Region eu-west-2.
   - Block all public access left **on**.
   - Default encryption SSE-S3.
2. **Add a lifecycle rule** on the bucket: expire current objects after **30 days**.
3. **Create an IAM user** (programmatic access only) with only this policy. The server can add backups but can't read or delete them:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       { "Effect": "Allow", "Action": "s3:PutObject", "Resource": "arn:aws:s3:::YOUR-BUCKET/gcse-coach/*" }
     ]
   }
   ```

4. **Put the bucket and key in `.env`:** `BACKUP_S3_BUCKET`, `BACKUP_AWS_ACCESS_KEY_ID` and `BACKUP_AWS_SECRET_ACCESS_KEY`. Then apply them:

   ```bash
   docker compose up -d --wait backup
   ```

5. **Run a backup now** to check the upload works. The last line should say `"uploaded":true`.

   ```bash
   docker compose run --rm backup backup
   ```

Test a restore at any time. It restores the newest dump into a scratch database, checks it, and drops it:

```bash
docker compose run --rm backup restore-test
```

### Restoring for real

Stop the app, restore the dump over the live database, then start again:

```bash
docker compose stop api worker caddy
```

```bash
docker compose exec -T postgres sh -c 'pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < backup.dump
```

```bash
docker compose up -d --wait
```

To use an off-site copy, download it from the S3 console first.

## 8. Monitoring

- **Uptime:** add a free monitor (for example UptimeRobot or Better Stack) for `https://coach.example.com/healthz`, with email alerts. It returns 200 when the API can reach the database.
- **Server:** in Lightsail, add metric alarms for **CPU over 80% for 10 minutes** and **failed status checks**, with email notifications.
- **AI spend:** the Admin page shows today and this month against the caps. Claude stops being called at either cap, and the app carries on from the question bank.
- **Logs:** use `docker compose logs --tail 200 api` (or `worker`, `caddy`, `backup`). Logs are JSON, with no passwords, tokens or student answers. They rotate at about 200 MB per service, which is well over 30 days at this volume.

Optionally, switch on Lightsail **automatic snapshots** for a whole-server copy as an extra safety net.

## 9. Updating

Pull and rebuild. Migrations and the curriculum import run automatically:

```bash
cd ~/gcse-coach && git pull && docker compose up -d --build --wait
```

To roll back, check out the previous commit and run the same `docker compose up` command. Every migration has a downgrade. Run `docker compose run --rm migrate alembic downgrade -1` only if a release's notes say so.

## 10. Keeping it secure

- Keep SSH restricted to your IP. Don't open other ports.
- **Rotate secrets** by editing `.env`, then running `docker compose up -d --wait`:
  - Changing `JWT_SECRET` signs everyone out.
  - Changing `AUDIT_IP_SALT` only affects new audit entries.
  - Rotate the Anthropic and AWS keys in their consoles too.
- Dependabot opens pull requests for dependency updates, and CI scans the images. Merge them, then update as in section 9.
- Check Admin → Review queue every so often for questions the student flagged.
