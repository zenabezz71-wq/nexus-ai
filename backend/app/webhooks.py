"""Inbound webhooks: let external tools push leads into a workspace.

The org's webhook_key authenticates the POST without a user session. Keys are
generated lazily, rotatable by anyone with integrations.manage, and compared in
constant time. Lead creation is idempotent on (organization, phone) — the same
phone pushed twice returns the existing lead, never a duplicate.

Honest status for the other Phase 5 integrations lives in GET /integrations:
they need paid APIs or the owner's own accounts, so they are listed as
not_connected with the reason rather than faked.
"""
import hmac
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import get_db
from .models import Lead, Organization, AuditLog
from .auth import current_membership
from .rbac import has_permission, INTEGRATIONS_MANAGE
from .normalization import normalize_phone

router = APIRouter()


def _new_key():
    return secrets.token_urlsafe(32)


class WebhookLead(BaseModel):
    phone: str = Field(min_length=3, max_length=40)
    name: str = Field(default="", max_length=200)
    email: str = Field(default="", max_length=320)
    goal: str = Field(default="", max_length=2000)
    source: str = Field(default="webhook", max_length=100)
    external_id: str | None = Field(default=None, max_length=200)
    amount: float | None = None
    currency: str = Field(default="", max_length=12)


@router.post("/webhooks/leads/{key}", status_code=201)
def receive_lead(key: str, data: WebhookLead, request: Request, db: Session = Depends(get_db)):
    match = None
    for cand in db.scalars(select(Organization).where(Organization.webhook_key.isnot(None),
                                                       Organization.is_active == True,
                                                       Organization.deleted_at.is_(None))).all():
        if hmac.compare_digest(cand.webhook_key, key):
            match = cand
            break
    if not match:
        raise HTTPException(404, "Unknown webhook endpoint")
    normalized, valid = normalize_phone(data.phone)
    if not valid:
        raise HTTPException(422, "Enter a valid international phone number")
    existing = db.scalar(select(Lead).where(Lead.organization_id == match.id, Lead.phone == normalized))
    if not existing and data.external_id:
        existing = db.scalar(select(Lead).where(Lead.organization_id == match.id, Lead.external_id == data.external_id))
    if existing:
        db.add(AuditLog(organization_id=match.id, actor_user_id=None, action="webhook.lead",
                        details={"result": "deduped", "lead_id": existing.id}))
        db.commit()
        return {"ok": True, "lead_id": existing.id, "deduped": True}
    lead = Lead(organization_id=match.id, phone=normalized, name=data.name.strip(),
                email=data.email.strip().lower(), goal=data.goal.strip(),
                source=("webhook:" + data.source.strip())[:100], external_id=data.external_id,
                amount=data.amount, currency=(data.currency or "").upper(),
                status="unclassified")
    db.add(lead)
    db.flush()
    db.add(AuditLog(organization_id=match.id, actor_user_id=None, action="webhook.lead",
                    details={"result": "created", "lead_id": lead.id}))
    db.commit()
    db.refresh(lead)
    return {"ok": True, "lead_id": lead.id, "deduped": False}


def _require_manage(ctx):
    if not has_permission(ctx["membership"], INTEGRATIONS_MANAGE):
        raise HTTPException(403, "This action requires the permission: " + INTEGRATIONS_MANAGE)


@router.get("/integrations")
def integrations(request: Request, ctx=Depends(current_membership), db: Session = Depends(get_db)):
    org = db.get(Organization, ctx["organization_id"])
    manage = has_permission(ctx["membership"], INTEGRATIONS_MANAGE)
    webhook = None
    if manage:
        if not org.webhook_key:
            org.webhook_key = _new_key()
            db.commit()
        base = str(request.base_url).rstrip("/")
        webhook = {"url": f"{base}/webhooks/leads/{org.webhook_key}",
                   "note": "Secret URL. Anyone with it can add leads to this workspace. Rotate to revoke."}
    return {
        "webhook": webhook,
        "integrations": [
            {"key": "whatsapp_business", "name": "WhatsApp Business", "status": "not_connected",
             "reason": "Requires the Meta WhatsApp Business API (paid per-conversation) and the owner's Meta Business account."},
            {"key": "meta_lead_ads", "name": "Meta Lead Ads", "status": "not_connected",
             "reason": "Requires a Meta app and the owner's ad account. Leads can arrive via the webhook above in the meantime."},
            {"key": "email", "name": "Email sending", "status": "not_connected",
             "reason": "Requires an email provider account (SMTP/API key) chosen by the owner."},
            {"key": "google_calendar", "name": "Google Calendar", "status": "not_connected",
             "reason": "Requires a Google Cloud OAuth app connected with the owner's Google account."},
        ],
    }


@router.post("/integrations/webhook-key/rotate")
def rotate_webhook_key(request: Request, ctx=Depends(current_membership), db: Session = Depends(get_db)):
    _require_manage(ctx)
    org = db.get(Organization, ctx["organization_id"])
    org.webhook_key = _new_key()
    db.commit()
    base = str(request.base_url).rstrip("/")
    return {"url": f"{base}/webhooks/leads/{org.webhook_key}", "rotated": True,
            "note": "The previous URL stopped working immediately."}
