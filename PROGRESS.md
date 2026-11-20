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
- [x] Team management UI: /team route (frontend/app/team/page.tsx) — member
      list, role select, extra-permission checkboxes, effective permissions.
      Degrades gracefully while the old API is live (role-based fallback;
      friendly rollout notice on 404).
- [x] Frontend wired to the permissions payload: /auth/me permissions gate
      the Team link and company analytics (legacy role fallback until the
      Render deploy lands).

Not done yet in Phase 1 (next session, in order):
- [ ] Route-based app shell: fixed collapsible sidebar + header per blueprint,
      /dashboard /leads /contacts /pipeline /tasks /assistant /reports /team
      /settings routes. Keep existing screens working during the split.
- [x] RLS verified on live Postgres 2026-11-20 (Render deploy
      dep-dc08eign74is73a5gr4g, commit 21ffaff): all 22 tenant tables have
      RLS enabled+forced with tenant_isolation policy; no context = 0 rows;
      org A context sees only A rows; org B sees none and gets API 404 for
      A's lead; system_context bypass works for webhooks; existing demo data
      (org 1, 30 leads) intact and reachable. Live RBAC denials verified
      (sales role: analytics 403, team.manage 403, team.view 200). Demo
      login end-to-end OK (owner, 16 permissions). Probe orgs deleted.
- [ ] (superseded - done above) RLS verification after Render redeploy (check
      signup, login, lead list, import, assistant demo all work; if anything
      returns empty, run `alembic downgrade 0005_assistant` on Render shell
      and investigate).
      First deploy attempt (dep-dc08crom7kps73d7smtg) FAILED safe: typo in
      TENANT_TABLES (outreach_suppression -> outreach_suppressions) aborted
      the migration, Render kept the previous deploy live, API never went
      down. Fixed + drift guard added in the RLS loop (commit 21ffaff).
- [ ] Password change; invitations and password reset need a mail path
      (currently no free verified sender — stub honestly).

## Platform super-admin — DONE 2026-11-20 (same-day requirement)

- [x] users.is_platform_admin flag (not tied to any tenant org) +
      organizations.is_active / deleted_at (migration 0007_platform_admin).
- [x] /platform/organizations list, /suspend, /restore, DELETE (reason
      required, soft-delete chosen over hard delete: reversible, keeps the
      audit trail, no destructive cross-tenant cascade under FORCE RLS).
      Operator cannot suspend/delete the workspace they act from.
- [x] Enforcement: require_platform_admin runs in verified system_context so
      tenant RLS cannot block operator views; suspended/deleted orgs are
      locked out at login AND on every request (current_membership).
- [x] Every action writes AuditLog on the target org (operator email,
      action, reason).
- [x] /platform UI page (operators only; /auth/me exposes is_platform_admin;
      Platform link in header).
- [x] Tests 58 passing (negative: owner/admin/manager/sales all 403).

## Phase 2 — Core CRM — IN PROGRESS

Backend API done 2026-11-20 (app/crm_core.py): contacts CRUD + profile,
pipelines (auto-default 7-stage), deals + stage moves with activity logging,
lead -> contact convert, tasks, activities timeline. Tests in
test_crm_core.py. NOT yet deployed to Render.



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

## 2026-11-20 — /platform delete control fix + live verification

**Problem:** Owner opened /platform and saw a "Platform operators only" panel with no delete controls. Root cause: JWT access tokens expire after 60 minutes; her stored token had expired, the API returned 401, and the page mislabeled that as a permissions restriction.

**Fix (commit 2268eb1):**
- /platform now hard-redirects to / when the session is missing/expired or the account is not a platform operator (no more misleading restricted panel; link in the header is also hidden for non-operators).
- window.prompt/confirm replaced with an inline reason-confirm panel per row: shows member/lead counts and the retention note, requires a typed reason, then Suspend/Delete/Restore executes and the row updates in place.

**Verified live (browser, signed in as the owner on https://nexus-ai-zeta-wine.vercel.app):**
- Header shows the Platform link; /platform lists every tenant workspace with Suspend + Delete on active rows.
- Full delete flow exercised on a disposable probe workspace: typed reason → confirmed → row flipped to "deleted" with Restore only; banner confirmed retention.
- Server side: organization soft-deleted (is_active=false, deleted_at set), audit_logs row platform.org_deleted with the reason and operator email, and the probe user's login now returns 403.
- Non-operator envelope verified: /auth/me returns is_platform_admin=false for a normal user, /platform/organizations returns 403, and the shipped bundle redirects non-operators/expired sessions to / (gate confirmed in the live JS).
- Probe workspace and user hard-removed after verification. Remaining tenant workspaces: NEXUS Demo Workspace, QA Company A/B (test-only leftovers from earlier QA; deletable from /platform anytime).
