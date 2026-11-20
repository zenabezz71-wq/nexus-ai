import io,re
from contextlib import asynccontextmanager
from fastapi import FastAPI,Depends,HTTPException,UploadFile,File
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import select,func
import pandas as pd
from .config import settings
from .database import get_db,engine,Base,SessionLocal
from .models import Organization,User,Membership,Lead,AuditLog
from .auth import hash_password,verify_password,token_for,current_membership
from .normalization import normalize_headers,normalize_phone,parse_bool
from .agents import classify
from .outreach import router as outreach_router
from .whatsapp import router as whatsapp_router
from .crm import router as crm_router
from .assistant import router as assistant_router, DEMO_SOURCE
from .accounts import router as accounts_router, session_payload, limit_auth, LoginInput
from .team import router as team_router
from .crm_core import router as crm_core_router
from .platform_admin import router as platform_router
from . import rls as _rls  # registers the tenant-context session listener
from . import tenant as _tenant_models  # registers Phase 1 tables on Base.metadata
from fastapi import Request
from .agents import baseline

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(bind=engine)
    db=SessionLocal()
    try:
        email=settings.bootstrap_email.lower()
        user=db.scalar(select(User).where(User.email==email))
        if not user:
            org=Organization(name="NEXUS Demo Workspace",slug="nexus-demo")
            user=User(email=email,password_hash=hash_password(settings.bootstrap_password),full_name="Workspace Admin")
            db.add_all([org,user]);db.flush()
            db.add(Membership(user_id=user.id,organization_id=org.id,role="owner"));db.commit()
    finally:db.close()
    yield
