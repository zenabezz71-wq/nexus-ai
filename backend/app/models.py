from datetime import datetime,timezone
from sqlalchemy import String,Integer,Float,Boolean,DateTime,Text,ForeignKey,JSON,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from .database import Base
def now(): return datetime.now(timezone.utc)
class Organization(Base):
    __tablename__="organizations"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    name:Mapped[str]=mapped_column(String(200))
    slug:Mapped[str]=mapped_column(String(100),unique=True,index=True)
    trial_only:Mapped[bool]=mapped_column(Boolean,default=False,server_default="false")
    is_active:Mapped[bool]=mapped_column(Boolean,default=True,server_default="true")
    deleted_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class User(Base):
    __tablename__="users"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    email:Mapped[str]=mapped_column(String(320),unique=True,index=True)
    password_hash:Mapped[str]=mapped_column(String(500))
    full_name:Mapped[str]=mapped_column(String(200),default="")
    is_active:Mapped[bool]=mapped_column(Boolean,default=True)
    is_platform_admin:Mapped[bool]=mapped_column(Boolean,default=False,server_default="false")
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Membership(Base):
    __tablename__="memberships"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"))
    organization_id:Mapped[int]=mapped_column(ForeignKey("organizations.id",ondelete="CASCADE"),index=True)
    role:Mapped[str]=mapped_column(String(30),default="member")
    grants:Mapped[list]=mapped_column(JSON,default=list,server_default="[]")
    is_active:Mapped[bool]=mapped_column(Boolean,default=True)
    __table_args__=(UniqueConstraint("user_id","organization_id"),)
class Lead(Base):
    __tablename__="leads"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    organization_id:Mapped[int]=mapped_column(ForeignKey("organizations.id",ondelete="CASCADE"),index=True)
    external_id:Mapped[str|None]=mapped_column(String(200),nullable=True)
    source:Mapped[str]=mapped_column(String(100),default="manual")
    name:Mapped[str]=mapped_column(String(200),default="")
    phone:Mapped[str]=mapped_column(String(40))
    email:Mapped[str]=mapped_column(String(320),default="")
    currency:Mapped[str]=mapped_column(String(12),default="")
    amount:Mapped[float|None]=mapped_column(Float,nullable=True)
    goal:Mapped[str]=mapped_column(Text,default="")
    source_message:Mapped[str]=mapped_column(Text,default="")
    consent:Mapped[bool]=mapped_column(Boolean,default=False)
    opted_out:Mapped[bool]=mapped_column(Boolean,default=False)
    status:Mapped[str]=mapped_column(String(40),default="unclassified",index=True)
    confidence:Mapped[float]=mapped_column(Float,default=0)
    classification_reason:Mapped[str]=mapped_column(Text,default="")
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,onupdate=now)
    __table_args__=(UniqueConstraint("organization_id","phone",name="uq_lead_org_phone"),)
class AuditLog(Base):
    __tablename__="audit_logs"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    organization_id:Mapped[int]=mapped_column(ForeignKey("organizations.id",ondelete="CASCADE"),index=True)
    actor_user_id:Mapped[int|None]=mapped_column(ForeignKey("users.id"),nullable=True)
    action:Mapped[str]=mapped_column(String(100))
    details:Mapped[dict]=mapped_column(JSON,default=dict)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
