"""Phase 2 Core CRM API: contacts, pipelines, deals, tasks, activities.

Org-scoped through current_membership (+ PostgreSQL RLS backstop from Phase 1).
Visibility: holders of contacts.view_all see everything in the workspace;
others see records they own or are assigned to. Deletes are soft.
Every mutation that matters writes an Activity row (the activity timeline).
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, or_, func
from sqlalchemy.orm import Session
from .database import get_db
from .auth import current_membership
from .models import Lead, AuditLog
from .tenant import Contact, Pipeline, PipelineStage, Deal, Task, Activity
from .rbac import has_permission, CONTACTS_VIEW_ALL, CONTACTS_EXPORT, DEALS_DELETE, COMPANY_SETTINGS

router = APIRouter()

DEFAULT_STAGES = [
    ("New", 0, 0, False, False),
    ("Contacted", 1, 20, False, False),
    ("Qualified", 2, 40, False, False),
    ("Proposal", 3, 60, False, False),
    ("Negotiation", 4, 80, False, False),
    ("Won", 5, 100, True, False),
    ("Lost", 6, 0, False, True),
]


def utcnow():
    return datetime.now(timezone.utc)


def view_all(ctx):
    return has_permission(ctx["membership"], CONTACTS_VIEW_ALL)


def visible(model, ctx):
    """WHERE clause: whole workspace for view_all holders, else own/assigned."""
    if view_all(ctx):
        return model.organization_id == ctx["organization_id"]
    me = ctx["user"].id
    return (model.organization_id == ctx["organization_id"]) & or_(
        model.assigned_to == me, model.created_by == me
    )


def get_scoped(db, model, ident, ctx):
    row = db.scalar(select(model).where(
        model.id == ident, visible(model, ctx), model.deleted_at.is_(None)
    ))
    if not row:
        raise HTTPException(404, "Not found in this workspace")
    return row


def log_activity(db, ctx, kind, body, contact_id=None, deal_id=None, lead_id=None):
    db.add(Activity(
        organization_id=ctx["organization_id"], kind=kind, body=body,
        user_id=ctx["user"].id, contact_id=contact_id, deal_id=deal_id, lead_id=lead_id,
    ))


def contact_view(c: Contact):
    return {"id": c.id, "name": c.name, "phone": c.phone, "email": c.email,
            "company": c.company, "position": c.position, "source": c.source,
            "priority": c.priority, "tags": c.tags or [], "notes": c.notes,
            "lead_id": c.lead_id, "assigned_to": c.assigned_to,
            "created_at": c.created_at.isoformat() if c.created_at else None}


def deal_view(d: Deal):
    return {"id": d.id, "title": d.title, "contact_id": d.contact_id,
            "lead_id": d.lead_id, "pipeline_id": d.pipeline_id, "stage_id": d.stage_id,
            "amount": d.amount, "currency": d.currency,
            "expected_close": d.expected_close.isoformat() if d.expected_close else None,
            "probability": d.probability, "status": d.status, "next_step": d.next_step,
            "assigned_to": d.assigned_to,
            "last_activity_at": d.last_activity_at.isoformat() if d.last_activity_at else None,
            "created_at": d.created_at.isoformat() if d.created_at else None}


def task_view(t: Task):
    return {"id": t.id, "title": t.title, "description": t.description,
            "status": t.status, "priority": t.priority,
            "due_at": t.due_at.isoformat() if t.due_at else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            "contact_id": t.contact_id, "deal_id": t.deal_id, "lead_id": t.lead_id,
            "assigned_to": t.assigned_to,
            "created_at": t.created_at.isoformat() if t.created_at else None}


class ContactInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=320)
    company: str = Field(default="", max_length=200)
    position: str = Field(default="", max_length=120)
    source: str = Field(default="manual", max_length=100)
    priority: str = Field(default="normal", max_length=20)
    tags: list[str] = Field(default_factory=list, max_length=20)
    notes: str = Field(default="", max_length=10000)


class ContactPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=320)
    company: str | None = Field(default=None, max_length=200)
    position: str | None = Field(default=None, max_length=120)
    source: str | None = Field(default=None, max_length=100)
    priority: str | None = Field(default=None, max_length=20)
    tags: list[str] | None = None
    notes: str | None = Field(default=None, max_length=10000)
    assigned_to: int | None = None


class DealInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    contact_id: int | None = None
    amount: float | None = None
    currency: str = Field(default="EGP", max_length=12)
    expected_close: str | None = None
    next_step: str = Field(default="", max_length=300)


class DealPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    contact_id: int | None = None
    stage_id: int | None = None
    amount: float | None = None
    currency: str | None = Field(default=None, max_length=12)
    expected_close: str | None = None
    next_step: str | None = Field(default=None, max_length=300)
    assigned_to: int | None = None


class TaskInput(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=10000)
    priority: str = Field(default="normal", max_length=20)
    due_at: str | None = None
    contact_id: int | None = None
    deal_id: int | None = None
    lead_id: int | None = None


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=10000)
    status: str | None = Field(default=None, max_length=20)
    priority: str | None = Field(default=None, max_length=20)
    due_at: str | None = None
    assigned_to: int | None = None


class ActivityInput(BaseModel):
    kind: str = Field(default="note", max_length=40)
    body: str = Field(min_length=1, max_length=10000)
    contact_id: int | None = None
    deal_id: int | None = None
    lead_id: int | None = None


def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, "Invalid datetime: " + value)


def parse_date(value):
    dt = parse_dt(value)
    return dt.date() if dt else None


# ---------- pipelines ----------

def ensure_default_pipeline(db, org, user_id):
    pipe = db.scalar(select(Pipeline).where(Pipeline.organization_id == org, Pipeline.deleted_at.is_(None)).order_by(Pipeline.is_default.desc(), Pipeline.id))
    if pipe:
        return pipe
    pipe = Pipeline(organization_id=org, name="Sales Pipeline", is_default=True, created_by=user_id)
    db.add(pipe)
    db.flush()
    for name, pos, prob, won, lost in DEFAULT_STAGES:
        db.add(PipelineStage(organization_id=org, pipeline_id=pipe.id, name=name,
                             position=pos, probability=prob, is_won=won, is_lost=lost))
    db.flush()
    return pipe


@router.get("/pipelines")
def pipelines(ctx=Depends(current_membership), db: Session = Depends(get_db)):
    pipe = ensure_default_pipeline(db, ctx["organization_id"], ctx["user"].id)
    db.commit()
    pipes = db.scalars(select(Pipeline).where(Pipeline.organization_id == ctx["organization_id"], Pipeline.deleted_at.is_(None)).order_by(Pipeline.id)).all()
    out = []
    for p in pipes:
        stages = db.scalars(select(PipelineStage).where(PipelineStage.pipeline_id == p.id, PipelineStage.deleted_at.is_(None)).order_by(PipelineStage.position, PipelineStage.id)).all()
        out.append({"id": p.id, "name": p.name, "is_default": p.is_default,
                    "stages": [{"id": s.id, "name": s.name, "position": s.position,
                                "probability": s.probability, "is_won": s.is_won, "is_lost": s.is_lost} for s in stages]})
    return out


# ---------- pipeline stage management ----------

class StageInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    probability: int = Field(default=0, ge=0, le=100)


class StagePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    probability: int | None = Field(default=None, ge=0, le=100)
    position: int | None = Field(default=None, ge=0)


def stage_view(s: PipelineStage):
    return {"id": s.id, "name": s.name, "position": s.position,
            "probability": s.probability, "is_won": s.is_won, "is_lost": s.is_lost}


def require_settings(ctx):
    if not has_permission(ctx["membership"], COMPANY_SETTINGS):
        raise HTTPException(403, "This action requires the permission: " + COMPANY_SETTINGS)


def get_stage(db, stage_id, ctx):
    s = db.scalar(select(PipelineStage).where(
        PipelineStage.id == stage_id,
        PipelineStage.organization_id == ctx["organization_id"],
        PipelineStage.deleted_at.is_(None)))
    if not s:
        raise HTTPException(404, "Stage not found in this workspace")
    return s


@router.post("/pipelines/{pipeline_id}/stages", status_code=201)
def create_stage(pipeline_id: int, data: StageInput, ctx=Depends(current_membership), db: Session = Depends(get_db)):
    require_settings(ctx)
    pipe = db.scalar(select(Pipeline).where(Pipeline.id == pipeline_id,
                                            Pipeline.organization_id == ctx["organization_id"],
                                            Pipeline.deleted_at.is_(None)))
    if not pipe:
        raise HTTPException(404, "Pipeline not found in this workspace")
    top = db.scalar(select(func.max(PipelineStage.position)).where(
        PipelineStage.pipeline_id == pipe.id, PipelineStage.deleted_at.is_(None)))
    s = PipelineStage(organization_id=ctx["organization_id"], pipeline_id=pipe.id,
                      name=data.name.strip(), position=(top if top is not None else -1) + 1,
                      probability=data.probability)
    db.add(s)
    db.flush()
    log_activity(db, ctx, "pipeline.stage_added", f"Pipeline stage added: {s.name}")
    db.commit()
    return stage_view(s)


@router.patch("/stages/{stage_id}")
def update_stage(stage_id: int, data: StagePatch, ctx=Depends(current_membership), db: Session = Depends(get_db)):
    require_settings(ctx)
    s = get_stage(db, stage_id, ctx)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("name"):
        s.name = changes["name"].strip()
    if changes.get("probability") is not None:
        s.probability = changes["probability"]
    if changes.get("position") is not None:
        s.position = changes["position"]
    log_activity(db, ctx, "pipeline.stage_updated", f"Pipeline stage updated: {s.name}")
    db.commit()
    return stage_view(s)


@router.delete("/stages/{stage_id}")
def delete_stage(stage_id: int, ctx=Depends(current_membership), db: Session = Depends(get_db)):
    require_settings(ctx)
    s = get_stage(db, stage_id, ctx)
    open_deals = db.scalar(select(func.count(Deal.id)).where(Deal.stage_id == s.id, Deal.deleted_at.is_(None)))
    if open_deals:
        raise HTTPException(409, f"Move the {open_deals} deal(s) in this stage to another stage first")
    remaining = db.scalar(select(func.count(PipelineStage.id)).where(
        PipelineStage.pipeline_id == s.pipeline_id, PipelineStage.deleted_at.is_(None)))
    if remaining <= 1:
        raise HTTPException(400, "A pipeline needs at least one stage")
    s.deleted_at = utcnow()
    log_activity(db, ctx, "pipeline.stage_deleted", f"Pipeline stage removed: {s.name}")
    db.commit()
    return {"ok": True}


# ---------- contacts ----------

@router.get("/contacts")
def contacts(q: str | None = None, priority: str | None = None, limit: int = 200,
             ctx=Depends(current_membership), db: Session = Depends(get_db)):
    stmt = select(Contact).where(visible(Contact, ctx), Contact.deleted_at.is_(None))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Contact.name.ilike(like), Contact.phone.ilike(like),
                              Contact.email.ilike(like), Contact.company.ilike(like)))
    if priority:
        stmt = stmt.where(Contact.priority == priority)
    rows = db.scalars(stmt.order_by(Contact.created_at.desc()).limit(min(limit, 500))).all()
    return [contact_view(c) for c in rows]


@router.post("/contacts", status_code=201)
def create_contact(data: ContactInput, ctx=Depends(current_membership), db: Session = Depends(get_db)):
    c = Contact(organization_id=ctx["organization_id"], name=data.name.strip(), phone=data.phone.strip(),
                email=data.email.strip(), company=data.company.strip(), position=data.position.strip(),
                source=data.source.strip() or "manual", priority=data.priority, tags=data.tags,
                notes=data.notes, assigned_to=ctx["user"].id, created_by=ctx["user"].id)
    db.add(c)
    db.flush()
    log_activity(db, ctx, "contact.created", f"Contact created: {c.name}", contact_id=c.id)
    db.commit()
    return contact_view(c)


@router.get("/contacts/export")
def export_contacts(ctx=Depends(current_membership), db: Session = Depends(get_db)):
    """CSV export of the contacts the caller can see. Requires the contacts.export permission."""
    if not has_permission(ctx["membership"], CONTACTS_EXPORT):
        raise HTTPException(403, "This action requires the permission: " + CONTACTS_EXPORT)
    import csv
    import io as _io
    rows = db.scalars(select(Contact).where(visible(Contact, ctx), Contact.deleted_at.is_(None)).order_by(Contact.name, Contact.id)).all()
    buf = _io.StringIO()
    w = csv.writer(buf)
    w.writerow(["name", "phone", "email", "company", "position", "source", "priority", "tags", "assigned_to", "created_at"])
    for c in rows:
        w.writerow([c.name, c.phone, c.email, c.company, c.position, c.source, c.priority,
                    ";".join(c.tags or []), c.assigned_to or "", c.created_at.isoformat() if c.created_at else ""])
    db.add(AuditLog(organization_id=ctx["organization_id"], actor_user_id=ctx["user"].id,
                    action="contact.exported", details={"rows": len(rows)}))
    db.commit()
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=nexus-contacts.csv"})


@router.get("/contacts/{contact_id}")
def contact_profile(contact_id: int, ctx=Depends(current_membership), db: Session = Depends(get_db)):
    c = get_scoped(db, Contact, contact_id, ctx)
    org = ctx["organization_id"]
    deals = db.scalars(select(Deal).where(Deal.contact_id == c.id, Deal.organization_id == org, Deal.deleted_at.is_(None)).order_by(Deal.created_at.desc())).all()
    tasks = db.scalars(select(Task).where(Task.contact_id == c.id, Task.organization_id == org, Task.deleted_at.is_(None)).order_by(Task.status, Task.due_at)).all()
    acts = db.scalars(select(Activity).where(Activity.contact_id == c.id, Activity.organization_id == org).order_by(Activity.created_at.desc()).limit(100)).all()
    return {**contact_view(c), "deals": [deal_view(d) for d in deals],
            "tasks": [task_view(t) for t in tasks],
            "activities": [{"id": a.id, "kind": a.kind, "body": a.body, "user_id": a.user_id,
                            "created_at": a.created_at.isoformat() if a.created_at else None} for a in acts]}


@router.patch("/contacts/{contact_id}")
def update_contact(contact_id: int, data: ContactPatch, ctx=Depends(current_membership), db: Session = Depends(get_db)):
    c = get_scoped(db, Contact, contact_id, ctx)
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is not None or field in ("tags", "notes", "assigned_to"):
            setattr(c, field, value)
    log_activity(db, ctx, "contact.updated", f"Contact updated: {c.name}", contact_id=c.id)
    db.commit()
    return contact_view(c)


@router.delete("/contacts/{contact_id}")
def delete_contact(contact_id: int, ctx=Depends(current_membership), db: Session = Depends(get_db)):
    if not view_all(ctx):
        raise HTTPException(403, "Only a member with company-wide contact access can delete contacts")
    c = get_scoped(db, Contact, contact_id, ctx)
    c.deleted_at = utcnow()
    log_activity(db, ctx, "contact.deleted", f"Contact archived: {c.name}", contact_id=c.id)
    db.add(AuditLog(organization_id=ctx["organization_id"], actor_user_id=ctx["user"].id,
                    action="contact.deleted", details={"contact_id": c.id}))
    db.commit()
    return {"ok": True}


# ---------- deals ----------

@router.get("/deals")
def deals(pipeline_id: int | None = None, status: str | None = None, limit: int = 300,
          ctx=Depends(current_membership), db: Session = Depends(get_db)):
    stmt = select(Deal).where(visible(Deal, ctx), Deal.deleted_at.is_(None))
    if pipeline_id:
        stmt = stmt.where(Deal.pipeline_id == pipeline_id)
    if status:
        stmt = stmt.where(Deal.status == status)
    rows = db.scalars(stmt.order_by(Deal.updated_at.desc()).limit(min(limit, 500))).all()
    return [deal_view(d) for d in rows]


@router.post("/deals", status_code=201)
def create_deal(data: DealInput, ctx=Depends(current_membership), db: Session = Depends(get_db)):
    org = ctx["organization_id"]
    pipe = ensure_default_pipeline(db, org, ctx["user"].id)
    stage = db.scalar(select(PipelineStage).where(PipelineStage.pipeline_id == pipe.id, PipelineStage.deleted_at.is_(None)).order_by(PipelineStage.position))
    if data.contact_id is not None:
        get_scoped(db, Contact, data.contact_id, ctx)
    d = Deal(organization_id=org, title=data.title.strip(), contact_id=data.contact_id,
             pipeline_id=pipe.id, stage_id=stage.id if stage else None, amount=data.amount,
             currency=data.currency, expected_close=parse_date(data.expected_close),
             next_step=data.next_step, probability=stage.probability if stage else 0,
             assigned_to=ctx["user"].id, created_by=ctx["user"].id, last_activity_at=utcnow())
    db.add(d)
    db.flush()
    log_activity(db, ctx, "deal.created", f"Deal created: {d.title}", contact_id=d.contact_id, deal_id=d.id)
    db.commit()
    return deal_view(d)


@router.patch("/deals/{deal_id}")
def update_deal(deal_id: int, data: DealPatch, ctx=Depends(current_membership), db: Session = Depends(get_db)):
    d = get_scoped(db, Deal, deal_id, ctx)
    changes = data.model_dump(exclude_unset=True)
    if "stage_id" in changes and changes["stage_id"] and changes["stage_id"] != d.stage_id:
        stage = db.scalar(select(PipelineStage).where(PipelineStage.id == changes["stage_id"],
                                                      PipelineStage.organization_id == ctx["organization_id"],
                                                      PipelineStage.deleted_at.is_(None)))
        if not stage:
            raise HTTPException(400, "Stage not found in this workspace")
        old = db.get(PipelineStage, d.stage_id) if d.stage_id else None
        d.stage_id = stage.id
        d.pipeline_id = stage.pipeline_id
        d.probability = stage.probability
        if stage.is_won:
            d.status = "won"
        elif stage.is_lost:
            d.status = "lost"
        else:
            d.status = "open"
        log_activity(db, ctx, "deal.stage_changed",
                     f"Deal moved: {d.title} — {old.name if old else 'no stage'} → {stage.name}",
                     contact_id=d.contact_id, deal_id=d.id)
    for field in ("title", "contact_id", "amount", "currency", "next_step", "assigned_to"):
        if field in changes and changes[field] is not None:
            setattr(d, field, changes[field])
    if "expected_close" in changes:
        d.expected_close = parse_date(changes["expected_close"])
    d.last_activity_at = utcnow()
    db.commit()
    return deal_view(d)


@router.delete("/deals/{deal_id}")
def delete_deal(deal_id: int, ctx=Depends(current_membership), db: Session = Depends(get_db)):
    if not has_permission(ctx["membership"], DEALS_DELETE):
        raise HTTPException(403, "This action requires the permission: " + DEALS_DELETE)
    d = get_scoped(db, Deal, deal_id, ctx)
    d.deleted_at = utcnow()
    log_activity(db, ctx, "deal.deleted", f"Deal archived: {d.title}", contact_id=d.contact_id, deal_id=d.id)
    db.add(AuditLog(organization_id=ctx["organization_id"], actor_user_id=ctx["user"].id,
                    action="deal.deleted", details={"deal_id": d.id}))
    db.commit()
    return {"ok": True}


# ---------- lead conversion ----------

@router.post("/leads/{lead_id}/convert", status_code=201)
def convert_lead(lead_id: int, ctx=Depends(current_membership), db: Session = Depends(get_db)):
    org = ctx["organization_id"]
    lead = db.scalar(select(Lead).where(Lead.id == lead_id, Lead.organization_id == org))
    if not lead:
        raise HTTPException(404, "Lead not found in this workspace")
    existing = db.scalar(select(Contact).where(Contact.lead_id == lead.id, Contact.organization_id == org, Contact.deleted_at.is_(None)))
    if existing:
        return {"contact": contact_view(existing), "already_converted": True}
    contact = Contact(organization_id=org, name=lead.name or lead.phone, phone=lead.phone,
                      email=lead.email or "", source=lead.source or "lead",
                      lead_id=lead.id, assigned_to=ctx["user"].id, created_by=ctx["user"].id)
    db.add(contact)
    db.flush()
    lead.status = "converted"
    log_activity(db, ctx, "lead.converted", f"Lead converted to contact: {contact.name}",
                 contact_id=contact.id, lead_id=lead.id)
    db.add(AuditLog(organization_id=org, actor_user_id=ctx["user"].id,
                    action="lead.converted", details={"lead_id": lead.id, "contact_id": contact.id}))
    db.commit()
    return {"contact": contact_view(contact), "already_converted": False}


# ---------- tasks ----------

@router.get("/tasks")
def tasks(status: str | None = None, limit: int = 200,
          ctx=Depends(current_membership), db: Session = Depends(get_db)):
    stmt = select(Task).where(visible(Task, ctx), Task.deleted_at.is_(None))
    if status:
        stmt = stmt.where(Task.status == status)
    rows = db.scalars(stmt.order_by(Task.status, Task.due_at.is_(None), Task.due_at).limit(min(limit, 500))).all()
    return [task_view(t) for t in rows]


@router.post("/tasks", status_code=201)
def create_task(data: TaskInput, ctx=Depends(current_membership), db: Session = Depends(get_db)):
    t = Task(organization_id=ctx["organization_id"], title=data.title.strip(),
             description=data.description, priority=data.priority, due_at=parse_dt(data.due_at),
             contact_id=data.contact_id, deal_id=data.deal_id, lead_id=data.lead_id,
             assigned_to=ctx["user"].id, created_by=ctx["user"].id)
    db.add(t)
    db.flush()
    log_activity(db, ctx, "task.created", f"Task created: {t.title}",
                 contact_id=t.contact_id, deal_id=t.deal_id, lead_id=t.lead_id)
    db.commit()
    return task_view(t)


@router.patch("/tasks/{task_id}")
def update_task(task_id: int, data: TaskPatch, ctx=Depends(current_membership), db: Session = Depends(get_db)):
    t = get_scoped(db, Task, task_id, ctx)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("status") == "done" and t.status != "done":
        t.status = "done"
        t.completed_at = utcnow()
        log_activity(db, ctx, "task.completed", f"Task completed: {t.title}",
                     contact_id=t.contact_id, deal_id=t.deal_id, lead_id=t.lead_id)
    elif "status" in changes and changes["status"] is not None:
        t.status = changes["status"]
        if t.status != "done":
            t.completed_at = None
    for field in ("title", "description", "priority", "assigned_to"):
        if field in changes and changes[field] is not None:
            setattr(t, field, changes[field])
    if "due_at" in changes:
        t.due_at = parse_dt(changes["due_at"])
    db.commit()
    return task_view(t)


@router.delete("/tasks/{task_id}")
def delete_task(task_id: int, ctx=Depends(current_membership), db: Session = Depends(get_db)):
    t = get_scoped(db, Task, task_id, ctx)
    t.deleted_at = utcnow()
    db.commit()
    return {"ok": True}


# ---------- activities ----------

@router.get("/activities")
def activities(contact_id: int | None = None, deal_id: int | None = None,
               lead_id: int | None = None, limit: int = 100,
               ctx=Depends(current_membership), db: Session = Depends(get_db)):
    stmt = select(Activity).where(Activity.organization_id == ctx["organization_id"])
    if not view_all(ctx):
        me = ctx["user"].id
        stmt = stmt.where(or_(Activity.user_id == me,
                              Activity.contact_id.in_(select(Contact.id).where(Contact.organization_id == ctx["organization_id"], Contact.assigned_to == me)),
                              Activity.deal_id.in_(select(Deal.id).where(Deal.organization_id == ctx["organization_id"], Deal.assigned_to == me))))
    if contact_id:
        stmt = stmt.where(Activity.contact_id == contact_id)
    if deal_id:
        stmt = stmt.where(Activity.deal_id == deal_id)
    if lead_id:
        stmt = stmt.where(Activity.lead_id == lead_id)
    rows = db.scalars(stmt.order_by(Activity.created_at.desc()).limit(min(limit, 300))).all()
    return [{"id": a.id, "kind": a.kind, "body": a.body, "user_id": a.user_id,
             "contact_id": a.contact_id, "deal_id": a.deal_id, "lead_id": a.lead_id,
             "created_at": a.created_at.isoformat() if a.created_at else None} for a in rows]


@router.post("/activities", status_code=201)
def create_activity(data: ActivityInput, ctx=Depends(current_membership), db: Session = Depends(get_db)):
    if not (data.contact_id or data.deal_id or data.lead_id):
        raise HTTPException(400, "An activity must link to a contact, deal or lead")
    kind = data.kind.strip() or "note"
    if kind not in ("note", "call", "meeting", "message", "email"):
        raise HTTPException(400, "Kind must be one of: note, call, meeting, message, email")
    log_activity(db, ctx, kind, data.body.strip(),
                 contact_id=data.contact_id, deal_id=data.deal_id, lead_id=data.lead_id)
    db.commit()
    return {"ok": True}
