# NEXUS AI — Build Progress

Living document. Update at the end of every work session so the next run (or a
future agent) can pick up cleanly. Blueprint source: product blueprint from the
owner, 2026-11-20 (12-week, 6-phase roadmap + Phase 0 audit).

Hard constraints (standing):
- FREE tiers only: Vercel free, Render free, existing Postgres. If a feature
  cannot be done free, ship a clean stub and say so. Never pay.
- No fake claims, no invented stats. Demo/seed data must be labeled.
- The live demo must keep working. Sales Reply Studio (#sales-studio) is
  public and must keep working.
- Render API deploys are MANUAL (Render dashboard). Frontend deploys are
  automatic on push to main via Vercel.
- GitHub pushes use a temporary fine-grained token, revoked after the push.

## Phase 0 — Technical & Product Audit — DONE 2026-11-20

See AUDIT.md: keep/develop/rebuild lists, security notes, real-vs-demo map.

## Phase 1 — Foundation — IN PROGRESS

Done 2026-11-20:
- [x] Blueprint tenant schema: teams, contacts, pipelines, pipeline_stages,
      deals, tasks, activities, notifications, integrations, ai_usage,
      subscriptions, invoices (backend/app/tenant.py, migration 0006_foundation).
      Every table: organization_id + FK, soft delete, audit timestamps,
      created_by/assigned_to where the blueprint asks.
- [x] PostgreSQL RLS: enabled + FORCED with a tenant_isolation policy on all
      tenant business tables (Postgres only; SQLite tests skip). Per-request
      org context via transaction-local GUC (backend/app/rls.py); identity
      tables stay app-scoped (documented in migration 0006). Policy SQL
      syntax-validated with pglast; NOT yet verified against a live Postgres —
      watch the first Render deploy and keep 0006 downgrade as rollback.
- [x] RBAC: owner/admin/manager/sales matrix + grantable extra permissions
      (backend/app/rbac.py), memberships.grants column, /team/members +
      role-change + grants endpoints (backend/app/team.py), /auth/me and
      login payload expose permissions. Analytics now follows the matrix
      (managers included).
- [x] lead_sales.organization_id added + backfilled.
- [x] Design system base: tokens (dark navy + gold default, light mode via
      [data-theme]), Inter + IBM Plex Sans Arabic, RTL-aware primitives,
      theme toggle persisted in localStorage (frontend/app/globals.css).
- [x] Frontend structure: components/ directory (Outreach, LeadEditor,
      Assistant, AdminAnalytics, SalesStudio extracted; page.tsx slimmed).
- [x] Tests: 50 passing (4 new: RBAC matrix, team endpoints, schema
      roundtrip, analytics permission).

Not done yet in Phase 1 (next session, in order):
- [ ] Route-based app shell: fixed collapsible sidebar + header per blueprint,
      /dashboard /leads /contacts /pipeline /tasks /assistant /reports /team
      /settings routes. Keep existing screens working during the split.
- [ ] Team management UI on top of /team endpoints.
- [ ] RLS verification against live Postgres after Render redeploy (check
      signup, login, lead list, import, assistant demo all work; if anything
      returns empty, run `alembic downgrade 0005_assistant` on Render shell
      and investigate).
- [ ] Password change; invitations and password reset need a mail path
      (currently no free verified sender — stub honestly).

## Phase 2 — Core CRM — NOT STARTED

Contacts module, blueprint lead lifecycle + convert-to-deal, pipeline board
with drag-and-drop, executive dashboard metrics, search/filters, export.

## Phase 3–6 — NOT STARTED

Tasks UI, notifications, reports + export, AI copilot (start rule/SQL-backed,
free), integrations hub, billing enforcement, launch hardening.

## Operational notes

- Backend tests: `cd backend && . .venv/bin/activate && python -m pytest -q`
  (SQLite, disposable). Migrations: `alembic upgrade head`.
- Frontend check: `cd frontend && npm ci && npm run build`.
- Render env holds real secrets (JWT_SECRET, DATABASE_URL, BOOTSTRAP_*).
  Never commit .env.
- Live URLs: frontend https://nexus-ai-zeta-wine.vercel.app — API
  https://nexus-ai-api-knad.onrender.com (Render free: cold start ~1 min).