app=FastAPI(title="NEXUS AI API",version="1.0.0",lifespan=lifespan)
app.include_router(outreach_router)
app.include_router(whatsapp_router)
app.include_router(crm_router)
app.include_router(accounts_router)
app.include_router(assistant_router)
app.include_router(team_router)
app.include_router(crm_core_router)
app.include_router(platform_router)
app.add_middleware(CORSMiddleware,allow_origins=settings.cors_list,allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
@app.get("/health")
def health():return {"ok":True,"service":"nexus-ai-api","version":"1.0.0"}
@app.post("/auth/login")
def login(data:LoginInput,request:Request,db:Session=Depends(get_db)):
    email=data.email.strip().lower();password=data.password
    limit_auth(db, request, "login", email)
    user=db.scalar(select(User).where(func.lower(User.email)==email))
    if not user or not user.is_active or not verify_password(password,user.password_hash):raise HTTPException(401,"Incorrect email or password")
    membership=db.scalar(select(Membership).where(Membership.user_id==user.id,Membership.is_active==True).order_by(Membership.id))
    if not membership:raise HTTPException(403,"No active organization")
    org=db.get(Organization,membership.organization_id)
    if not org or org.deleted_at is not None or not org.is_active:raise HTTPException(403,"This workspace has been suspended")
    return session_payload(db,user,membership)
@app.get("/auth/me")
def me(ctx=Depends(current_membership),db:Session=Depends(get_db)):
    from .rbac import permissions_for
    org=db.get(Organization,ctx["organization_id"])
    m=ctx["membership"]
    return {"id":ctx["user"].id,"email":ctx["user"].email,"name":ctx["user"].full_name,"organization_id":org.id,"organization_name":org.name,"trial_only":org.trial_only,"role":m.role,"grants":m.grants or [],"permissions":permissions_for(m.role,m.grants or []),"is_platform_admin":bool(getattr(ctx["user"],"is_platform_admin",False))}
@app.get("/dashboard/summary")
def summary(ctx=Depends(current_membership),db:Session=Depends(get_db)):
    org=ctx["organization_id"]; total=db.scalar(select(func.count(Lead.id)).where(Lead.organization_id==org,Lead.source!=DEMO_SOURCE)) or 0
    rows=db.execute(select(Lead.status,func.count(Lead.id)).where(Lead.organization_id==org,Lead.source!=DEMO_SOURCE).group_by(Lead.status)).all()
    eligible=db.scalar(select(func.count(Lead.id)).where(Lead.organization_id==org,Lead.consent==True,Lead.opted_out==False,Lead.source!=DEMO_SOURCE)) or 0
    return {"total_leads":total,"eligible_contacts":eligible,"statuses":dict(rows)}
@app.get("/leads")
def leads(status:str|None=None,q:str|None=None,limit:int=100,ctx=Depends(current_membership),db:Session=Depends(get_db)):
    stmt=select(Lead).where(Lead.organization_id==ctx["organization_id"],Lead.source!=DEMO_SOURCE).order_by(Lead.created_at.desc())
    if status:stmt=stmt.where(Lead.status==status)
    if q:
        term=f"%{q}%";stmt=stmt.where((Lead.name.ilike(term))|(Lead.phone.ilike(term))|(Lead.email.ilike(term)))
    return [{"id":x.id,"name":x.name,"phone":x.phone,"email":x.email,"source":x.source,"status":x.status,"consent":x.consent,"opted_out":x.opted_out,"currency":x.currency,"amount":x.amount,"goal":x.goal} for x in db.scalars(stmt.limit(min(max(limit,1),500))).all()]
@app.post("/leads/import")
async def import_leads(file:UploadFile=File(...),ctx=Depends(current_membership),db:Session=Depends(get_db)):
    name=(file.filename or "").lower();raw=await file.read(5*1024*1024+1)
    if len(raw)>5*1024*1024:raise HTTPException(413,"Maximum upload size is 5 MB")
    try:
        if name.endswith(".csv"):
            try:frame=pd.read_csv(io.BytesIO(raw),encoding="utf-8-sig")
            except UnicodeDecodeError:frame=pd.read_csv(io.BytesIO(raw),encoding="cp1256")
        elif name.endswith(".xlsx"):frame=pd.read_excel(io.BytesIO(raw))
        else:raise HTTPException(400,"Upload .csv or .xlsx")
    except HTTPException:raise
    except Exception as e:raise HTTPException(400,f"Cannot parse spreadsheet: {e}")
    if len(frame)>5000:raise HTTPException(413,"Import at most 5,000 rows at once")
    frame=frame.fillna("").rename(columns=normalize_headers(frame.columns))
    if "phone" not in frame.columns:raise HTTPException(400,"Required column: phone")
    org=ctx["organization_id"];known=set(db.scalars(select(Lead.phone).where(Lead.organization_id==org)).all())
    imported=duplicates=invalid=0
    for _,r in frame.iterrows():
        phone,valid=normalize_phone(r.get("phone",""))
        if not phone:invalid+=1;continue
        if phone in known:duplicates+=1;continue
        amount=None
        try:
            v=re.sub(r"[^0-9.\\-]","",str(r.get("amount","")));amount=float(v) if v else None
        except Exception:pass
        db.add(Lead(organization_id=org,name=str(r.get("name","") or "")[:200],phone=phone,email=str(r.get("email","") or "")[:320],
          currency=str(r.get("currency","") or "").upper()[:12],amount=amount,goal=str(r.get("goal","") or ""),source_message=str(r.get("message","") or ""),
          consent=parse_bool(r.get("consent",False)),source="file_import",status="unclassified" if valid else "invalid_number",
          confidence=0 if valid else .99,classification_reason="" if valid else "Phone failed validation"))
        known.add(phone);imported+=1
        if not valid:invalid+=1
    db.add(AuditLog(organization_id=org,actor_user_id=ctx["user"].id,action="leads.import",details={"file":file.filename,"imported":imported,"duplicates":duplicates,"invalid":invalid}))
    db.commit()
    return {"imported":imported,"duplicates":duplicates,"invalid_or_missing_phone":invalid,"rows":len(frame)}
@app.post("/agents/classify/{lead_id}")
async def classify_lead(lead_id:int,ctx=Depends(current_membership),db:Session=Depends(get_db)):
    lead=db.scalar(select(Lead).where(Lead.id==lead_id,Lead.organization_id==ctx["organization_id"]))
    if not lead:raise HTTPException(404,"Lead not found")
    text=" ".join([lead.goal or "",lead.source_message or ""])
    org=db.get(Organization,ctx["organization_id"])
    label,confidence,reason=baseline(text) if org.trial_only else await classify(text)
    lead.status,lead.confidence,lead.classification_reason=label,confidence,reason
    db.add(AuditLog(organization_id=ctx["organization_id"],actor_user_id=ctx["user"].id,action="agent.classify",details={"lead_id":lead.id,"status":label,"confidence":confidence}))
    db.commit()
    return {"lead_id":lead.id,"status":label,"confidence":confidence,"reason":reason}
@app.post("/webhooks/{source}")
async def universal_webhook(source:str,payload:dict,ctx=Depends(current_membership),db:Session=Depends(get_db)):
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,60}",source):raise HTTPException(400,"Invalid source identifier")
    phone,valid=normalize_phone(payload.get("phone",""))
    if not phone:raise HTTPException(400,"Phone is required")
    org=ctx["organization_id"];lead=db.scalar(select(Lead).where(Lead.organization_id==org,Lead.phone==phone))
    if lead:
        for key,attr in [("name","name"),("email","email"),("goal","goal"),("message","source_message"),("external_id","external_id")]:
            val=payload.get(key)
            if val:setattr(lead,attr,str(val))
        if payload.get("consent") is True:lead.consent=True
        lead.source=source;result="updated"
    else:
        lead=Lead(organization_id=org,external_id=payload.get("external_id"),source=source,name=str(payload.get("name",""))[:200],
          phone=phone,email=str(payload.get("email",""))[:320],currency=str(payload.get("currency","")).upper()[:12],
          amount=payload.get("amount"),goal=str(payload.get("goal","")),source_message=str(payload.get("message","")),
          consent=payload.get("consent") is True,status="unclassified" if valid else "invalid_number",confidence=0 if valid else .99)
        db.add(lead);result="created"
    db.flush();db.add(AuditLog(organization_id=org,actor_user_id=ctx["user"].id,action="webhook.lead",details={"source":source,"result":result,"lead_id":lead.id}))
    db.commit();return {"ok":True,"result":result,"lead_id":lead.id,"consent":lead.consent}
