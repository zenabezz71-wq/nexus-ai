"""NEXUS Copilot: answers manager questions from live workspace data.

Rule-based intent matching (Arabic + English) over real queries. No external AI
calls, so every answer is grounded in the database and labeled with its method.
If an LLM key is ever configured, phrasing can be upgraded without changing the
data path; the method label must always say what produced the answer.
"""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import get_db
from .models import Lead, User, Membership
from .tenant import Contact, Deal, Task, Activity
from .auth import current_membership
from .rbac import has_permission, REPORTS_COMPANY
from .assistant import DEMO_SOURCE

router = APIRouter()

METHOD = "Rule-based answer computed from live workspace data; no external AI calls."


class Ask(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


def aware(v):
    if v is None:
        return None
    return v.replace(tzinfo=v.tzinfo or timezone.utc)


def has(t, *words):
    return any(w in t for w in words)


@router.post("/copilot/ask")
def ask(data: Ask, ctx=Depends(current_membership), db: Session = Depends(get_db)):
    org = ctx["organization_id"]
    me = ctx["user"].id
    company = has_permission(ctx["membership"], REPORTS_COMPANY)
    q = data.question.strip().lower()
    now = datetime.now(timezone.utc)
    today = now.date()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def scoped(model):
        stmt = select(model).where(model.organization_id == org, model.deleted_at.is_(None))
        if not company and hasattr(model, "assigned_to"):
            stmt = stmt.where(model.assigned_to == me)
        return db.scalars(stmt).all()

    leads = db.scalars(select(Lead).where(Lead.organization_id == org, Lead.source != DEMO_SOURCE)).all()
    deals = scoped(Deal)
    tasks = scoped(Task)

    # --- intent: follow-ups needed today
    if not has(q, "اكتب", "draft", "write a follow") and has(q, "متابعة", "متابعات", "follow", "محتاجين", "النهارده", "اليوم") and has(q, "متابعة", "follow", "محتاج", "مهام", "task"):
        open_tasks = [t for t in tasks if t.status == "open"]
        due_today = [t for t in open_tasks if t.due_at and aware(t.due_at).date() == today]
        overdue = [t for t in open_tasks if t.due_at and aware(t.due_at) < now and aware(t.due_at).date() != today]
        follow_leads = [x for x in leads if x.status == "follow_up"]
        lines = []
        if overdue:
            lines.append(f"{len(overdue)} overdue task(s): " + "; ".join(t.title for t in overdue[:5]))
        if due_today:
            lines.append(f"{len(due_today)} task(s) due today: " + "; ".join(t.title for t in due_today[:5]))
        if follow_leads:
            lines.append(f"{len(follow_leads)} lead(s) marked follow_up: " + "; ".join((x.name or x.phone) for x in follow_leads[:5]))
        if not lines:
            lines.append("No overdue or due-today tasks, and no leads marked follow_up. Follow-ups are under control.")
        return {"intent": "followups_today", "answer": "\n".join(lines), "method": METHOD}

    # --- intent: best salesperson this month
    if has(q, "أفضل موظف", "افضل موظف", "best salesperson", "best sales", "مين أفضل", "top performer", "أداء الموظفين", "team performance"):
        members = db.execute(
            select(User.id, User.full_name, User.email)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.organization_id == org, Membership.is_active == True, User.is_active == True)).all()
        acts = [a for a in db.scalars(select(Activity).where(Activity.organization_id == org)).all()
                if aware(a.created_at) >= month_start]
        rows = []
        for uid, name, email in members:
            won = sum(1 for d in deals if d.assigned_to == uid and d.status == "won" and aware(d.updated_at) >= month_start)
            revenue = sum(d.amount or 0 for d in deals if d.assigned_to == uid and d.status == "won" and aware(d.updated_at) >= month_start)
            activity = sum(1 for a in acts if a.user_id == uid)
            rows.append((name or email, won, revenue, activity))
        rows.sort(key=lambda r: (-r[1], -r[2], -r[3]))
        if not rows or not any(r[1] or r[2] or r[3] for r in rows):
            return {"intent": "best_salesperson", "answer": "No sales activity recorded yet this month, so there is no leader to name.", "method": METHOD}
        lines = [f"{i+1}. {n}: {w} deal(s) won, {rev:.0f} EGP, {a} activities" for i, (n, w, rev, a) in enumerate(rows[:5])]
        return {"intent": "best_salesperson",
                "answer": "Team ranking this month (won deals, then revenue, then activity):\n" + "\n".join(lines),
                "method": METHOD}

    # --- intent: deals at risk
    if has(q, "نخسر", "خطر", "risk", "at risk", "خايف", "متوقع تخسر"):
        risk_cutoff = now - timedelta(days=7)
        open_deals = [d for d in deals if d.status == "open"]
        at_risk = [d for d in open_deals
                   if (d.last_activity_at is None or aware(d.last_activity_at) < risk_cutoff)
                   or (d.expected_close is not None and d.expected_close < today)]
        if not at_risk:
            return {"intent": "deals_at_risk", "answer": "No open deals are stale (7+ days without activity) or past their expected close date.", "method": METHOD}
        lines = [f"- {d.title}" + (f" ({d.currency} {d.amount:.0f})" if d.amount else "")
                 + (f", expected close {d.expected_close}" if d.expected_close else "")
                 + (", no recorded activity" if not d.last_activity_at else f", last activity {aware(d.last_activity_at).date()}")
                 for d in at_risk[:10]]
        return {"intent": "deals_at_risk",
                "answer": f"{len(at_risk)} open deal(s) at risk:\n" + "\n".join(lines),
                "method": METHOD}

    # --- intent: monthly sales report
    if has(q, "تقرير", "report", "ملخص", "summary", "أداء المبيعات", "sales performance"):
        new_month = [x for x in leads if aware(x.created_at) >= month_start]
        won_month = [d for d in deals if d.status == "won" and aware(d.updated_at) >= month_start]
        revenue = sum(d.amount or 0 for d in won_month)
        open_deals = [d for d in deals if d.status == "open"]
        expected = sum((d.amount or 0) * (d.probability or 0) / 100 for d in open_deals)
        converted = sum(1 for x in leads if x.status == "converted")
        conv_rate = f"{converted / len(leads) * 100:.1f}%" if leads else "n/a"
        answer = (
            f"Sales report for {now.strftime('%B %Y')} so far:\n"
            f"- New leads this month: {len(new_month)} (total {len(leads)})\n"
            f"- Deals won this month: {len(won_month)} for {revenue:.0f} EGP\n"
            f"- Open pipeline: {len(open_deals)} deal(s), expected value {expected:.0f} EGP (probability-weighted)\n"
            f"- Lead conversion rate (all time, current status): {conv_rate}"
        )
        return {"intent": "sales_report", "answer": answer, "method": METHOD}

    # --- intent: draft a follow-up message
    if has(q, "اكتب رسالة", "رسالة متابعة", "write a follow", "draft", "اكتب"):
        target = None
        for x in leads:
            if (x.name and x.name.lower() in q) or (x.phone and x.phone in q):
                target = x
                break
        name = target.name if target and target.name else "there"
        answer = (
            "Draft follow-up message (edit before sending; sending always needs your confirmation):\n\n"
            f"أهلاً {name}، معاك فريق NEXUS. بنتابع معاك بخصوص استفسارك الأخير. "
            "تحب نحدد مكالمة قصيرة الأسبوع ده ولا تفضّل نبعتلك التفاصيل هنا؟"
        )
        if target:
            answer += f"\n\nMatched lead: {target.name or target.phone} (current status: {target.status})."
        else:
            answer += "\n\nNo lead name or phone was recognized in your question, so the draft uses a generic greeting."
        return {"intent": "draft_followup", "answer": answer, "method": METHOD + " The message is a fixed template, not generated text presented as AI."}

    # --- intent: lead stats
    if has(q, "كام عميل", "عدد العملاء", "how many leads", "lead stats", "إحصائيات", "stats"):
        by_status = {}
        for x in leads:
            by_status[x.status] = by_status.get(x.status, 0) + 1
        lines = [f"- {k}: {v}" for k, v in sorted(by_status.items(), key=lambda kv: -kv[1])]
        contacts = db.scalars(select(Contact).where(Contact.organization_id == org, Contact.deleted_at.is_(None))).all()
        return {"intent": "lead_stats",
                "answer": f"{len(leads)} leads and {len(contacts)} contacts in the workspace.\n" + "\n".join(lines),
                "method": METHOD}

    # --- fallback: capabilities
    return {"intent": "help",
            "answer": ("I answer from your live workspace data. Try:\n"
                       "- Who needs a follow-up today? / مين محتاج متابعة النهارده؟\n"
                       "- Who is the best salesperson this month? / مين أفضل موظف الشهر ده؟\n"
                       "- Which deals are at risk? / حلل الصفقات اللي ممكن نخسرها\n"
                       "- Sales report for this month / اعمل تقرير مبيعات الشهر ده\n"
                       "- Lead stats / إحصائيات العملاء\n"
                       "- Draft a follow-up message / اكتب رسالة متابعة"),
            "method": METHOD}
