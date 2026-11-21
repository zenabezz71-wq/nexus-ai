"""Smart Follow-up (next actions) and Conversation Summary (lead digest)."""
from tests.test_foundation import signup
from tests.test_crm_core import make_lead
from tests.test_insights import _set_status


def test_next_actions(client):
    h = signup(client, "sf-a@example.com", "Co SA")
    hot = make_lead(client, h, "+201000000011")
    idle = make_lead(client, h, "+201000000012")
    _set_status(client, h, hot, "hot_lead")
    _set_status(client, h, idle, "warm_lead")
    client.post("/tasks", json={"title": "Late call", "due_at": "2020-01-01T09:00:00"}, headers=h)

    r = client.get("/insights/next-actions", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["method"].startswith("Rule-based")
    types = {a["type"] for a in d["actions"]}
    assert "overdue_task" in types
    assert "hot_lead_no_task" in types
    assert "lead_idle" in types
    # overdue sorts first
    assert d["actions"][0]["type"] == "overdue_task"
    assert all(a["reason"] for a in d["actions"])


def test_lead_digest(client):
    h = signup(client, "sf-b@example.com", "Co SB")
    lid = make_lead(client, h)
    client.post("/activities", json={"body": "first call", "lead_id": lid}, headers=h)
    client.post("/activities", json={"body": "sent details", "lead_id": lid}, headers=h)
    client.post("/tasks", json={"title": "Follow up", "lead_id": lid}, headers=h)

    r = client.get(f"/insights/lead-digest/{lid}", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["activity_count"] >= 2
    bodies = [a["body"] for a in d["latest"]]
    assert any("sent details" in b or "first call" in b for b in bodies)
    assert d["open_tasks"][0]["title"] == "Follow up"
    assert d["days_since_last_touch"] == 0
    assert "not an AI-generated summary" in d["method"]

    r = client.get("/insights/lead-digest/999999", headers=h)
    assert r.status_code == 404
