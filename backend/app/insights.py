"""Sales Insights: rule-based lead scoring and pipeline forecasting.

Both endpoints compute from live workspace data with transparent factor
breakdowns. No external AI calls; every response carries a method label so
users know exactly how the numbers were produced.
"""
from collections import defaultdict
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import get_db
from .models import Lead
from .tenant import Deal, Task, Activity
from .auth import current_membership
from .rbac import has_permission, REPORTS_COMPANY
from .assistant import DEMO_SOURCE

router = APIRouter()

METHOD = "Rule-based score computed from live workspace data; no external AI calls. Factors are listed per lead."
FORECAST_METHOD = "Rule-based forecast: open deal amount x stage probability, grouped by expected close month. No external AI calls."

STATUS_POINTS = {"hot_lead": 40, "warm_lead": 25, "follow_up": 20, "unclassified": 5, "cold_lead": 5, "not_interested": 0}


def aware(v):
    if v is None:
        return None
    return v.replace(tzinfo=v.tzinfo or timezone.utc)


@router.get("/insights/lead-scores")
def lead_scores(ctx=Depends(current_membership), db: Session = Depends(get_db)):
    org = ctx["organization_id"]
    now = datetime.now(timezone.utc)
    leads = db.scalars(select(Lead).where(Lead.organization_id == org, Lead.source != DEMO_SOURCE)).all()
    acts = db.scalars(select(Activity).where(Activity.organization_id == org, Activity.lead_id.isnot(None))).all()
    act_count = defaultdict(int)
    for a in acts:
        act_count[a.lead_id] += 1
    open_tasks = db.scalars(select(Task.lead_id).where(Task.organization_id == org, Task.status == "open",
                                                       Task.lead_id.isnot(None), Task.deleted_at.is_(None))).all()
    tasked = set(open_tasks)

    out = []
    for x in leads:
        if x.status in ("converted", "not_interested") or x.opted_out:
            continue
        factors = []
        score = 0
        pts = STATUS_POINTS.get(x.status, 5)
        score += pts
        factors.append(f"Status {x.status.replace('_', ' ')}: +{pts}")
        conf = round((x.confidence or 0) * 10)
        if x.status != "unclassified" and conf:
            score += conf
            factors.append(f"Classification confidence {round((x.confidence or 0)*100)}%: +{conf}")
        age_days = (now - aware(x.created_at)).days if aware(x.created_at) else 999
        if age_days <= 7:
            score += 15; factors.append("New this week: +15")
        elif age_days <= 30:
            score += 8; factors.append("New this month: +8")
        n = act_count.get(x.id, 0)
        if n >= 3:
            score += 15; factors.append(f"{n} logged activities: +15")
        elif n >= 1:
            score += 10; factors.append(f"{n} logged activit{'ies' if n > 1 else 'y'}: +10")
        if x.id in tasked:
            score += 10; factors.append("Open follow-up task: +10")
        if x.amount:
            score += 10; factors.append(f"Value indicated ({x.amount:.0f} {x.currency or 'EGP'}): +10")
        if x.email:
            score += 5; factors.append("Email on file: +5")
        out.append({"lead_id": x.id, "name": x.name or x.phone, "phone": x.phone, "status": x.status,
                    "score": min(score, 100), "factors": factors})
    out.sort(key=lambda r: -r["score"])
    return {"scores": out[:20], "total_scored": len(out), "method": METHOD}


@router.get("/insights/forecast")
def forecast(ctx=Depends(current_membership), db: Session = Depends(get_db)):
    org = ctx["organization_id"]
    me = ctx["user"].id
    company = has_permission(ctx["membership"], REPORTS_COMPANY)
    stmt = select(Deal).where(Deal.organization_id == org, Deal.deleted_at.is_(None), Deal.status == "open")
    if not company:
        stmt = stmt.where(Deal.assigned_to == me)
    deals = db.scalars(stmt).all()

    now = datetime.now(timezone.utc)
    months = defaultdict(lambda: {"deals": 0, "amount": 0.0, "weighted": 0.0})
    unscheduled = {"deals": 0, "amount": 0.0, "weighted": 0.0}
    for d in deals:
        amt = d.amount or 0
        w = amt * (d.probability or 0) / 100
        if d.expected_close:
            key = d.expected_close.strftime("%Y-%m")
            months[key]["deals"] += 1; months[key]["amount"] += amt; months[key]["weighted"] += w
        else:
            unscheduled["deals"] += 1; unscheduled["amount"] += amt; unscheduled["weighted"] += w
    month_rows = [{"month": k, **v} for k, v in sorted(months.items())]
    total_amt = sum(r["amount"] for r in month_rows) + unscheduled["amount"]
    total_w = sum(r["weighted"] for r in month_rows) + unscheduled["weighted"]
    return {
        "scope": "company" if company else "own",
        "open_deals": len(deals),
        "total_amount": round(total_amt, 2),
        "weighted_total": round(total_w, 2),
        "by_month": month_rows,
        "unscheduled": unscheduled,
        "method": FORECAST_METHOD,
    }
