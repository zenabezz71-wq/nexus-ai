# NEXUS AI

A local-development SaaS starter for managing and classifying leads. Includes a Next.js dashboard, FastAPI backend, PostgreSQL with Alembic migrations, a Redis service, JWT login, workspace-scoped records, CSV/XLSX imports, and an authenticated lead-ingestion endpoint.

This is a development foundation, not a finished or security-audited production service. Creating a GitHub repository does not deploy a running website.

## Run locally with Docker

Requires Git, Docker Engine/Desktop and the Docker Compose v2 plugin. Run these commands from the repository root:

```sh
cp .env.example .env
# Windows PowerShell: Copy-Item .env.example .env
```

Edit the new `.env` before starting:

- Set `POSTGRES_PASSWORD` and put the SAME password in `DATABASE_URL`. The hostname inside Compose must stay `db`, not `localhost`. If the password contains URL-reserved characters, percent-encode it in the URL only.
- Replace `JWT_SECRET` with a unique random secret of at least 32 characters.
- Set `BOOTSTRAP_EMAIL` and a strong `BOOTSTRAP_PASSWORD`. These create the first admin on an empty database. Changing the file later does not change an existing user's password.
- Leave `OPENAI_API_KEY` empty to use local rule-based classification. An API key enables external AI requests and can incur charges on your OpenAI account. Lead messages and goals are then sent to that provider. Do not add a key until that disclosure is appropriate for your data.
- For local use, keep `NEXT_PUBLIC_API_URL=http://localhost:8000` and `CORS_ORIGINS=http://localhost:3000`.

Then:

```sh
docker compose up --build
```

On first start, allow time for image downloads, package installation, migrations and the frontend build. Open:

- Dashboard: http://localhost:3000
- API docs: http://localhost:8000/docs
- API health: http://localhost:8000/health

Sign in with the `BOOTSTRAP_EMAIL` and `BOOTSTRAP_PASSWORD` from your own `.env`. The initial workspace is a demo workspace. Import `sample_leads.csv` to try the lead dashboard. Its rows are demonstration data, not permission to contact anyone.

The development ports bind only to `127.0.0.1`, not to all network interfaces. For another machine or a deployment, configure the public API URL, CORS, HTTPS, authentication and networking deliberately. `NEXT_PUBLIC_API_URL` is embedded during the frontend build, so rebuild the web image after changing it.

```sh
docker compose ps
docker compose logs --tail=100 api web
docker compose down
```

`docker compose down` keeps database and Redis volumes. Do not use `docker compose down -v` unless you intend to delete their stored data. PostgreSQL environment settings initialize a new database volume only; changing them later does not update existing database credentials.

Never commit `.env`, API keys, database dumps, or real customer spreadsheets. `.gitignore` and Docker ignore files exclude local secrets and generated files. Template values are not secure live credentials.

## What works

- JSON login and Bearer-token authentication.
- Active-membership-derived workspace scope, rather than client-supplied organization IDs.
- Summary metrics, lead search and lead listing.
- English/Arabic CSV or XLSX headers, phone normalization, and organization-level duplicate checks.
- Rule-based classification, with optional OpenAI chat-completions classification.
- Authenticated generic lead ingestion that upserts by normalized phone within a workspace.

## What is NOT implemented

Live WhatsApp/email sending, provider OAuth connections, provider-specific webhook signatures, billing, background workers, invitations, password reset, production onboarding, and a full agent platform are not enabled. Redis runs as a service but is not currently used by a worker or queue. A webhook source name does not make an official Meta or other provider integration.

Importing a lead never grants permission to contact it. Consent defaults to false. Explicit opt-in values are required. Production handling of consent withdrawal and opt-out enforcement needs additional work; do not use this starter to send outreach.

## API

`POST /auth/login` accepts JSON with `email` and `password`. Use its token as `Authorization: Bearer <token>`. The docs' built-in OAuth password form does not match this JSON login, so use the JSON endpoint to obtain your token.

- `GET /health`
- `POST /auth/login`
- `GET /auth/me`
- `GET /dashboard/summary`
- `GET /leads?q=&status=&limit=`
- `POST /leads/import`, multipart CSV/XLSX
- `POST /agents/classify/{lead_id}`
- `POST /webhooks/{source}`, authenticated JSON lead upsert

Lead payload fields include `external_id`, `name`, `phone`, `email`, `currency`, `amount`, `goal`, `message` and Boolean `consent`. Phone is required. Webhook signatures, replay protection and provider OAuth scopes must be implemented before exposing provider ingestion publicly.

## Backend development and tests

Python 3.12 is used by the Docker image. From the repository root, without running Compose:

```sh
cd backend
python -m venv .venv
# macOS/Linux:
. .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest -q
```

The tests use a disposable SQLite database, not the Compose PostgreSQL service. A local backend reads `../.env`; if that file contains a Compose database URL, replace or override it with a local development URL before running the API outside Docker.

Docker startup applies `alembic upgrade head`. Generate a new migration from `backend` with:

```sh
alembic revision --autogenerate -m "description"
```

## Review and verification

The supplied source was reviewed for startup configuration, imports, migrations, dependency installation and accidental credential files. Changes include a repaired `.gitignore`, Docker context exclusions, a missing OpenAI SDK dependency, a frontend API build argument, a reproducible npm lockfile, updated Next.js/React dependencies, and test import-path configuration.

Verified during review: four backend tests pass; Python dependencies install and pass `pip check`; an Alembic upgrade succeeds on a fresh SQLite database; the optional SDK request interface works with a mocked HTTP response; and the frontend production build succeeds. The npm audit of the resolved lockfile reports no known vulnerabilities at review time. That is not a security audit or a guarantee about future advisories.

Not verified during review: a full Docker Compose run, PostgreSQL-specific migration behavior in a running container, paid/live OpenAI calls, or a deployed public website. Docker was unavailable in the review environment. Backend tests ran on Python 3.10, while the image specifies 3.12. Do not describe this as production-ready.

## Before production

Add MFA, password reset, invitations, token revocation, rate limits, role enforcement, upload size limits, safe spreadsheet parsing, secure session storage, PostgreSQL RLS, webhook verification/replay protection, background retries, billing controls, backups, monitoring, privacy/retention controls and security/load testing. Replace development secrets and use HTTPS. Review changing provider and library policies before any production launch.
