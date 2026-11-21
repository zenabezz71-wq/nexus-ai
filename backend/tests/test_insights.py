"""Sales Insights: rule-based lead scoring and pipeline forecast."""
from tests.test_foundation import signup
from tests.test_crm_core import make_lead


def _set_status(client, h, lead_id, status):
    cur = client.get(f"/leads/{lead_id}", headers=h).json()
    r = client.patch(f"/leads/{lead_id}", json={"status": status, "expected_updated_at": cur["updated_at"]}, headers=h)
    assert r.status_code == 200, r.text


def test_lead_scores(client):
    h = signup(client, "ins-a@example.com", "Co IA")
    hot = make_lead(client, h, "+201000000001")
    cold = make_lead(client, h, "+201000000002")
    _set_status(client, h, hot, "hot_lead")
    _set_status(client, h, cold, "cold_lead")
    for _ in range(3):
        client.post("/activities", json={"body": "call", "lead_id": hot}, headers=h)

    r = client.get("/insights/lead-scores", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["method"].startswith("Rule-based")
    scores = {s["lead_id"]: s for s in d["scores"]}
    assert scores[hot]["score"] > scores[cold]["score"]
    assert any("hot lead" in f for f in scores[hot]["factors"])
    assert any("activities" in f for f in scores[hot]["factors"])
    # demo-studio leads never appear
    assert all(s["lead_id"] in (hot, cold) for s in d["scores"])


def test_forecast(client):
    h = signup(client, "ins-b@example.com", "Co IB")
    lid = make_lead(client, h)
    contact = client.post(f"/leads/{lid}/convert", headers=h).json()["contact"]
    d1 = client.post("/deals", json={"title": "D1", "contact_id": contact["id"], "amount": 1000}, headers=h).json()
    d2 = client.post("/deals", json={"title": "D2", "contact_id": contact["id"], "amount": 500}, headers=h).json()
    client.patch(f"/deals/{d1['id']}", json={"expected_close": "2030-03-15"}, headers=h)
    # d2 stays unscheduled
    r = client.get("/insights/forecast", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["open_deals"] == 2 and d["total_amount"] == 1500
    assert d["by_month"][0]["month"] == "2030-03" and d["by_month"][0]["amount"] == 1000
    assert d["unscheduled"]["deals"] == 1 and d["unscheduled"]["amount"] == 500
    assert "probability" in d["method"]
