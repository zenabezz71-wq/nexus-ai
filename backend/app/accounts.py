"""Company signup. No existing ownership is reassigned and no sample data is copied."""
from datetime import datetime, timezone
import hashlib
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ConfigDict, field_validator
from sqlalchemy import select, update, Integer, String
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, Mapped, mapped_column
from .database import Base, get_db
from .models import Organization, User, Membership, AuditLog
from .auth import hash_password, token_for, current_membership
from .config import settings

router=APIRouter()
class AuthRateBucket(Base):
    __tablename__="auth_rate_buckets"
    key:Mapped[str]=mapped_column(String(64),primary_key=True)
    used:Mapped[int]=mapped_column(Integer,default=0)
    expires_at:Mapped[int]=mapped_column(Integer,index=True)

class LoginInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    email:str=Field(min_length=3,max_length=320)
    password:str=Field(min_length=1,max_length=128)

class SignupInput(LoginInput):
    company_name:str=Field(min_length=2,max_length=200)
    full_name:str=Field(min_length=2,max_length=200)
    password:str=Field(min_length=12,max_length=128)
    @field_validator("company_name","full_name")
    @classmethod
    def names(cls,value):
        value=value.strip()
        if len(value)<2 or any(ord(c)<32 for c in value):raise ValueError("Use at least two printable characters")
        return value
    @field_validator("email")
    @classmethod
    def email_valid(cls,value):
        import re
        value=value.strip().lower()
        if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}",value):raise ValueError("Enter a valid email address")
        return value
    @field_validator("password")
    @classmethod
    def password_valid(cls,value):
        if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):raise ValueError("Use at least 12 characters including a letter and a number")
        return value

def limit_auth(db,request,kind,email=""):
    # Never trust caller-supplied X-Forwarded-For. The hosting proxy must supply client IP.
    ip=request.client.host if request.client else "unknown"
    seconds=3600 if kind=="signup" else 900
    maximum=10 if kind=="signup" else 30
    now=int(datetime.now(timezone.utc).timestamp());window=now//seconds
    subjects=[ip]+(["email:"+email] if kind=="login" else [])
    for subject in subjects:
        key=hashlib.sha256(f"{kind}:{window}:{subject}".encode()).hexdigest()
        if not db.get(AuthRateBucket,key):
            try:
                db.add(AuthRateBucket(key=key,used=0,expires_at=(window+1)*seconds));db.commit()
            except IntegrityError:db.rollback()
        changed=db.execute(update(AuthRateBucket).where(AuthRateBucket.key==key,AuthRateBucket.used<maximum).values(used=AuthRateBucket.used+1)).rowcount
        db.commit()
        if not changed:raise HTTPException(429,"Too many attempts. Please try again later.",headers={"Retry-After":str((window+1)*seconds-now)})
    db.query(AuthRateBucket).filter(AuthRateBucket.expires_at<now-86400).delete(synchronize_session=False);db.commit()

def session_payload(db,user,membership):
    from .rbac import permissions_for
    org=db.get(Organization,membership.organization_id)
    return {"access_token":token_for(user.id),"token_type":"bearer","user":{"id":user.id,"email":user.email,"name":user.full_name},"organization":{"id":org.id,"name":org.name,"role":membership.role,"trial_only":org.trial_only},"permissions":permissions_for(membership.role,membership.grants or [])}

@router.post("/auth/signup",status_code=201)
def signup(data:SignupInput,request:Request,db:Session=Depends(get_db)):
    limit_auth(db,request,"signup")
    # Reserve bootstrap identity even if the admin has not yet been initialized.
    if data.email==settings.bootstrap_email.strip().lower() or db.scalar(select(User.id).where(User.email==data.email)):
        raise HTTPException(409,"An account with this email already exists. Sign in instead.")
    org=Organization(name=data.company_name,slug="company-"+uuid.uuid4().hex,trial_only=True)
    user=User(email=data.email,full_name=data.full_name,password_hash=hash_password(data.password))
    try:
        db.add_all([org,user]);db.flush()
        from .rls import org_context
        org_context(db,org.id)
        membership=Membership(user_id=user.id,organization_id=org.id,role="owner")
        db.add(membership)
        db.add(AuditLog(organization_id=org.id,actor_user_id=user.id,action="account.signup",details={"mode":"company_trial"}))
        db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,"An account with this email already exists. Sign in instead.")
    return session_payload(db,user,membership)

@router.get("/dashboard/analytics")
def analytics(ctx=Depends(current_membership),db:Session=Depends(get_db)):
    from collections import Counter
    from datetime import timedelta
    from .models import Lead
    from .crm import LeadSales, SalesFeedback
    from .rbac import has_permission, REPORTS_COMPANY
    if not has_permission(ctx["membership"],REPORTS_COMPANY):raise HTTPException(403,"This action requires the permission: "+REPORTS_COMPANY)
    org=ctx["organization_id"];today=datetime.now(timezone.utc).date();start=today-timedelta(days=6)
    leads=db.scalars(select(Lead).where(Lead.organization_id==org,Lead.source!="assistant_demo")).all()
    counts=Counter(x.status for x in leads)
    recent=[x for x in leads if x.created_at.date()>=start]
    timeline=[]
    for n in range(7):
        day=start+timedelta(days=n)
        subset=[x for x in recent if x.created_at.date()==day]
        timeline.append({"date":str(day),"new_leads":len(subset),"current_statuses":dict(Counter(x.status for x in subset))})
    members=db.execute(select(User,Membership).join(Membership,User.id==Membership.user_id).where(Membership.organization_id==org,Membership.is_active==True,User.is_active==True)).all()
    assignments=dict(db.execute(select(LeadSales.lead_id,LeadSales.assigned_user_id).join(Lead,Lead.id==LeadSales.lead_id).where(Lead.organization_id==org)).all())
    feedback=[x for x in db.scalars(select(SalesFeedback).where(SalesFeedback.organization_id==org)).all() if not x.body.startswith(("🤖","🔥","👤","🚫"))]
    people=[]
    for user,member in members:
        assigned=[x for x in leads if assignments.get(x.id)==user.id]
        people.append({"name":user.full_name or user.email,"assigned":len(assigned),"won":sum(x.status=="won" for x in assigned),"lost":sum(x.status=="lost" for x in assigned),"feedback_week":sum(x.author_user_id==user.id and x.created_at.date()>=start for x in feedback)})
    won=counts.get("won",0);closed=won+counts.get("lost",0);unassigned=sum(not assignments.get(x.id) for x in leads)
    summary=f"Last 7 days: {len(recent)} new leads and {sum(x.created_at.date()>=start for x in feedback)} sales notes. Your current pipeline has {counts.get('hot_lead',0)} hot leads, {counts.get('follow_up',0)} follow-ups and {won} won leads. {unassigned} leads are unassigned. "
    summary+=("Assign an owner to unassigned leads and review pending follow-ups." if unassigned or counts.get("follow_up",0) else "Import your first leads to start tracking results." if not leads else "Keep lead statuses and sales notes up to date.")
    return {"period_start":str(start),"period_end":str(today),"total":len(leads),"new_week":len(recent),"hot":counts.get("hot_lead",0),"won":won,"closed_win_rate":round(won/closed*100,1) if closed else None,"statuses":dict(counts),"timeline":timeline,"salespeople":people,"unassigned":unassigned,"weekly_summary":summary,"summary_method":"Local rules from workspace data, no external AI calls", "timeline_note":"New leads grouped by creation day and their CURRENT status. Historical stage transitions are not reconstructed; status groups are not a sequential conversion funnel."}
