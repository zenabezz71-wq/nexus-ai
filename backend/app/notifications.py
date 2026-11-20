"""In-app notifications: assignment events and a lazy daily overdue-task reminder."""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .database import get_db
from .tenant import Notification, Task
from .auth import current_membership

router = APIRouter()


def aware(value):
    if value is None:
        return None
    return value.replace(tzinfo=value.tzinfo or timezone.utc)


def notify(db, organization_id, user_id, kind, body):
    db.add(Notification(organization_id=organization_id, user_id=user_id, kind=kind, body=body))


def view(n):
    return {"id": n.id, "kind": n.kind, "body": n.body,
            "read": n.read_at is not None,
            "created_at": aware(n.created_at).isoformat() if n.created_at else None}


def lazy_reminders(db, org, user_id):
    """Create at most one overdue-task reminder per user per UTC day, when they fetch."""
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    existing = db.scalars(select(Notification).where(
        Notification.organization_id == org, Notification.user_id == user_id,
        Notification.kind == "tasks.overdue_reminder")).all()
    if any(aware(n.created_at) >= day_start for n in existing):
        return
    overdue = [t for t in db.scalars(select(Task).where(
        Task.organization_id == org, Task.assigned_to == user_id,
        Task.status == "open", Task.deleted_at.is_(None), Task.due_at.isnot(None))).all()
        if aware(t.due_at) < now]
    if overdue:
        notify(db, org, user_id, "tasks.overdue_reminder",
               f"You have {len(overdue)} overdue task(s). Oldest due {aware(min(aware(t.due_at) for t in overdue)).date()}.")
        db.commit()


@router.get("/notifications")
def list_notifications(ctx=Depends(current_membership), db: Session = Depends(get_db)):
    org, uid = ctx["organization_id"], ctx["user"].id
    lazy_reminders(db, org, uid)
    rows = db.scalars(select(Notification).where(
        Notification.organization_id == org, Notification.user_id == uid)
        .order_by(Notification.created_at.desc(), Notification.id.desc()).limit(100)).all()
    unread = sum(1 for n in rows if n.read_at is None)
    return {"notifications": [view(n) for n in rows], "unread": unread}


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: int, ctx=Depends(current_membership), db: Session = Depends(get_db)):
    n = db.scalar(select(Notification).where(
        Notification.id == notification_id,
        Notification.organization_id == ctx["organization_id"],
        Notification.user_id == ctx["user"].id))
    if not n:
        raise HTTPException(404, "Notification not found")
    if n.read_at is None:
        n.read_at = datetime.now(timezone.utc)
        db.commit()
    return view(n)


@router.post("/notifications/read-all")
def mark_all_read(ctx=Depends(current_membership), db: Session = Depends(get_db)):
    rows = db.scalars(select(Notification).where(
        Notification.organization_id == ctx["organization_id"],
        Notification.user_id == ctx["user"].id, Notification.read_at.is_(None))).all()
    now = datetime.now(timezone.utc)
    for n in rows:
        n.read_at = now
    db.commit()
    return {"ok": True, "marked": len(rows)}
