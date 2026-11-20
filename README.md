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

Sending adapters for Brevo email and the official WhatsApp Cloud API are implemented, but live sends are OFF by default and need the setup below. Provider OAuth connections, billing, background workers, invitations, password reset, production onboarding, and a full agent platform are not implemented. Redis runs as a service but is not currently used by a worker or queue. A webhook source name does not make an official Meta or other provider integration.

Importing a lead never grants permission to contact it. Consent defaults to false. Explicit opt-in values are required. The outreach adapters enforce recorded consent, opt-outs and suppression lists. The generic consent flag must represent explicit marketing opt-in for the channel you select; a phone number, email address or imported row is not consent. This remains a demo foundation, not a reviewed production campaign service.

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


## Email and WhatsApp outreach

The dashboard has separate Email via Brevo and WhatsApp via Meta tabs. Select up to 20 loaded leads, inspect the personalized recipients and full content, then explicitly confirm sending. No scheduler, autonomous campaign runner, auto-send on import, retry worker, or contact-enrichment service is present. Phone-only lists cannot be reached by email. Existing sample contacts are not permission to send. Example-domain emails and contacts marked Demo/تجريبي can be personalized in preview but can never be sent. The shipped sample phone numbers are blocked for real WhatsApp sends too. With no Meta setup, WhatsApp preview uses an explicitly illustrative, unapproved demo message and returns no send token.

Both channels are OFF by default. Only owners/admins can edit templates, preview, or send. A signed 10-minute review token binds the exact rendered messages, selected recipients, workspace and user. Changes to consent/content invalidate the review. Consent, opt-out and prior attempts are rechecked before submission. Sending to an address or phone is attempted once per workspace, including failures/uncertain results. This avoids duplicates at the cost of requiring manual investigation for a retry. No retry button is supplied.

### Brevo email setup

Use your own free Brevo account, verify your sender, and save an API key in the backend host's secret environment, never in GitHub or a frontend variable. Complete Brevo's business onboarding honestly. Required settings:

- `BREVO_API_KEY`
- `OUTREACH_SENDER_EMAIL`, `OUTREACH_SENDER_NAME`
- `OUTREACH_SENDER_VERIFIED=true`, only after verification in Brevo
- `OUTREACH_POSTAL_ADDRESS`, a valid sender postal address approved for inclusion in emails
- `OUTREACH_PUBLIC_API_URL`, the stable public HTTPS backend URL
- `OUTREACH_DAILY_CAP=250`, clamped to at most 290
- `OUTREACH_ENABLED=true`, only after legal/provider/hosting checks and approved tests
- A strong stable `JWT_SECRET` of at least 32 characters

The editable workspace email subject/body supports only `{name}` and `{sender_name}` placeholders. A promotional disclosure, postal address and signed unsubscribe link are appended. From and Reply-To use the configured sender. The default template is intentionally generic and is not an approved sales pitch. Review/edit it for your business before sending.

The unsubscribe GET displays a confirmation page, so link scanners do not opt people out. Its POST immediately suppresses the normalized email within that workspace and marks matching leads opted out, including protection against re-imports. Links have no expiry; keep this HTTPS endpoint and the signing secret available for at least 30 days after the last email, and longer where law/policy requires. Changing the signing secret breaks previously issued links. Honor withdrawal requests received elsewhere too; this starter has no mailbox-monitoring service. Deleting the database loses suppression history, so do not run real campaigns without durable backups and retention controls.

Brevo Free currently includes **300 emails/day across the account**, not per workspace. Unused sends do not roll over. The application's default 250/day limit is global across workspaces sharing its database and counts reserved attempts, not deliveries. It resets at the UTC date boundary. Rejected/unknown attempts still count conservatively. It is **not a live view of Brevo's remaining credits**. Other applications and campaigns in the Brevo account also consume the provider allowance; use a dedicated account and inspect its quota. A provider limit/error stops the current batch with no automatic retry. Brevo can queue mail at its own limit; an accepted result does not guarantee immediate delivery. No paid plan or card is required for the Free plan, but account validation and sender restrictions still apply.

### Official WhatsApp Cloud API setup, configure later

This adapter does not create a Meta account, register a number, add billing or buy message credits. The owner must set up the official Meta app and WhatsApp Business account, register a sending number, obtain an appropriately scoped token, configure signed webhooks, approve costs and have an approved marketing template. It does not use unofficial WhatsApp Web automation.

Backend-only settings:

