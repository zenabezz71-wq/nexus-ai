"""Workspace team management: list members, change roles, set extra grants."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .database import get_db
from .models import User, Membership, AuditLog
from .rbac import (
    require, permissions_for, ROLES, GRANTABLE, OWNER_ONLY_GRANTS,
    TEAM_VIEW, TEAM_MANAGE, ROLE_OWNER,
)

router = APIRouter()


class RoleInput(BaseModel):
    role: str = Field(min_length=3, max_length=20)


class GrantsInput(BaseModel):
    grants: list[str] = Field(default_factory=list, max_length=20)


def member_view(m: Membership, u: User):
    return {
        "membership_id": m.id,
        "user_id": u.id,
        "name": u.full_name,
        "email": u.email,
        "role": m.role,
        "grants": m.grants or [],
        "permissions": permissions_for(m.role, m.grants or []),
    }


def own_membership(db, membership_id, org):
    m = db.scalar(select(Membership).where(
        Membership.id == membership_id,
        Membership.organization_id == org,
        Membership.is_active == True,
    ))
    if not m:
        raise HTTPException(404, "Membership not found in workspace")
    return m


def owner_count(db, org):
    return db.scalar(select(func.count(Membership.id)).where(
        Membership.organization_id == org,
        Membership.role == ROLE_OWNER,
        Membership.is_active == True,
    )) or 0


@router.get("/team/members")
def members(ctx=Depends(require(TEAM_VIEW)), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == ctx["organization_id"], Membership.is_active == True, User.is_active == True)
        .order_by(Membership.id)
    ).all()
    return [member_view(m, u) for m, u in rows]


@router.patch("/team/members/{membership_id}")
def change_role(membership_id: int, data: RoleInput, ctx=Depends(require(TEAM_MANAGE)), db: Session = Depends(get_db)):
    role = data.role.strip().lower()
    if role not in ROLES:
        raise HTTPException(400, "Role must be one of: " + ", ".join(ROLES))
    actor = ctx["membership"]
    target = own_membership(db, membership_id, ctx["organization_id"])
    if target.role == ROLE_OWNER and actor.role != ROLE_OWNER:
        raise HTTPException(403, "Only an owner can change an owner's role")
    if target.id == actor.id and actor.role == ROLE_OWNER and role != ROLE_OWNER:
        raise HTTPException(400, "Transfer ownership to another member before changing your own role")
    if target.role == ROLE_OWNER and role != ROLE_OWNER and owner_count(db, ctx["organization_id"]) <= 1:
        raise HTTPException(400, "A workspace must keep at least one owner")
    old = target.role
    target.role = role
    db.add(AuditLog(organization_id=ctx["organization_id"], actor_user_id=ctx["user"].id,
                    action="team.role_changed", details={"membership_id": target.id, "from": old, "to": role}))
    db.commit()
    return member_view(target, db.get(User, target.user_id))


@router.put("/team/members/{membership_id}/grants")
def set_grants(membership_id: int, data: GrantsInput, ctx=Depends(require(TEAM_MANAGE)), db: Session = Depends(get_db)):
    grants = sorted({g.strip() for g in data.grants if g.strip()})
    unknown = [g for g in grants if g not in GRANTABLE]
    if unknown:
        raise HTTPException(400, "Unknown or non-grantable permissions: " + ", ".join(unknown))
    if any(g in OWNER_ONLY_GRANTS for g in grants) and ctx["membership"].role != ROLE_OWNER:
        raise HTTPException(403, "Only an owner can grant: " + ", ".join(sorted(OWNER_ONLY_GRANTS)))
    target = own_membership(db, membership_id, ctx["organization_id"])
    target.grants = grants
    db.add(AuditLog(organization_id=ctx["organization_id"], actor_user_id=ctx["user"].id,
                    action="team.grants_updated", details={"membership_id": target.id, "grants": grants}))
    db.commit()
    return member_view(target, db.get(User, target.user_id))
