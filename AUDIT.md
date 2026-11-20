# NEXUS AI — Phase 0: Technical & Product Audit

Date: 2026-11-20. Scope: current repo (`main` @ 9e85bb3), live frontend
(nexus-ai-zeta-wine.vercel.app), live API (nexus-ai-api-knad.onrender.com).
Method: full code read of backend and frontend, README verification notes,
test suite run (46 tests, all passing), production build check.

This audit answers the blueprint's Phase 0 question: what works today, what is
demo-only, and what do we keep / develop / rebuild before the 12-week roadmap.

## What exists today

**Backend** (FastAPI + SQLAlchemy + Alembic, Render free, PostgreSQL in
Compose / SQLite in tests):

- Company signup and JWT login with argon2 password hashing, per-IP/per-email
  rate limiting, validated inputs, bootstrap admin.
- Multi-tenancy: `organizations` + `memberships`; every lead, send, note,
  template and audit row is queried through the caller's active membership.
  Application-level scoping only — no PostgreSQL RLS yet.
- Leads: list/search, CSV/XLSX import with Arabic+English header
  normalization, phone normalization (Egypt default), per-workspace duplicate
  detection, optimistic-locking edits, assignment to members, append-only
  sales notes, status model (unclassified → hot/warm/cold/follow_up/…/won/lost).
- Rule-based Arabic/English lead classifier; optional paid OpenAI path, off
  without a key.
- Outreach: Brevo email + official WhatsApp Cloud API adapters with consent
  gating, opt-out/suppression lists, per-day quotas, signed 10-minute review
  tokens, once-per-recipient reservations. OFF by default, no credentials set.
- Assistant: rule-based Egyptian-Arabic auto-reply engine with simulated
  conversations, human takeover, demo leads clearly separated. No LLM calls.
- Analytics: owner/admin workspace overview (weekly brief, pipeline counts,
  per-salesperson table) computed from real workspace data.
- AuditLog on imports, edits, sends, simulations.

**Frontend** (Next.js 16 + React 19, Vercel free): single-page dashboard —
auth panel, stat cards, lead import/table/search, lead editor, assistant chat,
outreach review UI, admin analytics, and the public Egyptian Sales Reply
Studio (#sales-studio, local template tool, no data leaves the page).
Plain CSS, light theme only, Arial, no component structure beyond 4 files,
no sidebar/navigation, no dark mode, LTR only except the studio section.

## What is real vs demo

Real (works against the live API today): signup/login, workspace isolation,
import, lead editing/assignment/notes, classification, analytics, sales studio.
Demo/stub: Brevo/Meta sending (adapters written, disabled, uncredentialed),
OpenAI classification (off), the assistant's WhatsApp webhook (gated),
Redis (running, unused).

## List 1 — KEEP (works, aligned with the blueprint)

1. Auth core: JWT login/signup, argon2, rate limits, input validation.
2. Membership-derived tenant scoping pattern (no client-supplied org ids).
3. Lead import pipeline: header/phone normalization, dedupe, 5 MB/5000-row caps.
4. Optimistic-locking edit flow + consent reset on contact change + do-not-contact
   suppression handling.
5. Consent/opt-out/quota/review-token architecture for outreach (stays OFF
   until real provider credentials exist — matches blueprint section 3F).
6. Rule-based classifier and rule-based Arabic assistant (free to run; the
   honest foundation the AI layer builds on).
7. Sales Reply Studio as-is (public, no-login, no-data-collection).
8. Alembic migration discipline + AuditLog + test suite (50 tests green).

## List 2 — DEVELOP (exists, needs building out)

1. **Roles**: today only owner/admin checks exist. Build the blueprint RBAC
   matrix (owner/admin/manager/sales + grantable extra permissions). → Done in
   Phase 1 (rbac.py, memberships.grants, /team endpoints).
2. **Multi-tenancy**: add PostgreSQL RLS as a database-level backstop on every
   tenant table. → Done in Phase 1 (migration 0006).
3. **Schema**: extend to the blueprint model — contacts, pipelines, stages,
   deals, tasks, activities, notifications, integrations, ai_usage,
   subscriptions, invoices, teams. → Schema done in Phase 1; endpoints/UI in
   Phase 2+.
4. **Dashboard**: current 4 stat cards → executive dashboard (revenue,
   conversion, period comparison, filters, at-risk deals) once deals exist.
5. **Leads**: add blueprint lifecycle (New/Contacted/Qualified/Converted/Lost)
   mapping and convert-lead-to-contact+deal flow (Phase 2).
6. **Auth**: add invitations, email verification, password reset (needs a
   mail path), token revocation. Login/signup themselves stay.
7. **Analytics**: current admin overview → full reports with export (Phase 2–3).
8. **Frontend**: adopt the design system (dark navy + gold, Inter + IBM Plex
   Sans Arabic, RTL/LTR, dark/light, responsive). → Base tokens + component
   structure landed in Phase 1; route-based app shell with sidebar next.

## List 3 — REBUILD / BUILD NEW

1. Frontend information architecture: the single mega-page becomes a routed
   app (Dashboard / CRM / Leads / Pipeline / Tasks / Communications / AI /
   Reports / Team / Integrations / Billing / Settings) with a fixed
   collapsible sidebar per the blueprint. Keep every working screen's logic.
2. Contacts module (separate from leads) with full profile, tags, timeline.
3. Sales Pipeline module: customizable stages, drag-and-drop deals,
   activity logging per change.
4. Tasks & Activities module (list/calendar/kanban, reminders, overdue).
5. Team management UI (backend landed in Phase 1) + invitation flow.
6. Billing: plans/limits/trial/invoices schema exists (Phase 1); the actual
   paywall, plan enforcement and payment provider integration are new work.
7. Notifications center (schema exists).
8. Integrations hub UI (WhatsApp/Meta/email/calendar connect flows — real
   OAuth, not buttons; provider review is external work, not free-tier code).
9. NEXUS AI Copilot: in-app assistant over workspace data. Start with
   free, rule/SQL-backed answers over real data (no LLM cost), LLM tool layer
   later behind permissions and usage tracking (ai_usage table ready).
10. PostgreSQL RLS: applied to existing tenant tables; new modules must keep
    the pattern (org id + policy + tests).

## Security & correctness notes found during the audit

- lead_sales lacked organization_id (tenant key inferred via lead). Fixed in
  migration 0006 with backfill; RLS now covers it directly.
- The signed WhatsApp webhook intentionally updates leads across workspaces
  for STOP opt-outs (suppression is global by number). Under RLS this needs an
  explicit, code-reviewed system context — added and documented in rls.py.
- The unsubscribe endpoint acts on a signed token without a session; it now
  sets the org context from the verified token claims.
- Login resolves memberships before any org context exists, so identity tables
  (users/organizations/memberships) stay app-scoped; business tables are RLS
  protected. This is deliberate and documented in migration 0006.
- README's own "not production-ready" list (MFA, password reset, invitations,
  webhook replay protection, billing controls) still stands.

## Performance & mobile

- No pagination on lead lists beyond a 500 cap; fine for current scale,
  needs real pagination in Phase 2 tables.
- Frontend is one client component tree; acceptable now, route-split in the
  rebuild keeps it that way.
- Current CSS is mobile-tolerant; the design system keeps the breakpoints.