- `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_BUSINESS_ACCOUNT_ID`
- `WHATSAPP_TEMPLATE_NAME`, `WHATSAPP_TEMPLATE_LANGUAGE=en_US`
- `WHATSAPP_GRAPH_VERSION=v23.0`, check Meta's supported versions before enabling
- `WHATSAPP_APP_SECRET`, used to verify `X-Hub-Signature-256`
- `WHATSAPP_WEBHOOK_VERIFY_TOKEN`, a strong secret chosen for webhook verification
- `WHATSAPP_DAILY_CAP=20`, clamped to at most 100 app reservations/day (UTC)
- `WHATSAPP_COST_ACKNOWLEDGED=true`, only after the owner approves applicable Meta charges
- `WHATSAPP_ENABLED=true`, only after the owner deliberately enables a tested setup

Use `GET/POST /whatsapp/webhook` as the callback URL and subscribe to the WhatsApp messages field. Verification uses the configured verify token. Incoming callbacks require a valid HMAC-SHA256 signature with the app secret and the configured phone number ID. STOP, UNSUBSCRIBE, CANCEL, END, QUIT and common Arabic stop/withdrawal replies suppress that number across workspaces sharing this single configured WhatsApp sender. Delivery/read/failed callbacks update the send log. Callbacks are replay-safe for suppression and delivery progression. There is no reply bot or automatic opt-out acknowledgment message.

This first adapter supports **simple APPROVED MARKETING text templates** with exactly one positional `{{1}}` name parameter in BODY, optional static FOOTER and no media/header/buttons. Include clear STOP opt-out instructions in the approved text. It fetches the approved template from Meta for preview and rechecks it before sending. Unsupported/pending templates block sending. Template copy is edited and approved in Meta, not free-form in this dashboard.

Business-initiated WhatsApp marketing is **not promised free**. Meta charges can depend on country, category and current terms; review the current account rate card and approved budget before enabling. No fixed price or free allowance is assumed by this code. The daily cap limits attempts, not monetary spend. Meta template approval, opt-in and account quality/rate rules apply. The generic `consent=true` field must only be set when the business has explicit opt-in for WhatsApp marketing; the app cannot verify that provenance by itself.

### Logs and limits

Separate email/WhatsApp send records retain rendered content, recipient, status, provider message ID and safe error summaries. The dashboard shows the latest 100 attempts per channel. `accepted` means provider acceptance, not inbox/phone delivery. WhatsApp signed callbacks can later show sent/delivered/read/failed; email has no delivery/bounce webhook in this version. Inspect Brevo for delivery, bounces and complaints and disable sending when appropriate. No automatic bounce/complaint suppression exists yet, so this is not ready for unattended production marketing.

A send is reserved in the database before contacting the provider. Unique workspace/recipient constraints prevent concurrent duplicate attempts; conditional database quota updates cap concurrent reservations. A crash/timeout can leave `sending` or `unknown`: inspect the provider dashboard before any manual recovery. No automatic retries are made. Secrets and full provider error responses are not returned in logs. A long batch runs in the HTTP request; client disconnection/timeouts need log checks rather than blind repetition.

The current hosted demo uses free hosting: Render's free API can sleep, its free PostgreSQL expires, and Vercel Hobby is for non-commercial personal use. Do not use the current demo hosting or sample data for live commercial campaigns. Choose hosting whose terms allow the intended use, preserve data/backups/suppression history, and complete a security/legal review first. Setting an environment flag does not make these requirements disappear.

### Outreach endpoints

- `GET /outreach/status`, `PUT /outreach/template`, `POST /outreach/preview`, `POST /outreach/send`
- `GET/POST /outreach/unsubscribe`, public signed-token confirmation/withdrawal
- `GET /whatsapp/status`, `POST /whatsapp/preview`, `POST /whatsapp/send`
- `GET/POST /whatsapp/webhook`, Meta challenge and signed callbacks

Preview accepts `{"lead_ids":[1,2]}`. Send accepts `{"review_token":"..."}` from that exact preview. Status reports setup blockers and app-only quota. All endpoints except unsubscribe/webhook require the workspace Bearer token; mutating/sending operations additionally require owner/admin membership.

Sources for provider setup and changing limits:
- https://help.brevo.com/hc/en-us/articles/208580669-FAQs-What-are-the-limits-of-the-Free-plan
- https://developers.brevo.com/reference/sendtransacemail
- https://developers.facebook.com/docs/whatsapp/cloud-api/guides/send-message-templates/

### Verification for this feature

Backend tests mock provider HTTP calls and never send real emails or WhatsApp messages. They cover consent/default-off gates, sample/invalid addresses, exact-preview binding, template edits, duplicate recipients, role/workspace isolation, quota boundaries, provider rejection/timeouts, unsubscribe persistence, approved WhatsApp template shape and signed STOP/delivery callbacks. A passing mocked test is not a live delivery test. Configure-later WhatsApp has not been tested against a real Meta account. No real campaign has been sent.
