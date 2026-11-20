"""Workspace-scoped lead editing, assignment and append-only sales feedback."""
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, Session
from sqlalchemy.exc import IntegrityError
from .database import Base, get_db
from .models import Lead, User, Membership, AuditLog, Organization, now
from .auth import current_membership
from .normalization import normalize_phone
from .outreach import address, OutreachSuppression
from .whatsapp import phone, WhatsAppSuppression
router = APIRouter()

class LeadSales(Base):
    __tablename__ = "lead_sales"
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

class SalesFeedback(Base):
    __tablename__ = "sales_feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    author_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

Status = Literal["unclassified", "hot_lead", "warm_lead", "cold_lead", "follow_up", "not_interested", "invalid_number", "contacted", "qualified", "won", "lost"]
class LeadPatch(BaseModel):
    expected_updated_at: datetime
    name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=320)
    goal: str | None = Field(default=None, max_length=10000)
    currency: str | None = Field(default=None, max_length=12)
    amount: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    status: Status | None = None
    assigned_user_id: int | None = None
    do_not_contact: bool = False
class NoteInput(BaseModel):
    body: str = Field(min_length=1, max_length=5000)

def scoped_lead(db, ident, org, lock=False):
    stmt = select(Lead).where(Lead.id == ident, Lead.organization_id == org)
    if lock: stmt = stmt.with_for_update()
    lead = db.scalar(stmt)
    if not lead: raise HTTPException(404, "Lead not found in workspace")
    return lead

def stamp(value):
    return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc)

def detail(db, lead):
    assignment = db.get(LeadSales, lead.id)
    notes = db.execute(select(SalesFeedback, User.full_name, User.email).join(User, User.id == SalesFeedback.author_user_id).where(SalesFeedback.lead_id == lead.id, SalesFeedback.organization_id == lead.organization_id).order_by(SalesFeedback.created_at.desc(), SalesFeedback.id.desc()).limit(100)).all()
    return {"id": lead.id, "name": lead.name, "phone": lead.phone, "email": lead.email, "status": lead.status, "goal": lead.goal,
            "currency": lead.currency, "amount": lead.amount, "source": lead.source, "consent": lead.consent,
            "opted_out": lead.opted_out, "updated_at": stamp(lead.updated_at).isoformat(),
            "assigned_user_id": assignment.assigned_user_id if assignment else None,
            "feedback": [{"id": n.id, "body": n.body, "author": name or email, "author_user_id": n.author_user_id, "created_at": stamp(n.created_at).isoformat()} for n, name, email in notes]}

@router.get("/workspace/salespeople")
def salespeople(ctx=Depends(current_membership), db: Session=Depends(get_db)):
    rows = db.execute(select(User.id, User.full_name, User.email).join(Membership, Membership.user_id == User.id).where(Membership.organization_id == ctx["organization_id"], Membership.is_active == True, User.is_active == True).order_by(User.full_name, User.id)).all()
    return [{"id": ident, "name": name or email} for ident, name, email in rows]

@router.get("/leads/{lead_id}")
def get_lead(lead_id: int, ctx=Depends(current_membership), db: Session=Depends(get_db)):
    return detail(db, scoped_lead(db, lead_id, ctx["organization_id"]))

@router.patch("/leads/{lead_id}")
def edit_lead(lead_id: int, data: LeadPatch, ctx=Depends(current_membership), db: Session=Depends(get_db)):
    lead = scoped_lead(db, lead_id, ctx["organization_id"], lock=True)
    if stamp(lead.updated_at) != stamp(data.expected_updated_at): raise HTTPException(409, "This lead changed. Reopen it before saving to avoid overwriting someone else's work.")
    fields = data.model_fields_set - {"expected_updated_at", "do_not_contact"}
    contact_changed = False
    status_changed = "status" in fields and data.status != lead.status
    if "assigned_user_id" in fields and data.assigned_user_id is not None:
        membership = db.scalar(select(Membership).join(User, User.id == Membership.user_id).where(Membership.user_id == data.assigned_user_id, Membership.organization_id == ctx["organization_id"], Membership.is_active == True, User.is_active == True))
        if not membership: raise HTTPException(400, "Assignee must be an active member of this workspace")
    if "phone" in fields:
        normalized, valid = normalize_phone(data.phone or "")
        if not valid: raise HTTPException(400, "Enter a valid international phone number")
        if normalized != lead.phone: contact_changed = True
        lead.phone = normalized
    if "email" in fields:
        normalized = address(data.email)
        if (data.email or "").strip() and not normalized: raise HTTPException(400, "Enter a valid email or leave it blank")
        if normalized != address(lead.email): contact_changed = True
        lead.email = normalized
    for key in fields - {"phone", "email", "assigned_user_id"}:
        value = getattr(data, key)
        if value is None and key != "amount": raise HTTPException(400, key+" cannot be null")
        setattr(lead, key, value.strip() if isinstance(value, str) else value)
    if "currency" in fields: lead.currency = lead.currency.upper()
    if status_changed:
        lead.classification_reason = "Status set manually by a workspace salesperson"
        lead.confidence = 1
    if contact_changed: lead.consent = False
    if data.do_not_contact:
        lead.opted_out = True; lead.consent = False
        email = address(lead.email); number = phone(lead.phone)
        if email and not db.get(OutreachSuppression, (lead.organization_id, email)): db.add(OutreachSuppression(organization_id=lead.organization_id, recipient=email))
        if number and not db.get(Organization,lead.organization_id).trial_only and not db.get(WhatsAppSuppression, number): db.add(WhatsAppSuppression(recipient=number))
    if "assigned_user_id" in fields:
        assignment = db.get(LeadSales, lead.id)
        if not assignment: assignment = LeadSales(lead_id=lead.id, organization_id=lead.organization_id); db.add(assignment)
        assignment.assigned_user_id = data.assigned_user_id
    lead.updated_at = now()
    db.add(AuditLog(organization_id=lead.organization_id, actor_user_id=ctx["user"].id, action="lead.edited", details={"lead_id": lead.id, "fields": sorted(fields), "contact_changed_consent_reset": contact_changed, "do_not_contact": data.do_not_contact}))
    try: db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(409, "Duplicate phone or concurrent update. Refresh and try again.")
    return detail(db, lead)

@router.post("/leads/{lead_id}/feedback")
def add_feedback(lead_id: int, data: NoteInput, ctx=Depends(current_membership), db: Session=Depends(get_db)):
    lead = scoped_lead(db, lead_id, ctx["organization_id"])
    body = data.body.strip()
    if not body: raise HTTPException(400, "Feedback cannot be blank")
    note = SalesFeedback(organization_id=lead.organization_id, lead_id=lead.id, author_user_id=ctx["user"].id, body=body)
    db.add(note); db.flush()
    db.add(AuditLog(organization_id=lead.organization_id, actor_user_id=ctx["user"].id, action="lead.feedback_added", details={"lead_id": lead.id, "feedback_id": note.id}))
    db.commit()
    return detail(db, lead)
