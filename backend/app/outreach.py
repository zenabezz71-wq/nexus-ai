"""Consent-gated, review-before-send Brevo outreach. Never runs on import."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from html import escape
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse
from jose import jwt, JWTError
from pydantic import BaseModel, Field
from sqlalchemy import select, update, String, Integer, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column, Session
from .database import Base, get_db
from .models import Lead, AuditLog, now
from .auth import current_membership
from .config import settings

router = APIRouter()
DEFAULT_SUBJECT = "A message from {sender_name}"
DEFAULT_BODY = "Hello {name},\n\nThis is a promotional message from {sender_name}. Would you like to hear more about our services?\n\nThank you,\n{sender_name}"

class OutreachTemplate(Base):
    __tablename__ = "outreach_templates"
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    subject: Mapped[str] = mapped_column(String(200), default=DEFAULT_SUBJECT)
    body: Mapped[str] = mapped_column(Text, default=DEFAULT_BODY)

class OutreachSend(Base):
    __tablename__ = "outreach_sends"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    recipient: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="reserved")
    provider_message_id: Mapped[str] = mapped_column(String(500), default="")
    error: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("organization_id", "recipient", name="uq_outreach_recipient"),)

class OutreachQuota(Base):
    __tablename__ = "outreach_quota"
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    used: Mapped[int] = mapped_column(Integer, default=0)

class OutreachSuppression(Base):
    __tablename__ = "outreach_suppressions"
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    recipient: Mapped[str] = mapped_column(String(320), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class TemplateInput(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10000)

class PreviewInput(BaseModel):
    lead_ids: list[int] = Field(min_length=1, max_length=20)

class SendInput(BaseModel):
    review_token: str = Field(min_length=1, max_length=10000)


def admin(ctx=Depends(current_membership)):
    if ctx["membership"].role not in ("owner", "admin"):
        raise HTTPException(403, "Only workspace owners/admins can send outreach")
    return ctx


def address(value):
    value = (value or "").strip().lower()
    if len(value) > 254 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}", value):
        return ""
    return value


def cap():
    return min(max(settings.outreach_daily_cap, 0), 290)


def readiness():
    missing = []
    if not settings.outreach_enabled: missing.append("Live sending is disabled (demo mode)")
    if not settings.brevo_api_key: missing.append("Brevo API key is missing")
    if not settings.outreach_sender_verified: missing.append("Sender must be verified in Brevo")
    if not address(settings.outreach_sender_email): missing.append("Valid sender email is required")
    if not settings.outreach_sender_name.strip(): missing.append("Sender name is required")
    if not settings.outreach_postal_address.strip(): missing.append("Valid sender postal address is required")
    if not settings.outreach_public_api_url.startswith("https://"): missing.append("Stable HTTPS API URL is required for unsubscribe")
    if len(settings.jwt_secret) < 32 or settings.jwt_secret.startswith("development-"):
        missing.append("A strong stable JWT signing secret is required")
    if cap() == 0: missing.append("Daily cap is zero")
    return missing


def get_template(db, org):
    template = db.get(OutreachTemplate, org)
    return {"subject": template.subject if template else DEFAULT_SUBJECT,
            "body": template.body if template else DEFAULT_BODY}


def render(text, lead):
    # Only literal replacement; untrusted lead text cannot introduce template code.
    return text.replace("{name}", (lead.name.strip() or "there")[:200]).replace("{sender_name}", settings.outreach_sender_name or "Your business")


def unsubscribe_token(org, recipient):
    # No expiry: recipients must still be able to opt out after 30 days.
    return jwt.encode({"purpose": "outreach-unsubscribe", "org": org, "email": recipient}, settings.jwt_secret, algorithm="HS256")


def content(db, lead):
    template = get_template(db, lead.organization_id)
    subject = render(template["subject"], lead).replace("\r", " ").replace("\n", " ")[:200]
    url = settings.outreach_public_api_url.rstrip("/") + "/outreach/unsubscribe?token=" + quote(unsubscribe_token(lead.organization_id, address(lead.email)), safe="")
    body = render(template["body"], lead) + "\n\nPromotional email\n" + (settings.outreach_postal_address.strip() or "[DEMO: valid sender postal address required]") + "\nUnsubscribe: " + url
    return {"lead_id": lead.id, "recipient": address(lead.email), "subject": subject, "body": body, "demo_only": is_demo(lead)}


def is_demo(lead):
    recipient = address(lead.email)
    return bool(lead.source == "sample" or re.search(r"\bdemo\b|تجريبي", lead.name or "", re.I) or recipient.endswith(("@example.com", "@example.org", "@example.net")))


def reason(db, lead, preview=False):
    if not lead.consent: return "No recorded email marketing consent"
    if lead.opted_out: return "Opted out"
    recipient = address(lead.email)
    if not recipient: return "Missing or invalid email"
    if is_demo(lead) and not preview:
        return "Demonstration addresses cannot receive outreach"
    if db.get(OutreachSuppression, (lead.organization_id, recipient)): return "Email is suppressed"
    if db.scalar(select(OutreachSend.id).where(OutreachSend.organization_id == lead.organization_id, OutreachSend.recipient == recipient)):
        return "Already attempted; no automatic resend"
    return ""


def fingerprint(messages):
    config = [settings.outreach_sender_email, settings.outreach_sender_name, settings.outreach_postal_address, settings.outreach_public_api_url]
    return hashlib.sha256(json.dumps([messages, config], sort_keys=True).encode()).hexdigest()


@router.get("/outreach/status")
def status(ctx=Depends(current_membership), db: Session=Depends(get_db)):
    day = datetime.now(timezone.utc).date().isoformat()
    quota = db.get(OutreachQuota, day)
    used = quota.used if quota else 0
    logs = db.scalars(select(OutreachSend).where(OutreachSend.organization_id == ctx["organization_id"]).order_by(OutreachSend.id.desc()).limit(100)).all()
    return {"ready": not readiness(), "blockers": readiness(), "daily_cap": cap(), "attempts_today": used,
            "remaining_today": max(0, cap()-used), "quota_day_utc": day, "provider_free_limit": 300,
            "provider_quota_note": "App reservations only; other Brevo activity also consumes its 300/day allowance. Not a delivery count.",
            "template": get_template(db, ctx["organization_id"]),
            "logs": [{"id": x.id, "lead_id": x.lead_id, "recipient": x.recipient, "status": x.status,
                      "provider_message_id": x.provider_message_id, "error": x.error, "created_at": x.created_at} for x in logs]}


@router.put("/outreach/template")
def save_template(data: TemplateInput, ctx=Depends(admin), db: Session=Depends(get_db)):
    if "\n" in data.subject or "\r" in data.subject:
        raise HTTPException(400, "Subject must be a single line")
    row = db.get(OutreachTemplate, ctx["organization_id"])
    if not row:
        row = OutreachTemplate(organization_id=ctx["organization_id"])
        db.add(row)
    row.subject, row.body = data.subject, data.body
    db.add(AuditLog(organization_id=ctx["organization_id"], actor_user_id=ctx["user"].id, action="outreach.template_updated", details={}))
    db.commit()
    return get_template(db, ctx["organization_id"])


@router.post("/outreach/preview")
def preview(data: PreviewInput, ctx=Depends(admin), db: Session=Depends(get_db)):
    messages, skipped, recipients = [], [], set()
    for ident in dict.fromkeys(data.lead_ids):
        lead = db.scalar(select(Lead).where(Lead.id == ident, Lead.organization_id == ctx["organization_id"]))
        if not lead: raise HTTPException(404, "Lead not found in workspace")
        why = reason(db, lead, preview=True)
        if not why and address(lead.email) in recipients: why = "Duplicate email in selection"
        if why: skipped.append({"lead_id": ident, "reason": why})
        else:
            messages.append(content(db, lead))
            recipients.add(address(lead.email))
    token = jwt.encode({"purpose": "outreach-review", "org": ctx["organization_id"], "user": ctx["user"].id,
                        "ids": [m["lead_id"] for m in messages], "digest": fingerprint(messages),
                        "exp": datetime.now(timezone.utc)+timedelta(minutes=10)}, settings.jwt_secret, algorithm="HS256")
    return {"messages": messages, "skipped": skipped, "review_token": token, "blockers": readiness()+(["Demo contacts are preview-only; no real send is allowed"] if any(m["demo_only"] for m in messages) else []), "sender": {"name": settings.outreach_sender_name, "email": settings.outreach_sender_email}}


def reserve(db, message, org, actor):
    day = datetime.now(timezone.utc).date().isoformat()
    if not db.get(OutreachQuota, day):
        try:
            with db.begin_nested():
                db.add(OutreachQuota(day=day, used=0)); db.flush()
        except IntegrityError: pass
    changed = db.execute(update(OutreachQuota).where(OutreachQuota.day == day, OutreachQuota.used < cap()).values(used=OutreachQuota.used+1))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(429, "App daily limit reached; wait until the next UTC day")
    entry = OutreachSend(organization_id=org, lead_id=message["lead_id"], recipient=message["recipient"], subject=message["subject"], body=message["body"], status="sending")
    db.add(entry)
    db.add(AuditLog(organization_id=org, actor_user_id=actor, action="outreach.reserved", details={"lead_id": message["lead_id"]}))
    try: db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Recipient was already reserved by another send")
    return entry


@router.post("/outreach/send")
def send(data: SendInput, ctx=Depends(admin), db: Session=Depends(get_db)):
    blockers = readiness()
    if blockers: raise HTTPException(409, "; ".join(blockers))
    try:
        reviewed = jwt.decode(data.review_token, settings.jwt_secret, algorithms=["HS256"])
        if reviewed.get("purpose") != "outreach-review" or reviewed.get("org") != ctx["organization_id"] or reviewed.get("user") != ctx["user"].id:
            raise ValueError()
        ids = reviewed["ids"]
        if not isinstance(ids, list) or not 1 <= len(ids) <= 20: raise ValueError()
    except (JWTError, ValueError, KeyError): raise HTTPException(400, "Invalid/expired review; preview again")
    messages = []
    for ident in ids:
        lead = db.scalar(select(Lead).where(Lead.id == ident, Lead.organization_id == ctx["organization_id"]))
        if not lead or reason(db, lead): raise HTTPException(409, "Eligibility changed; preview again")
        messages.append(content(db, lead))
    if fingerprint(messages) != reviewed.get("digest"): raise HTTPException(409, "Content or recipients changed; preview again")
    results = []
    for message in messages:
        # Recheck after preceding network calls and use a unique recipient reservation.
        db.expire_all()
        lead = db.get(Lead, message["lead_id"])
        if reason(db, lead):
            results.append({"lead_id": lead.id, "status": "skipped"}); continue
        try: entry = reserve(db, message, ctx["organization_id"], ctx["user"].id)
        except HTTPException as exc:
            if exc.status_code in (409, 429):
                results.append({"lead_id": message["lead_id"], "status": "not_sent", "reason": exc.detail}); break
            raise
        try:
            response = httpx.post("https://api.brevo.com/v3/smtp/email", headers={"api-key": settings.brevo_api_key, "accept": "application/json"},
                json={"sender": {"email": settings.outreach_sender_email, "name": settings.outreach_sender_name},
                      "replyTo": {"email": settings.outreach_sender_email, "name": settings.outreach_sender_name},
                      "to": [{"email": entry.recipient}], "subject": entry.subject, "textContent": entry.body,
                      "tags": ["nexus-outreach"]}, timeout=20)
            if response.status_code in (200, 201, 202):
                entry.status = "accepted"
                try: entry.provider_message_id = str(response.json().get("messageId", ""))[:500]
                except ValueError: pass
            else:
                entry.status = "rejected"
                entry.error = f"Brevo HTTP {response.status_code}; inspect provider dashboard. No automatic retry."
        except httpx.RequestError:
            entry.status = "unknown"
            entry.error = "Network outcome unknown. Check Brevo before any manual retry."
        db.add(AuditLog(organization_id=ctx["organization_id"], actor_user_id=ctx["user"].id, action="outreach."+entry.status, details={"send_id": entry.id, "lead_id": entry.lead_id}))
        db.commit()
        results.append({"lead_id": entry.lead_id, "status": entry.status})
        # Stop on any provider failure, especially quota/rate limits. No tight retries.
        if entry.status != "accepted": break
    return {"results": results, "note": "Accepted means queued by Brevo, not delivered."}


def decode_unsubscribe(token):
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        if data.get("purpose") != "outreach-unsubscribe" or not address(data.get("email")) or not isinstance(data.get("org"), int): raise ValueError()
        return data
    except (JWTError, ValueError, TypeError): raise HTTPException(400, "Invalid unsubscribe link")


@router.get("/outreach/unsubscribe", response_class=HTMLResponse)
def unsubscribe_page(token: str):
    decode_unsubscribe(token)
    return '<!doctype html><html lang="en"><meta name="viewport" content="width=device-width"><title>Unsubscribe</title><body style="font:18px system-ui;max-width:600px;margin:60px auto;padding:24px"><h1>Stop promotional emails</h1><p>Confirm to stop future outreach from this workspace.</p><form method="post"><input type="hidden" name="token" value="'+escape(token, quote=True)+'"><button type="submit" style="padding:12px">Unsubscribe</button></form></body></html>'


@router.post("/outreach/unsubscribe", response_class=HTMLResponse)
def unsubscribe(token: str=Form(...), db: Session=Depends(get_db)):
    data = decode_unsubscribe(token)
    key = (data["org"], data["email"])
    if not db.get(OutreachSuppression, key):
        try:
            with db.begin_nested():
                db.add(OutreachSuppression(organization_id=key[0], recipient=key[1])); db.flush()
        except IntegrityError: pass
    from sqlalchemy import func
    db.execute(update(Lead).where(Lead.organization_id == key[0], func.lower(func.trim(Lead.email)) == key[1]).values(opted_out=True, consent=False))
    db.commit()
    return '<!doctype html><html lang="en"><meta name="viewport" content="width=device-width"><title>Unsubscribed</title><body style="font:18px system-ui;max-width:600px;margin:60px auto;padding:24px"><h1>You are unsubscribed</h1><p>No further outreach will be sent to this email from this workspace.</p></body></html>'
