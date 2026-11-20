"""Executive dashboard: real aggregates from workspace data. No external AI calls."""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .database import get_db
from .models import Lead, User, Membership
from .tenant import Contact, Deal, Task, Activity
from .auth import current_membership
from .rbac import has_permission, REPORTS_COMPANY, REPORTS_OWN
from .assistant import DEMO_SOURCE

router = APIRouter()

PERIODS = {"day": 1, "week": 7, "month": 30}


def aware(value):
    """SQLite returns naive datetimes; treat them as UTC."""
    if value is None:
        return None
    return value.replace(tzinfo=value.tzinfo or timezone.utc)


@router.get("/dashboard/executive")
def executive(period: str = "week", ctx=Depends(current_membership), db: Session = Depends(get_db)):
    if period not in PERIODS:
        raise HTTPException(400, "period must be one of: day, week, month")
    company = has_permission(ctx["membership"], REPORTS_COMPANY)
    if not company and not has_permission(ctx["membership"], REPORTS_OWN):
        raise HTTPException(403, "This action requires the permission: " + REPORTS_OWN)
    org = ctx["organization_id"]
    me = ctx["user"].id
    days = PERIODS[period]
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    prev_start = start - timedelta(days=days)

    def scoped(model):
        stmt = select(model).where(model.organization_id == org, model.deleted_at.is_(None))
        if not company and hasattr(model, "assigned_to"):
            stmt = stmt.where(model.assigned_to == me)
        return stmt

    # Leads (not soft-deleted; demo-source excluded to match the rest of the app)
    lead_stmt = select(Lead).where(Lead.organization_id == org, Lead.source != DEMO_SOURCE)
    leads = db.scalars(lead_stmt).all()
    total_leads = len(leads)
    converted = sum(1 for x in leads if x.status == "converted")
    new_period = sum(1 for x in leads if aware(x.created_at) >= start)
    new_prev = sum(1 for x in leads if prev_start <= aware(x.created_at) < start)
    sources = {}
    for x in leads:
        sources[x.source or "unknown"] = sources.get(x.source or "unknown", 0) + 1
    top_sources = sorted(({"source": k, "leads": v} for k, v in sources.items()),
                         key=lambda r: -r["leads"])[:5]

    # Deals
    deals = db.scalars(scoped(Deal)).all()
    open_deals = [d for d in deals if d.status == "open"]
    won_period = [d for d in deals if d.status == "won" and aware(d.updated_at) >= start]
    won_prev = [d for d in deals if d.status == "won" and prev_start <= aware(d.updated_at) < start]
    revenue = sum(d.amount or 0 for d in won_period)
    revenue_prev = sum(d.amount or 0 for d in won_prev)
    pipeline_value = sum(d.amount or 0 for d in open_deals)
    expected_revenue = round(sum((d.amount or 0) * (d.probability or 0) / 100 for d in open_deals), 2)

    # Deals at risk: open and (no activity in 7+ days) or expected close passed
    risk_cutoff = now - timedelta(days=7)
    today = now.date()
    at_risk = [d for d in open_deals
               if (d.last_activity_at is None or aware(d.last_activity_at) < risk_cutoff)
               or (d.expected_close is not None and d.expected_close < today)]
    at_risk.sort(key=lambda d: (d.expected_close is None, d.expected_close or today))
    risk_ids = {d.id for d in at_risk}

    # Tasks due today and overdue
    tasks = db.scalars(scoped(Task)).all()
    open_tasks = [t for t in tasks if t.status == "open"]
    due_today = [t for t in open_tasks if t.due_at is not None and aware(t.due_at).date() == today]
    overdue = [t for t in open_tasks if t.due_at is not None and aware(t.due_at) < now and aware(t.due_at).date() != today]

    # Team performance (company view only): won deals and logged activities per member in period
    team = []
    if company:
        members = db.execute(
            select(User.id, User.full_name, User.email)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.organization_id == org, Membership.is_active == True, User.is_active == True)
        ).all()
        acts_period = [a for a in db.scalars(
            select(Activity).where(Activity.organization_id == org)
        ).all() if aware(a.created_at) >= start]
        for uid, name, email in members:
            team.append({
                "user_id": uid,
                "name": name or email,
                "deals_won": sum(1 for d in won_period if d.assigned_to == uid),
                "open_deals": sum(1 for d in open_deals if d.assigned_to == uid),
                "activities": sum(1 for a in acts_period if a.user_id == uid),
            })
        team.sort(key=lambda r: (-r["deals_won"], -r["activities"]))

    def pct_change(cur, prev):
        if prev:
            return round((cur - prev) / prev * 100, 1)
        return None

    conversion_rate = round(converted / total_leads * 100, 1) if total_leads else None

    # NEXUS Intelligence: rule-based statements, each with its period and sample
    insights = []
    if revenue_prev:
        change = pct_change(revenue, revenue_prev)
        direction = "up" if change >= 0 else "down"
        insights.append(
            f"Revenue from won deals is {direction} {abs(change)}% versus the previous {period} "
            f"({revenue:.0f} vs {revenue_prev:.0f} EGP, {len(won_period)} vs {len(won_prev)} deals won)."
        )
    elif revenue:
        insights.append(
            f"{revenue:.0f} EGP won across {len(won_period)} deals this {period}; "
            f"no won deals in the previous {period} to compare against."
        )
    if new_period or new_prev:
        if new_prev:
            change = pct_change(new_period, new_prev)
            direction = "up" if change >= 0 else "down"
            insights.append(
                f"New leads are {direction} {abs(change)}% versus the previous {period} "
                f"({new_period} vs {new_prev} leads)."
            )
        else:
            insights.append(f"{new_period} new leads this {period}; none arrived in the previous {period}.")
    if risk_ids:
        insights.append(
            f"{len(risk_ids)} open deal(s) are at risk: no recorded activity in 7+ days or an expected close date that has passed."
        )
    if overdue:
        insights.append(f"{len(overdue)} open task(s) are overdue.")
    if not insights:
        insights.append("Not enough workspace data in this period for insights yet. Import leads and work deals to see trends here.")

    return {
        "period": period,
        "period_days": days,
        "period_start": start.isoformat(),
        "period_end": now.isoformat(),
        "scope": "company" if company else "own",
        "total_leads": total_leads,
        "new_leads_period": new_period,
        "new_leads_change_pct": pct_change(new_period, new_prev),
        "active_deals": len(open_deals),
        "pipeline_value": pipeline_value,
        "revenue_period": revenue,
        "revenue_change_pct": pct_change(revenue, revenue_prev),
        "deals_won_period": len(won_period),
        "expected_revenue": expected_revenue,
        "conversion_rate_pct": conversion_rate,
        "conversion_note": "Converted leads divided by all imported leads (current status, not a historical funnel).",
        "top_lead_sources": top_sources,
        "deals_at_risk": [
            {"id": d.id, "title": d.title, "amount": d.amount, "currency": d.currency,
             "expected_close": str(d.expected_close) if d.expected_close else None,
             "last_activity_at": aware(d.last_activity_at).isoformat() if d.last_activity_at else None}
            for d in at_risk[:10]
        ],
        "tasks_due_today": [{"id": t.id, "title": t.title, "due_at": aware(t.due_at).isoformat()} for t in due_today],
        "tasks_overdue": [{"id": t.id, "title": t.title, "due_at": aware(t.due_at).isoformat()} for t in overdue[:10]],
        "tasks_overdue_count": len(overdue),
        "team": team,
        "insights": insights,
        "insights_method": "Rule-based statements computed from workspace data over the selected period; no external AI calls.",
    }
