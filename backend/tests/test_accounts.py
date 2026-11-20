from app.database import SessionLocal
from app.models import Organization, User, Membership, Lead
from app.accounts import AuthRateBucket
from app.auth import hash_password
from app.config import settings
from sqlalchemy import select

DATA={"email":"company@example.org","password":"CompanyPassword123!","company_name":"New Company","full_name":"Company Owner"}
def register(client,**values):return client.post('/auth/signup',json=DATA|values)
def header(response):return {"Authorization":"Bearer "+response.json()["access_token"]}
def test_signup_empty_private_owner_and_login(client):
    r=register(client,email="  COMPANY@example.org  ");assert r.status_code==201
    h=header(r);me=client.get('/auth/me',headers=h).json()
    assert me['organization_name']=='New Company' and me['role']=='owner' and me['trial_only'] is True
    assert client.get('/leads',headers=h).json()==[]
    assert client.get('/dashboard/analytics',headers=h).json()['total']==0
    assert client.post('/auth/login',json={"email":" COMPANY@example.org ","password":DATA['password']}).status_code==200

def test_duplicate_email_atomic(client):
    assert register(client).status_code==201
    assert register(client,email="COMPANY@example.org").status_code==409
    with SessionLocal() as db:
        assert len(db.scalars(select(Organization).where(Organization.trial_only==True)).all())==1

def test_bootstrap_reserved_and_preserved(client,token):
    assert register(client,email=settings.bootstrap_email).status_code==409
    assert client.get('/auth/me',headers={"Authorization":"Bearer "+token}).json()['trial_only'] is False

def test_validation_and_scope_injection(client):
    for patch in [{"password":"short"},{"password":"abcdefghijklmnop"},{"company_name":"  "},{"email":"not-email"},{"organization_id":1},{"role":"admin"}]:
        assert register(client,**patch).status_code==422
    assert register(client).status_code==201

def test_full_company_isolation(client):
    a=header(register(client));b=header(register(client,email="second@example.org",company_name="Second Company"))
    payload={"phone":"+201001112233","name":"Company A lead","email":"a@example.org","consent":True}
    ident=client.post('/webhooks/manual',headers=a,json=payload).json()['lead_id']
    other=client.post('/webhooks/manual',headers=b,json=payload|{"name":"Company B lead"}).json()['lead_id']
    assert ident!=other
    assert len(client.get('/leads',headers=b).json())==1
    assert client.get(f'/leads/{ident}',headers=b).status_code==404
    assert client.patch(f'/leads/{ident}',headers=b,json={"expected_updated_at":"2026-01-01T00:00:00Z","name":"hijack"}).status_code==404
    assert client.post(f'/leads/{ident}/feedback',headers=b,json={"body":"hijack"}).status_code==404
    assert client.post(f'/agents/classify/{ident}',headers=b).status_code==404
    for path in ['/outreach/preview','/whatsapp/preview']:
        assert client.post(path,headers=b,json={"lead_ids":[ident]}).status_code==404
    note=client.post(f'/leads/{ident}/feedback',headers=a,json={"body":"A private sales note"})
    assert note.status_code==200
    assert client.get('/dashboard/analytics',headers=a).json()['salespeople'][0]['feedback_week']==1
    assert client.get('/dashboard/analytics',headers=b).json()['salespeople'][0]['feedback_week']==0
    assert client.get('/workspace/salespeople',headers=a).json()!=client.get('/workspace/salespeople',headers=b).json()

def test_trial_sending_remains_off_even_if_globally_enabled(client,monkeypatch):
    h=header(register(client))
    monkeypatch.setattr('app.outreach.readiness',lambda:[])
    monkeypatch.setattr('app.whatsapp.readiness',lambda:[])
    monkeypatch.setattr('app.whatsapp.template',lambda:(_ for _ in ()).throw(AssertionError('No Meta access in trial')))
    for path in ['/outreach','/whatsapp']:
        status=client.get(path+'/status',headers=h).json();assert status['ready'] is False and status['blockers']
        assert client.post(path+'/send',headers=h,json={"review_token":"anything"}).status_code==409
    ident=client.post('/webhooks/manual',headers=h,json={"phone":"+201001112233","consent":True,"email":"lead@example.org"}).json()['lead_id']
    for path in ['/outreach','/whatsapp']:
        preview=client.post(path+'/preview',headers=h,json={"lead_ids":[ident]}).json()
        assert preview['blockers'] and preview['messages'][0]['demo_only']

def test_trial_classification_never_calls_paid_ai(client,monkeypatch):
    h=header(register(client))
    async def forbidden(*args):raise AssertionError('No paid AI in trial')
    monkeypatch.setattr('app.main.classify',forbidden)
    ident=client.post('/webhooks/manual',headers=h,json={"phone":"+201001112233","goal":"interested in price"}).json()['lead_id']
    assert client.post(f'/agents/classify/{ident}',headers=h).json()['status']=='hot_lead'

def test_analytics_role_and_auth(client):
    assert client.get('/dashboard/analytics').status_code==401
    r=register(client);h=header(r)
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email==DATA['email']));m=db.scalar(select(Membership).where(Membership.user_id==user.id));m.role='member';db.commit()
    assert client.get('/dashboard/analytics',headers=h).status_code==403

def test_login_throttling_persisted(client):
    for _ in range(30):assert client.post('/auth/login',json={"email":"absent@example.org","password":"wrong"}).status_code==401
    r=client.post('/auth/login',json={"email":"absent@example.org","password":"wrong"});assert r.status_code==429 and r.headers['retry-after']
    with SessionLocal() as db:assert len(db.scalars(select(AuthRateBucket)).all())==2

def test_signup_throttling(client):
    for _ in range(10):assert register(client,email=settings.bootstrap_email).status_code==409
    assert register(client).status_code==429

def test_trial_optout_does_not_affect_other_company(client):
    a=header(register(client));b=header(register(client,email="second@example.org"))
    ids=[]
    for h in [a,b]:ids.append(client.post('/webhooks/manual',headers=h,json={"phone":"+201001112233","consent":True,"email":"lead@example.org"}).json()['lead_id'])
    detail=client.get(f'/leads/{ids[0]}',headers=a).json()
    assert client.patch(f'/leads/{ids[0]}',headers=a,json={"expected_updated_at":detail['updated_at'],"do_not_contact":True}).status_code==200
    r=client.post('/whatsapp/preview',headers=b,json={"lead_ids":[ids[1]]}).json()
    assert len(r['messages'])==1 and not r['skipped']

def test_analytics_counts(client):
    h=header(register(client))
    ident=client.post('/webhooks/manual',headers=h,json={"phone":"+201001112233"}).json()['lead_id']
    me=client.get('/auth/me',headers=h).json();detail=client.get(f'/leads/{ident}',headers=h).json()
    assert client.patch(f'/leads/{ident}',headers=h,json={"expected_updated_at":detail['updated_at'],"status":"won","assigned_user_id":me['id']}).status_code==200
    d=client.get('/dashboard/analytics',headers=h).json()
    assert (d['total'],d['new_week'],d['won'],d['closed_win_rate'])==(1,1,1,100)
    assert d['salespeople'][0]['assigned']==1 and d['salespeople'][0]['won']==1
