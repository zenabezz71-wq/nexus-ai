"""Blueprint section 9: product acceptance criteria, proven as tests."""
from tests.test_foundation import signup, login, add_member
from tests.test_crm_core import make_lead


def _org(client, h):
    return client.get("/auth/me", headers=h).json()["organization_id"]


def test_tenant_isolation_direct_api(client):
    """Company A cannot reach company B's records even by direct id."""
    ha = signup(client, "acc-a@example.com", "Acc A")
    hb = signup(client, "acc-b@example.com", "Acc B")
    lead_b = make_lead(client, hb)
    contact_b = client.post(f"/leads/{lead_b}/convert", headers=hb).json()["contact"]
    deal_b = client.post("/deals", json={"title": "B deal", "contact_id": contact_b["id"], "amount": 100}, headers=hb).json()
    task_b = client.post("/tasks", json={"title": "B task"}, headers=hb).json()

    assert client.get(f"/leads/{lead_b}", headers=ha).status_code == 404
    assert client.get(f"/contacts/{contact_b['id']}", headers=ha).status_code == 404
    assert client.patch(f"/deals/{deal_b['id']}", json={"title": "stolen"}, headers=ha).status_code == 404
    assert client.patch(f"/tasks/{task_b['id']}", json={"title": "stolen"}, headers=ha).status_code == 404
    assert client.get("/leads", headers=ha).json() == []
    assert all(c["id"] != contact_b["id"] for c in client.get("/contacts", headers=ha).json())
    # B's lead ids never leak through A's AI endpoints
    digest = client.get(f"/insights/lead-digest/{lead_b}", headers=ha)
    assert digest.status_code == 404


def test_permission_enforcement_for_sales(client):
    """A sales member cannot execute actions outside their permissions."""
    h = signup(client, "acc-c@example.com", "Acc C")
    lid = make_lead(client, h)
    contact = client.post(f"/leads/{lid}/convert", headers=h).json()["contact"]
    deal = client.post("/deals", json={"title": "C deal", "contact_id": contact["id"]}, headers=h).json()
    org = _org(client, h)
    add_member(org, "acc-c-sales@example.com", "sales")
    hs = login(client, "acc-c-sales@example.com")

    assert client.get("/contacts/export", headers=hs).status_code == 403
    assert client.delete(f"/deals/{deal['id']}", headers=hs).status_code == 403
    assert client.post("/integrations/webhook-key/rotate", headers=hs).status_code == 403
    assert client.get("/audit-log", headers=hs).status_code == 403


def test_convert_never_duplicates(client):
    """Converting a lead twice creates one contact, not two."""
    h = signup(client, "acc-d@example.com", "Acc D")
    lid = make_lead(client, h)
    first = client.post(f"/leads/{lid}/convert", headers=h).json()
    second = client.post(f"/leads/{lid}/convert", headers=h).json()
    assert first["already_converted"] is False
    assert second["already_converted"] is True
    assert first["contact"]["id"] == second["contact"]["id"]
    contacts = client.get("/contacts", headers=h).json()
    assert len([c for c in contacts if c.get("lead_id") == lid or c["phone"] == second["contact"]["phone"]]) == 1


def test_stage_change_updates_reports(client):
    """Moving a deal to Won shows up in the executive report."""
    h = signup(client, "acc-e@example.com", "Acc E")
    lid = make_lead(client, h)
    contact = client.post(f"/leads/{lid}/convert", headers=h).json()["contact"]
    deal = client.post("/deals", json={"title": "Report deal", "contact_id": contact["id"], "amount": 700}, headers=h).json()
    before = client.get("/dashboard/executive?period=month", headers=h).json()
    stages = client.get("/pipelines", headers=h).json()[0]["stages"]
    won = next(s for s in stages if s["name"] == "Won")
    client.patch(f"/deals/{deal['id']}", json={"stage_id": won["id"]}, headers=h)
    after = client.get("/dashboard/executive?period=month", headers=h).json()
    assert after["deals_won_period"] == before["deals_won_period"] + 1
    assert after["revenue_period"] == before["revenue_period"] + 700


def test_ai_endpoints_respect_scope(client):
    """AI features only see data the caller may see."""
    h = signup(client, "acc-f@example.com", "Acc F")
    lid = make_lead(client, h)
    contact = client.post(f"/leads/{lid}/convert", headers=h).json()["contact"]
    client.post("/deals", json={"title": "Owner deal", "contact_id": contact["id"], "amount": 900}, headers=h)
    org = _org(client, h)
    add_member(org, "acc-f-sales@example.com", "sales")
    hs = login(client, "acc-f-sales@example.com")

    fc = client.get("/insights/forecast", headers=hs).json()
    assert fc["scope"] == "own" and fc["open_deals"] == 0 and fc["total_amount"] == 0
    r = client.post("/copilot/ask", json={"question": "sales report this month"}, headers=hs)
    assert r.status_code == 200
    assert "Open pipeline: 0 deal(s)" in r.json()["answer"]


def test_sensitive_actions_are_audited(client):
    """Sensitive operations land in the audit log, readable by owner only."""
    h = signup(client, "acc-g@example.com", "Acc G")
    lid = make_lead(client, h)
    client.post(f"/leads/{lid}/convert", headers=h)
    client.get("/contacts/export", headers=h)
    url = client.get("/integrations", headers=h).json()["webhook"]["url"]
    rw = client.post(url[url.index("/webhooks/"):], json={"phone": "+201555000099", "name": "Audit hook"})
    assert rw.status_code == 201, rw.text

    log = client.get("/audit-log", headers=h).json()
    actions = {e["action"] for e in log["entries"]}
    assert "lead.converted" in actions
    assert "webhook.lead" in actions
    assert any("export" in a for a in actions)
    wh = [e for e in log["entries"] if e["action"] == "webhook.lead"][0]
    assert wh["actor"] == "system"
