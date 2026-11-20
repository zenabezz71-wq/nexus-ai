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

## 2026-11-21 — Phase 2 workspace app shell + screens live

**Shipped (commit 676b2ad, live on Vercel):**
- Workspace shell with persistent sidebar at /app (Dashboard, Contacts, Pipeline, Tasks; Team when permitted; Platform for operators), workspace/user/role display, theme toggle, sign out. Auth-gated: missing or expired session redirects to /.
- /app/contacts: searchable list, create, profile (deals, tasks, activity timeline), edit, note/call/meeting/message/email logging, archive (contacts.view_all only).
- /app/pipeline: 7-stage kanban with drag-drop (HTML5 DnD), per-column counts and EGP totals, create-deal form, archive (deals.delete only). Stage moves are written to the activity timeline by the API.
- /app/tasks: open/done/all filters, create with due date/priority/contact link, complete/reopen, delete, overdue highlighting.
- Signed-in landing header now links to the workspace (/app).

**Verified live as the owner:** contact create + note (timeline recorded note + contact.created), deal create linked to contact, drag-drop to Qualified (server recorded deal.stage_changed), task create + complete. All test data removed afterwards.

**Session-stability fix (commit e0253ce, live):** the landing page's mount-effect session restore called clearSession() unconditionally when the stored token failed; racing a concurrent successful login it could delete the fresh token. Both clearSession call sites now only clear the exact token they validated. Verified live: UI sign-in persists (60s+ with valid /auth/me), and a valid token planted while a stale-token restore is failing survives (guard works).

## 2026-11-21 — Phase 2 continued: deal detail, stage management, activity feed, lead delete

**Shipped (commit 28818ea backend live on Render, frontend live on Vercel; lead-delete in follow-up commit):**
- Deal detail panel on /app/pipeline: open any deal card to edit title/stage/amount/expected close/next step, log notes, and read the deal's activity timeline (deal.created, deal.stage_changed, notes).
- Pipeline stage management (company.settings only): add, rename, set probability, move left/right, and delete stages from the Manage stages mode on /app/pipeline. API: POST /pipelines/{id}/stages, PATCH /stages/{id}, DELETE /stages/{id} (409 while deals are in the stage, 400 when it is the last stage).
- /app/activity: workspace-wide feed grouped by day with kind filters (All, Notes & comms, Deals, Contacts & leads, Tasks, Pipeline) and contact/deal name mapping.
- Landing leads table: Convert button per unconverted lead (POST /leads/{id}/convert); converted leads show a converted badge instead. /app/contacts?open=<id> opens a contact profile directly.
- DELETE /leads/{id} (company-wide access only): removes a lead and its feedback/assignment, nulls lead references on contacts/deals/activities, writes lead.deleted to the feed and audit log.

**Verified live as the owner:** stage add/rename/move/delete (feed recorded each), lead import + convert (contact created, converted badge, no Convert button afterwards), deal create + stage change + note (timeline and /app/activity show all), contacts?open= deep link. Test data removed afterwards (deal, contact, lead).

**Backend tests: 61 passed.**

## 2026-11-21 — Executive Dashboard (blueprint section A)

**Shipped (commit b8a9de7, backend live on Render, frontend live on Vercel):**
- GET /dashboard/executive?period=day|week|month: total leads and new-this-period with previous-period change %, active deals and pipeline value, won revenue with previous-period comparison, probability-weighted expected revenue, conversion rate (definition returned with the data), top lead sources, deals at risk (open deals with no activity in 7+ days or a passed expected close), tasks due today and overdue, per-member team performance. Scope follows permissions: reports.company holders see the company view, sales sees own records only.
- NEXUS Intelligence card: rule-based statements from the same aggregates, each with its period and sample, labeled as computed from workspace data with no external AI calls.
- /app is now the dashboard (previously redirected to /app/contacts): KPI cards, period switcher, insights card, deals-at-risk and tasks panels, team performance table, top lead sources. Sidebar Dashboard link fixed to /app.

**Verified live as the owner:** endpoint returns company scope with real counts; page renders and period switch works. Backend tests: 63 passed.

## 2026-11-21 — Phase 3 slice: contacts CSV export + tasks calendar view

**Shipped:**
- GET /contacts/export: CSV export of the contacts the caller can see, gated on the contacts.export permission (owner/admin by default), with a contacts.exported audit log entry recording the row count.
- /app/contacts: Export CSV button, visible only when the signed-in member holds contacts.export.
- /app/tasks: List/Calendar view toggle. Calendar is a month grid with prev/next navigation; tasks appear on their due date, overdue outlined red, done struck through, today highlighted. Tasks without a due date are noted as excluded.

**Backend tests: 64 passed.** TypeScript compiles clean.

## 2026-11-21 — Phase 3 slice 2: in-app notifications

**Shipped:**
- GET /notifications (own, latest 100 + unread count), POST /notifications/{id}/read, POST /notifications/read-all.
- Assignment events notify the new assignee when someone else assigns them a task or a deal (task.assigned, deal.assigned). Self-assignment does not notify.
- Lazy reminder: fetching notifications creates at most one tasks.overdue_reminder per user per UTC day, listing their overdue open-task count and oldest due date. No background worker needed (free tier).
- /app/notifications page: list with kind tags, unread highlighting, mark-read and mark-all-read. Sidebar Notifications link with an unread-count badge that refreshes on navigation.

**Backend tests: 66 passed.** TypeScript compiles clean.
