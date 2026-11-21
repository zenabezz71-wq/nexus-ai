"""Copilot: rule-based answers from live workspace data."""
from tests.test_foundation import signup
from tests.test_crm_core import make_lead


def test_copilot_intents(client):
    h = signup(client, "copilot-a@example.com", "Co A")
    lid = make_lead(client, h)
    contact = client.post(f"/leads/{lid}/convert", headers=h).json()["contact"]
    deal = client.post("/deals", json={"title": "Risky", "contact_id": contact["id"], "amount": 300}, headers=h).json()
    client.patch(f"/deals/{deal['id']}", json={"expected_close": "2020-01-01"}, headers=h)
    client.post("/tasks", json={"title": "Old call", "due_at": "2020-01-01T09:00:00"}, headers=h)

    r = client.post("/copilot/ask", json={"question": "مين محتاج متابعة النهارده؟"}, headers=h)
    assert r.status_code == 200, r.text
    assert "Old call" in r.json()["answer"] and r.json()["method"].startswith("Rule-based")

    r = client.post("/copilot/ask", json={"question": "which deals are at risk?"}, headers=h)
    assert "Risky" in r.json()["answer"]

    r = client.post("/copilot/ask", json={"question": "اعمل تقرير مبيعات الشهر ده"}, headers=h)
    assert "Sales report" in r.json()["answer"] and "New leads this month: 1" in r.json()["answer"]

    r = client.post("/copilot/ask", json={"question": "اكتب رسالة متابعة"}, headers=h)
    assert "Draft follow-up" in r.json()["answer"] and "template" in r.json()["method"]

    r = client.post("/copilot/ask", json={"question": "إحصائيات العملاء"}, headers=h)
    assert "1 leads" in r.json()["answer"]

    r = client.post("/copilot/ask", json={"question": "hello"}, headers=h)
    assert r.json()["intent"] == "help"


def test_copilot_best_salesperson_empty(client):
    h = signup(client, "copilot-b@example.com", "Co B")
    r = client.post("/copilot/ask", json={"question": "best salesperson this month?"}, headers=h)
    assert "no leader" in r.json()["answer"]
