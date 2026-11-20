"""Platform-owner super-admin: enforcement, suspension, soft delete, audit."""
from sqlalchemy import select
from app.database import SessionLocal
from app.models import User, Organization, AuditLog
from tests.test_foundation import signup, add_member, login, PASSWORD
from tests.test_crm_core import make_lead


def make_operator(email="root@platform.example"):
    db = SessionLocal()
    u = db.scalar(select(User).where(User.email == email))
    if not u:
        from app.auth import hash_password
        u = User(email=email, password_hash=hash_password(PASSWORD), full_name="Platform Operator")
        db.add(u); db.flush()
    u.is_platform_admin = True
    db.commit(); db.close()
    return email


def test_non_operators_get_403(client):
    h = signup(client, "plat-owner@example.com", "Plat Org")
    org = client.get("/auth/me", headers=h).json()["organization_id"]
    assert client.get("/platform/organizations", headers=h).status_code == 403
    for role in ("admin", "manager", "sales"):
        email = f"plat-{role}@example.com"
        add_member(org, email, role)
        hr = login(client, email)
        assert client.get("/platform/organizations", headers=hr).status_code == 403, role


def test_operator_suspend_restore_delete(client):
    op_email = "root@platform.example"
    # operator needs a membership to authenticate; give them their own org
    hop = signup(client, op_email, "Platform Home")
    make_operator(op_email)
    h1 = signup(client, "plat-a@example.com", "Plat A")
    h2 = signup(client, "plat-b@example.com", "Plat B")
    org_b = client.get("/auth/me", headers=h2).json()["organization_id"]
    make_lead(client, h2, phone="+201222222222")

    orgs = client.get("/platform/organizations", headers=hop).json()
    by_name = {o["name"]: o for o in orgs}
    assert by_name["Plat B"]["lead_count"] == 1  # system_context: cross-org counts work

    # missing reason rejected
    assert client.delete(f"/platform/organizations/{org_b}", headers=hop).status_code == 400
    # cannot touch own org
    me = client.get("/auth/me", headers=hop).json()
    assert client.post(f"/platform/organizations/{me['organization_id']}/suspend", json={"reason": "test"}, headers=hop).status_code == 400

    # suspend
    r = client.post(f"/platform/organizations/{org_b}/suspend", json={"reason": "terms violation probe"}, headers=hop)
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False
    # suspended org members are locked out immediately
    assert client.get("/auth/me", headers=h2).status_code == 403
    assert client.post("/auth/login", json={"email": "plat-b@example.com", "password": PASSWORD}).status_code == 403
    # other orgs unaffected
    assert client.get("/auth/me", headers=h1).status_code == 200

    # restore
    r = client.post(f"/platform/organizations/{org_b}/restore", json={"reason": "false alarm"}, headers=hop)
    assert r.json()["is_active"] is True
    assert client.get("/auth/me", headers=h2).status_code == 200

    # soft delete
    r = client.delete(f"/platform/organizations/{org_b}", params={"reason": "operator probe cleanup"}, headers=hop)
    assert r.json()["mode"] == "soft-delete"
    assert client.get("/auth/me", headers=h2).status_code == 403

    # audit trail on the target org
    db = SessionLocal()
    actions = [a.action for a in db.scalars(select(AuditLog).where(AuditLog.organization_id == org_b)).all()]
    db.close()
    assert "platform.org_suspended" in actions
    assert "platform.org_restored" in actions
    assert "platform.org_deleted" in actions
