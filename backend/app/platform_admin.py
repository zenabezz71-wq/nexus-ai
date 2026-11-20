"""Platform-owner super-admin: manage tenant workspaces across the whole platform.

Platform operators are flagged on the USER (users.is_platform_admin), not on any
membership, so the power is not tied to a single tenant org. Every operator
action runs in the verified system context (the same RLS bypass used by signed
webhooks) so tenant RLS can never silently hide or block a cross-org operation,
and every action writes an AuditLog row on the target org with the operator,
the action and the reason.

Suspension blocks every member of the workspace at login and on every request
(current_membership rejects suspended/deleted orgs). Deletion is a SOFT delete
(deleted_at + is_active=false): it is reversible, keeps the audit trail intact
and avoids destructive cross-tenant cascades under FORCE RLS.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .database import get_db
from .auth import current_membership
from .models import Organization, User, Membership, Lead, AuditLog
from .rls import system_context

router = APIRouter()


def require_platform_admin(ctx=Depends(current_membership), db: Session = Depends(get_db)):
    if not getattr(ctx["user"], "is_platform_admin", False):
        raise HTTPException(403, "Platform operator access required")
    system_context(db)
    return ctx


class ReasonInput(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


def org_view(db, o: Organization):
    members = db.scalar(select(func.count(Membership.id)).where(Membership.organization_id == o.id, Membership.is_active == True)) or 0
    leads = db.scalar(select(func.count(Lead.id)).where(Lead.organization_id == o.id)) or 0
    return {"id": o.id, "name": o.name, "slug": o.slug, "trial_only": o.trial_only,
            "is_active": o.is_active, "deleted_at": o.deleted_at.isoformat() if o.deleted_at else None,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "member_count": members, "lead_count": leads}


@router.get("/platform/organizations")
def list_organizations(ctx=Depends(require_platform_admin), db: Session = Depends(get_db)):
    orgs = db.scalars(select(Organization).order_by(Organization.id)).all()
    return [org_view(db, o) for o in orgs]


@router.post("/platform/organizations/{org_id}/suspend")
def suspend_organization(org_id: int, data: ReasonInput, ctx=Depends(require_platform_admin), db: Session = Depends(get_db)):
    org = db.get(Organization, org_id)
    if not org or org.deleted_at is not None:
        raise HTTPException(404, "Organization not found")
    if org.id == ctx["organization_id"]:
        raise HTTPException(400, "You cannot suspend the workspace you are acting from")
    org.is_active = False
    db.add(AuditLog(organization_id=org.id, actor_user_id=ctx["user"].id,
                    action="platform.org_suspended", details={"reason": data.reason, "operator": ctx["user"].email}))
    db.commit()
    return org_view(db, org)


@router.post("/platform/organizations/{org_id}/restore")
def restore_organization(org_id: int, data: ReasonInput, ctx=Depends(require_platform_admin), db: Session = Depends(get_db)):
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Organization not found")
    org.is_active = True
    org.deleted_at = None
    db.add(AuditLog(organization_id=org.id, actor_user_id=ctx["user"].id,
                    action="platform.org_restored", details={"reason": data.reason, "operator": ctx["user"].email}))
    db.commit()
    return org_view(db, org)


@router.delete("/platform/organizations/{org_id}")
def delete_organization(org_id: int, reason: str = "", ctx=Depends(require_platform_admin), db: Session = Depends(get_db)):
    if len(reason.strip()) < 3:
        raise HTTPException(400, "A reason (3+ characters) is required to delete a workspace")
    org = db.get(Organization, org_id)
    if not org or org.deleted_at is not None:
        raise HTTPException(404, "Organization not found")
    if org.id == ctx["organization_id"]:
        raise HTTPException(400, "You cannot delete the workspace you are acting from")
    org.is_active = False
    org.deleted_at = datetime.now(timezone.utc)
    db.add(AuditLog(organization_id=org.id, actor_user_id=ctx["user"].id,
                    action="platform.org_deleted",
                    details={"reason": reason.strip(), "operator": ctx["user"].email, "mode": "soft-delete (retained, restorable)"}))
    db.commit()
    return {"ok": True, "mode": "soft-delete", "organization_id": org.id}
