"""Phase 1 foundation: RBAC matrix, team endpoints, blueprint tenant schema."""
from sqlalchemy import select
from app.database import SessionLocal
from app.models import Organization, User, Membership
from app.auth import hash_password
from app.rbac import (
    permissions_for, has_permission,
    ROLE_OWNER, ROLE_ADMIN, ROLE_MANAGER, ROLE_SALES,
    BILLING_MANAGE, REPORTS_COMPANY, TEAM_MANAGE, LEADS_VIEW_ALL,
)
from app.tenant import Contact, Pipeline, PipelineStage, Deal, Task, Activity, Subscription

PASSWORD = "FoundationPass123"


def signup(client, email, company):
    r = client.post("/auth/signup", json={
        "email": email, "password": PASSWORD, "company_name": company, "full_name": "Owner " + company})
    assert r.status_code == 201, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def add_member(org_id, email, role):
    db = SessionLocal()
    u = User(email=email, password_hash=hash_password(PASSWORD), full_name="Member " + email)
    db.add(u); db.flush()
    m = Membership(user_id=u.id, organization_id=org_id, role=role)
    db.add(m); db.commit()
    mid = m.id; db.close()
    return mid


def login(client, email):
    r = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def test_rbac_matrix():
    owner = permissions_for(ROLE_OWNER, [])
    assert BILLING_MANAGE in owner and TEAM_MANAGE in owner and REPORTS_COMPANY in owner
    admin = permissions_for(ROLE_ADMIN, [])
    assert TEAM_MANAGE in admin and BILLING_MANAGE not in admin
    manager = permissions_for(ROLE_MANAGER, [])
    assert REPORTS_COMPANY in manager and TEAM_MANAGE not in manager
    sales = permissions_for(ROLE_SALES, [])
    assert REPORTS_COMPANY not in sales and "reports.own" in sales
    assert LEADS_VIEW_ALL in permissions_for(ROLE_SALES, [LEADS_VIEW_ALL])
    assert "not.a.permission" not in permissions_for(ROLE_OWNER, ["not.a.permission"])


def test_me_exposes_permissions(client):
    h = signup(client, "perm-owner@example.org", "PermCo")
    me = client.get("/auth/me", headers=h).json()
    assert me["role"] == "owner"
    assert BILLING_MANAGE in me["permissions"] and me["grants"] == []


def test_team_roles_and_grants(client):
    owner = signup(client, "team-owner@example.org", "TeamCo")
    org_id = client.get("/auth/me", headers=owner).json()["organization_id"]
    sales_mid = add_member(org_id, "team-sales@example.org", "sales")
    sales = login(client, "team-sales@example.org")

    members = client.get("/team/members", headers=sales).json()
    assert len(members) == 2  # team.view is held by every role
    assert {m["role"] for m in members} == {"owner", "sales"}

    # Sales cannot manage the team.
    assert client.patch(f"/team/members/{sales_mid}", headers=sales, json={"role": "manager"}).status_code == 403
    # Owner promotes sales to manager.
    r = client.patch(f"/team/members/{sales_mid}", headers=owner, json={"role": "manager"})
    assert r.status_code == 200 and r.json()["role"] == "manager"
    assert REPORTS_COMPANY in r.json()["permissions"]
    # Owner grants an extra permission; unknown permissions are rejected.
    r = client.put(f"/team/members/{sales_mid}/grants", headers=owner, json={"grants": [LEADS_VIEW_ALL, "nope.bad"]})
    assert r.status_code == 400
    r = client.put(f"/team/members/{sales_mid}/grants", headers=owner, json={"grants": [LEADS_VIEW_ALL]})
    assert r.status_code == 200 and r.json()["grants"] == [LEADS_VIEW_ALL]
    assert LEADS_VIEW_ALL in r.json()["permissions"]
    # The last owner cannot demote themselves.
    own_mid = [m for m in client.get("/team/members", headers=owner).json() if m["role"] == "owner"][0]["membership_id"]
    assert client.patch(f"/team/members/{own_mid}", headers=owner, json={"role": "admin"}).status_code == 400
    # Role strings are validated.
    assert client.patch(f"/team/members/{sales_mid}", headers=owner, json={"role": "superuser"}).status_code == 400


def test_tenant_schema_roundtrip():
    db = SessionLocal()
    org = Organization(name="SchemaCo", slug="schemaco")
    user = User(email="schema@example.org", password_hash=hash_password(PASSWORD), full_name="Schema User")
    db.add_all([org, user]); db.flush()
    membership = Membership(user_id=user.id, organization_id=org.id, role="owner")
    db.add(membership); db.flush()
    assert (membership.grants or []) == []
    contact = Contact(organization_id=org.id, name="Layla", phone="+201001234567", created_by=user.id)
    pipeline = Pipeline(organization_id=org.id, name="Main", is_default=True, created_by=user.id)
    db.add_all([contact, pipeline]); db.flush()
    stage = PipelineStage(organization_id=org.id, pipeline_id=pipeline.id, name="New Opportunity", position=1)
    db.add(stage); db.flush()
    deal = Deal(organization_id=org.id, title="First deal", contact_id=contact.id, pipeline_id=pipeline.id,
                stage_id=stage.id, amount=15000, currency="EGP", created_by=user.id)
    task = Task(organization_id=org.id, title="Call Layla", contact_id=contact.id, assigned_to=user.id, created_by=user.id)
    activity = Activity(organization_id=org.id, kind="deal_created", body="Deal created", user_id=user.id, deal_id=None)
    sub = Subscription(organization_id=org.id, plan="trial", status="trialing")
    db.add_all([deal, task, sub]); db.flush()
    activity.deal_id = deal.id
    db.commit()
    found = db.scalars(select(Deal).where(Deal.organization_id == org.id)).all()
    assert len(found) == 1 and found[0].contact_id == contact.id and found[0].deleted_at is None
    assert db.scalar(select(Subscription).where(Subscription.organization_id == org.id)).plan == "trial"
    db.close()


def test_analytics_permission_follows_matrix(client):
    owner = signup(client, "ana-owner@example.org", "AnaCo")
    assert client.get("/dashboard/analytics", headers=owner).status_code == 200
    org_id = client.get("/auth/me", headers=owner).json()["organization_id"]
    add_member(org_id, "ana-sales@example.org", "sales")
    sales = login(client, "ana-sales@example.org")
    assert client.get("/dashboard/analytics", headers=sales).status_code == 403
    add_member(org_id, "ana-manager@example.org", "manager")
    manager = login(client, "ana-manager@example.org")
    assert client.get("/dashboard/analytics", headers=manager).status_code == 200
