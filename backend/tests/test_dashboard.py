"""Executive dashboard endpoint."""
from tests.test_foundation import signup, add_member, login
from tests.test_crm_core import make_lead


def test_executive_dashboard(client):
    h = signup(client, "dash-a@example.com", "Dash A")
    lid = make_lead(client, h)
    contact = client.post(f"/leads/{lid}/convert", headers=h).json()["contact"]
    won = client.post("/deals", json={"title": "Won one", "contact_id": contact["id"], "amount": 1000}, headers=h).json()
    stages = client.get("/pipelines", headers=h).json()[0]["stages"]
    won_stage = next(s for s in stages if s["name"] == "Won")
    r = client.patch(f"/deals/{won['id']}", json={"stage_id": won_stage["id"]}, headers=h)
    assert r.json()["status"] == "won", r.text
    stale = client.post("/deals", json={"title": "Stale open", "contact_id": contact["id"]}, headers=h).json()
    client.patch(f"/deals/{stale['id']}", json={"expected_close": "2020-01-01"}, headers=h)
    growing = client.post("/deals", json={"title": "Growing", "contact_id": contact["id"], "amount": 500}, headers=h).json()
    qualified = next(s for s in stages if s["name"] == "Qualified")
    client.patch(f"/deals/{growing['id']}", json={"stage_id": qualified["id"]}, headers=h)
    client.post("/tasks", json={"title": "Late task", "due_at": "2020-01-01T10:00:00"}, headers=h)

    r = client.get("/dashboard/executive", params={"period": "week"}, headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["scope"] == "company"
    assert d["total_leads"] == 1
    assert d["new_leads_period"] == 1
    assert d["deals_won_period"] == 1 and d["revenue_period"] == 1000
    assert d["active_deals"] == 2 and d["pipeline_value"] == 500
    assert d["expected_revenue"] == 200
    assert d["conversion_rate_pct"] == 100.0
    assert [x["title"] for x in d["deals_at_risk"]] == ["Stale open"]
    assert d["tasks_overdue_count"] == 1
    assert d["team"] and d["team"][0]["deals_won"] == 1
    assert d["insights"] and "previous week" in d["insights"][0]
    assert d["insights_method"].startswith("Rule-based")
    assert client.get("/dashboard/executive", params={"period": "year"}, headers=h).status_code == 400


def test_executive_dashboard_own_scope(client):
    h = signup(client, "dash-b@example.com", "Dash B")
    org = client.get("/auth/me", headers=h).json()["organization_id"]
    add_member(org, "dash-b-sales@example.com", "sales")
    mh = login(client, "dash-b-sales@example.com")
    r = client.get("/dashboard/executive", headers=mh)
    assert r.status_code == 200, r.text
    assert r.json()["scope"] == "own"
    assert r.json()["team"] == []
