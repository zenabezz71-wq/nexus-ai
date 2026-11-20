"""Official WhatsApp Cloud API, configured separately and OFF by default.
Only approved simple text marketing templates with one name parameter are supported.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from jose import jwt, JWTError
from sqlalchemy import select, update, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, Mapped, mapped_column
from .database import Base, get_db
from .models import Lead, AuditLog, Organization, now
from .config import settings
from .outreach import admin, PreviewInput, SendInput, is_demo, trial_workspace, workspace_blockers
from .auth import current_membership

router = APIRouter()

class WhatsAppSend(Base):
    __tablename__ = "whatsapp_sends"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    recipient: Mapped[str] = mapped_column(String(40))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="sending")
    provider_message_id: Mapped[str] = mapped_column(String(500), default="", index=True)
    error: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("organization_id", "recipient", name="uq_whatsapp_recipient"),)

class WhatsAppQuota(Base):
    __tablename__ = "whatsapp_quota"
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    used: Mapped[int] = mapped_column(Integer, default=0)

class WhatsAppSuppression(Base):
    __tablename__ = "whatsapp_suppressions"
    recipient: Mapped[str] = mapped_column(String(40), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


def phone(value):
    value = (value or "").strip()
    return value.lstrip("+") if re.fullmatch(r"\+[1-9][0-9]{7,14}", value) else ""


def cap(): return min(max(settings.whatsapp_daily_cap, 0), 100)


def readiness():
    missing = []
    if not settings.whatsapp_enabled: missing.append("WhatsApp live sending is disabled")
    if not settings.whatsapp_cost_acknowledged: missing.append("Owner must approve Meta message costs before enabling")
    for field, label in [("whatsapp_access_token", "Meta access token"), ("whatsapp_phone_number_id", "Meta phone number ID"),
                         ("whatsapp_business_account_id", "WhatsApp Business account ID"), ("whatsapp_template_name", "Approved marketing template name"),
                         ("whatsapp_app_secret", "Meta app secret for signed webhooks"), ("whatsapp_webhook_verify_token", "Webhook verify token")]:
        if not getattr(settings, field): missing.append(label+" is missing")
    if not re.fullmatch(r"v\d+\.0", settings.whatsapp_graph_version): missing.append("Valid supported Graph API version is required")
    for value in [settings.whatsapp_phone_number_id, settings.whatsapp_business_account_id]:
        if value and not value.isdigit(): missing.append("Meta IDs must contain digits only")
    if len(settings.jwt_secret) < 32 or settings.jwt_secret.startswith("development-"): missing.append("Strong stable signing secret is required")
    if cap() == 0: missing.append("WhatsApp daily cap is zero")
    return missing


def template():
    if not settings.whatsapp_access_token or not settings.whatsapp_business_account_id or not settings.whatsapp_template_name:
        return None
    try:
        result = httpx.get(f"https://graph.facebook.com/{settings.whatsapp_graph_version}/{settings.whatsapp_business_account_id}/message_templates",
            headers={"Authorization": "Bearer "+settings.whatsapp_access_token},
            params={"name": settings.whatsapp_template_name, "fields": "name,status,category,language,components", "limit": 100}, timeout=20)
        if result.status_code != 200: raise ValueError()
        candidates = result.json().get("data", [])
        item = next(x for x in candidates if x.get("name") == settings.whatsapp_template_name and x.get("language") == settings.whatsapp_template_language and x.get("status") == "APPROVED" and x.get("category") == "MARKETING")
        components = item["components"]
        if any(c["type"] not in ("BODY", "FOOTER") for c in components): raise ValueError()
        body = next(c["text"] for c in components if c["type"] == "BODY")
        # A single positional name variable, no unsupported headers/buttons/media.
        if body.count("{{1}}") != 1 or re.findall(r"{{.*?}}", body) != ["{{1}}"]: raise ValueError()
        footer = "\n".join(c.get("text", "") for c in components if c["type"] == "FOOTER")
        text = body+("\n"+footer if footer else "")
        if not re.search(r"\bSTOP\b|توقف|إلغاء|الغاء", text, re.I): raise ValueError()
        return {"name": item["name"], "language": item["language"], "text": text}
    except (httpx.RequestError, ValueError, KeyError, StopIteration, TypeError):
        raise HTTPException(409, "Could not verify a supported APPROVED MARKETING template. Use BODY with exactly one {{1}} name parameter, optional static FOOTER, and STOP opt-out instructions.")


def reason(db, lead, preview=False):
    if not lead.consent: return "No recorded WhatsApp marketing consent"
    if lead.opted_out: return "Opted out"
    number = phone(lead.phone)
    if not number: return "Valid international phone number required"
    # The shipped sample CSV is not permission to message its numbers.
    if not preview and (is_demo(lead) or number in ("201005551234", "201001112233")): return "Demonstration number cannot receive outreach"
    if not db.get(Organization,lead.organization_id).trial_only and db.get(WhatsAppSuppression, number): return "Number is suppressed"
    if db.scalar(select(WhatsAppSend.id).where(WhatsAppSend.organization_id == lead.organization_id, WhatsAppSend.recipient == number)): return "Already attempted; no automatic resend"
    return ""


def digest(messages):
    return hashlib.sha256(json.dumps([messages, settings.whatsapp_phone_number_id, settings.whatsapp_template_name, settings.whatsapp_template_language], sort_keys=True).encode()).hexdigest()


def message(lead, tmpl):
    name = re.sub(r"[\r\n\t]+", " ", lead.name.strip() or "there")[:100]
    return {"lead_id": lead.id, "recipient": phone(lead.phone), "name": name,
            "body": tmpl["text"].replace("{{1}}", name), "template": tmpl["name"], "language": tmpl["language"], "demo_only": is_demo(lead) or tmpl["name"] == "demo_only_not_approved"}


@router.get("/whatsapp/status")
def status(ctx=Depends(current_membership), db: Session=Depends(get_db)):
    day = datetime.now(timezone.utc).date().isoformat()
    quota = db.get(WhatsAppQuota, day)
    used = quota.used if quota and not trial_workspace(db,ctx) else 0
    logs = db.scalars(select(WhatsAppSend).where(WhatsAppSend.organization_id == ctx["organization_id"]).order_by(WhatsAppSend.id.desc()).limit(100)).all()
    return {"ready": not (readiness()+workspace_blockers(db,ctx)), "blockers": readiness()+workspace_blockers(db,ctx), "daily_cap": cap(), "attempts_today": used,
            "remaining_today": max(0, cap()-used), "quota_day_utc": day, "template_name": "" if trial_workspace(db,ctx) else settings.whatsapp_template_name,
            "cost_note": "Official Meta marketing messages can cost money. No account or billing setup is created by this app.",
            "logs": [{"lead_id": x.lead_id, "recipient": x.recipient, "status": x.status, "error": x.error, "provider_message_id": x.provider_message_id} for x in logs]}


@router.post("/whatsapp/preview")
def preview(data: PreviewInput, ctx=Depends(admin), db: Session=Depends(get_db)):
    tmpl = None if trial_workspace(db,ctx) else template()
    demo_template = tmpl is None
    if demo_template:
        tmpl = {"name": "demo_only_not_approved", "language": "en_US", "text": "DEMO ONLY, not a Meta-approved template. Hello {{1}}, this is an example promotional message. Reply STOP to opt out."}
    messages, skipped, numbers = [], [], set()
    for ident in dict.fromkeys(data.lead_ids):
        lead = db.scalar(select(Lead).where(Lead.id == ident, Lead.organization_id == ctx["organization_id"]))
        if not lead: raise HTTPException(404, "Lead not found in workspace")
        why = reason(db, lead, preview=True)
        if not why and phone(lead.phone) in numbers: why = "Duplicate phone in selection"
        if why: skipped.append({"lead_id": ident, "reason": why})
        else: messages.append(message(lead, tmpl)); numbers.add(phone(lead.phone))
    token = jwt.encode({"purpose": "whatsapp-review", "org": ctx["organization_id"], "user": ctx["user"].id,
        "ids": [m["lead_id"] for m in messages], "digest": digest(messages), "exp": datetime.now(timezone.utc)+timedelta(minutes=10)}, settings.jwt_secret, algorithm="HS256")
    return {"messages": messages, "skipped": skipped, "review_token": "" if demo_template else token, "blockers": readiness()+workspace_blockers(db,ctx)+(["Illustrative demo only. No approved Meta template is configured"] if demo_template else [])+(["Demo contacts are preview-only; no real send is allowed"] if any(m["demo_only"] for m in messages) else [])}


@router.post("/whatsapp/send")
def send(data: SendInput, ctx=Depends(admin), db: Session=Depends(get_db)):
    blockers = readiness()+workspace_blockers(db,ctx)
    if blockers: raise HTTPException(409, "; ".join(blockers))
    try:
        reviewed = jwt.decode(data.review_token, settings.jwt_secret, algorithms=["HS256"])
        if reviewed.get("purpose") != "whatsapp-review" or reviewed.get("org") != ctx["organization_id"] or reviewed.get("user") != ctx["user"].id: raise ValueError()
        ids = reviewed["ids"]
        if not isinstance(ids, list) or not 1 <= len(ids) <= 20: raise ValueError()
    except (JWTError, KeyError, ValueError): raise HTTPException(400, "Invalid/expired review; preview again")
    tmpl = None if trial_workspace(db,ctx) else template()
    messages = []
    for ident in ids:
        lead = db.scalar(select(Lead).where(Lead.id == ident, Lead.organization_id == ctx["organization_id"]))
        if not lead or reason(db, lead): raise HTTPException(409, "Eligibility changed; preview again")
        messages.append(message(lead, tmpl))
    if digest(messages) != reviewed.get("digest"): raise HTTPException(409, "Content or recipients changed; preview again")
    results = []
    for item in messages:
        db.expire_all()
        lead = db.get(Lead, item["lead_id"])
        if reason(db, lead): results.append({"lead_id": lead.id, "status": "skipped"}); continue
        day = datetime.now(timezone.utc).date().isoformat()
        if not db.get(WhatsAppQuota, day):
            try:
                with db.begin_nested(): db.add(WhatsAppQuota(day=day, used=0)); db.flush()
            except IntegrityError: pass
        changed = db.execute(update(WhatsAppQuota).where(WhatsAppQuota.day == day, WhatsAppQuota.used < cap()).values(used=WhatsAppQuota.used+1))
        if changed.rowcount != 1:
            db.rollback(); results.append({"lead_id": lead.id, "status": "not_sent", "reason": "Daily cap reached"}); break
        entry = WhatsAppSend(organization_id=ctx["organization_id"], lead_id=lead.id, recipient=item["recipient"], body=item["body"], status="sending")
        db.add(entry)
        try: db.commit()
        except IntegrityError:
            db.rollback(); results.append({"lead_id": item["lead_id"], "status": "not_sent", "reason": "Already reserved"}); break
        try:
            response = httpx.post(f"https://graph.facebook.com/{settings.whatsapp_graph_version}/{settings.whatsapp_phone_number_id}/messages",
                headers={"Authorization": "Bearer "+settings.whatsapp_access_token},
                json={"messaging_product": "whatsapp", "recipient_type": "individual", "to": entry.recipient,
                      "type": "template", "template": {"name": tmpl["name"], "language": {"code": tmpl["language"]},
                      "components": [{"type": "body", "parameters": [{"type": "text", "text": item["name"]}]}]}}, timeout=20)
            if response.status_code in (200, 201):
                entry.status = "accepted"
                try: entry.provider_message_id = str(response.json()["messages"][0]["id"])[:500]
                except (ValueError, KeyError, IndexError, TypeError): pass
            else:
                entry.status = "rejected"; entry.error = f"Meta HTTP {response.status_code}; inspect WhatsApp Manager. No automatic retry."
        except httpx.RequestError:
            entry.status = "unknown"; entry.error = "Network outcome unknown; check WhatsApp Manager before any manual retry."
        db.add(AuditLog(organization_id=ctx["organization_id"], actor_user_id=ctx["user"].id, action="whatsapp."+entry.status, details={"lead_id": entry.lead_id, "send_id": entry.id}))
        db.commit()
        results.append({"lead_id": entry.lead_id, "status": entry.status})
        if entry.status != "accepted": break
    return {"results": results, "note": "Accepted is not delivered. Signed callbacks update delivery status."}


@router.get("/whatsapp/webhook", response_class=PlainTextResponse)
def verify_webhook(request: Request):
    query = request.query_params
    if settings.whatsapp_webhook_verify_token and query.get("hub.mode") == "subscribe" and hmac.compare_digest(query.get("hub.verify_token", ""), settings.whatsapp_webhook_verify_token):
        return query.get("hub.challenge", "")
    raise HTTPException(403, "Verification failed")


@router.post("/whatsapp/webhook")
async def webhook(request: Request, db: Session=Depends(get_db)):
    if not settings.whatsapp_app_secret: raise HTTPException(503, "Webhook is not configured")
    raw = await request.body()
    if len(raw) > 1000000: raise HTTPException(413, "Payload too large")
    expected = "sha256="+hmac.new(settings.whatsapp_app_secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(request.headers.get("x-hub-signature-256", ""), expected): raise HTTPException(403, "Invalid signature")
    try: payload = json.loads(raw)
    except ValueError: raise HTTPException(400, "Invalid JSON")
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            if str(value.get("metadata", {}).get("phone_number_id", "")) != settings.whatsapp_phone_number_id: continue
            for msg in value.get("messages", []):
                text = str(msg.get("text", {}).get("body", "")).strip().casefold()
                if text in {"stop", "unsubscribe", "cancel", "end", "quit", "توقف", "الغاء", "إلغاء", "إلغاء الاشتراك", "الغاء الاشتراك"}:
                    number = phone("+"+str(msg.get("from", "")).lstrip("+"))
                    if number:
                        if not db.get(WhatsAppSuppression, number):
                            try:
                                with db.begin_nested(): db.add(WhatsAppSuppression(recipient=number)); db.flush()
                            except IntegrityError: pass
                        db.execute(update(Lead).where(Lead.phone == "+"+number).values(opted_out=True, consent=False))
            for event in value.get("statuses", []):
                row = db.scalar(select(WhatsAppSend).where(WhatsAppSend.provider_message_id == event.get("id", ""), WhatsAppSend.provider_message_id != ""))
                state = event.get("status")
                if row and state in ("sent", "delivered", "read", "failed"):
                    rank = {"sending": 0, "accepted": 0, "unknown": 0, "sent": 1, "delivered": 2, "read": 3, "failed": 1}
                    if rank.get(state, 0) > rank.get(row.status, 0): row.status = state
    db.commit()
    return {"ok": True}
