"""Audit log read API: every sensitive action, visible to owner/admin.

Blueprint Phase 6 (Audit Logs) and acceptance criterion "كل العمليات الحساسة
تسجل في Audit Log". Read-only; entries are written by the features themselves.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import get_db
from .models import AuditLog, User
from .auth import current_membership
from .rbac import has_permission, COMPANY_SETTINGS

router = APIRouter()


@router.get("/audit-log")
def audit_log(action: str | None = None, limit: int = 100,
              ctx=Depends(current_membership), db: Session = Depends(get_db)):
    if not has_permission(ctx["membership"], COMPANY_SETTINGS):
        raise HTTPException(403, "This action requires the permission: " + COMPANY_SETTINGS)
    stmt = (select(AuditLog, User.full_name, User.email)
            .outerjoin(User, User.id == AuditLog.actor_user_id)
            .where(AuditLog.organization_id == ctx["organization_id"])
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(min(limit, 300)))
    if action:
        stmt = stmt.where(AuditLog.action == action)
    rows = db.execute(stmt).all()
    actions = [a.action for a, _, _ in rows]
    return {
        "entries": [{
            "id": a.id, "action": a.action,
            "actor": name or email or ("system" if a.actor_user_id is None else f"user #{a.actor_user_id}"),
            "details": a.details or {},
            "created_at": a.created_at.isoformat() if a.created_at else None,
        } for a, name, email in rows],
        "method": "Every entry was written by the feature that performed the action; this log is read-only.",
    }
