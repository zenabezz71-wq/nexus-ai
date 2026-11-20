from datetime import datetime,timedelta,timezone
from jose import jwt,JWTError
from passlib.context import CryptContext
from fastapi import Depends,HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import settings
from .database import get_db
from .models import User,Membership,Organization
pwd=CryptContext(schemes=["argon2"],deprecated="auto")
oauth=OAuth2PasswordBearer(tokenUrl="/auth/login")
def hash_password(p): return pwd.hash(p)
def verify_password(p,h): return pwd.verify(p,h)
def token_for(uid):
    exp=datetime.now(timezone.utc)+timedelta(minutes=settings.jwt_access_minutes)
    return jwt.encode({"sub":str(uid),"exp":exp},settings.jwt_secret,algorithm="HS256")
def current_membership(token:str=Depends(oauth),db:Session=Depends(get_db)):
    err=HTTPException(401,"Invalid or expired token",headers={"WWW-Authenticate":"Bearer"})
    try: uid=int(jwt.decode(token,settings.jwt_secret,algorithms=["HS256"]).get("sub","0"))
    except (JWTError,ValueError): raise err
    user=db.get(User,uid)
    if not user or not user.is_active: raise err
    membership=db.scalar(select(Membership).where(Membership.user_id==uid,Membership.is_active==True).order_by(Membership.id))
    if not membership: raise HTTPException(403,"No active organization membership")
    org=db.get(Organization,membership.organization_id)
    if not org or org.deleted_at is not None or not org.is_active: raise HTTPException(403,"This workspace has been suspended")
    from .rls import org_context
    org_context(db,membership.organization_id)
    return {"user":user,"membership":membership,"organization_id":membership.organization_id}
