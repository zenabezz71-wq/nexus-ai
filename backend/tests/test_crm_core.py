"""Phase 2 Core CRM API: contacts, pipelines, deals, tasks, activities, convert."""
from tests.test_foundation import signup, add_member, login, PASSWORD
from app.database import SessionLocal
from app.models import User, Membership
from sqlalchemy import select


def make_lead(client, headers, phone="+201111111111"):
    import io
    csv = "name,phone\nPipeline Lead," + phone + "\n"
    r = client.post("/leads/import", files={"file": ("leads.csv", io.BytesIO(csv.encode()), "text/csv")}, headers=headers)
    assert r.status_code == 200, r.text
    leads = client.get("/leads", headers=headers).json()
    return leads[0]["id"]


def org_of(client, headers):
    return client.get("/auth/me", headers=headers).json()["organization_id"]


def test_contacts_crud_and_search(client):
    h = signup(client, "crm-a@example.com", "CRM A")
    r = client.post("/contacts", json={"name": "Mona Ali", "phone": "+201000000001", "company": "Mona Co", "tags": ["vip"]}, headers=h)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert r.json()["assigned_to"] is not None
    lst = client.get("/contacts", headers=h).json()
    assert [c["id"] for c in lst] == [cid]
    assert client.get("/contacts", params={"q": "mona co"}, headers=h).json()[0]["id"] == cid
    r = client.patch(f"/contacts/{cid}", json={"priority": "high"}, headers=h)
    assert r.json()["priority"] == "high"
    prof = client.get(f"/contacts/{cid}", headers=h).json()
    assert prof["name"] == "Mona Ali" and any(a["kind"] == "contact.created" for a in prof["activities"])
    assert client.delete(f"/contacts/{cid}", headers=h).json()["ok"] is True
    assert client.get("/contacts", headers=h).json() == []


def test_pipeline_board_flow(client):
    h = signup(client, "crm-b@example.com", "CRM B")
    cid = client.post("/contacts", json={"name": "Karim"}, headers=h).json()["id"]
    pipes = client.get("/pipelines", headers=h).json()
    assert len(pipes) == 1 and len(pipes[0]["stages"]) == 7
    stages = pipes[0]["stages"]
    assert [s["name"] for s in stages][:2] == ["New", "Contacted"]
    r = client.post("/deals", json={"title": "Karim deal", "contact_id": cid, "amount": 5000}, headers=h)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["stage_id"] == stages[0]["id"] and d["status"] == "open"
    won = [s for s in stages if s["is_won"]][0]
    r = client.patch(f"/deals/{d['id']}", json={"stage_id": won["id"]}, headers=h)
    assert r.json()["status"] == "won" and r.json()["probability"] == 100
    acts = client.get("/activities", params={"deal_id": d["id"]}, headers=h).json()
    kinds = [a["kind"] for a in acts]
    assert "deal.created" in kinds and "deal.stage_changed" in kinds
    board = client.get("/deals", params={"pipeline_id": pipes[0]["id"]}, headers=h).json()
    assert [x["id"] for x in board] == [d["id"]]


def test_sales_sees_only_own_records(client):
    h = signup(client, "crm-c@example.com", "CRM C")
    org = org_of(client, h)
    add_member(org, "crm-c-sales@example.com", "sales")
    hs = login(client, "crm-c-sales@example.com")
    mine = client.post("/contacts", json={"name": "Mine"}, headers=hs).json()["id"]
    theirs = client.post("/contacts", json={"name": "Theirs"}, headers=h).json()["id"]
    sales_list = client.get("/contacts", headers=hs).json()
    assert [c["id"] for c in sales_list] == [mine]
    assert client.get(f"/contacts/{theirs}", headers=hs).status_code == 404
    assert client.delete(f"/contacts/{mine}", headers=hs).status_code == 403
    # owner sees both
    assert len(client.get("/contacts", headers=h).json()) == 2


def test_lead_convert(client):
    h = signup(client, "crm-d@example.com", "CRM D")
    lid = make_lead(client, h)
    r = client.post(f"/leads/{lid}/convert", headers=h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["already_converted"] is False
    assert body["contact"]["lead_id"] == lid
    again = client.post(f"/leads/{lid}/convert", headers=h).json()
    assert again["already_converted"] is True
    leads = client.get("/leads", headers=h).json()
    assert leads[0]["status"] == "converted"


def test_tasks_flow(client):
    h = signup(client, "crm-e@example.com", "CRM E")
    cid = client.post("/contacts", json={"name": "Tasky"}, headers=h).json()["id"]
    r = client.post("/tasks", json={"title": "Call back", "contact_id": cid, "due_at": "2026-11-25T10:00:00"}, headers=h)
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    open_tasks = client.get("/tasks", params={"status": "open"}, headers=h).json()
    assert [t["id"] for t in open_tasks] == [tid]
    r = client.patch(f"/tasks/{tid}", json={"status": "done"}, headers=h)
    assert r.json()["status"] == "done" and r.json()["completed_at"]
    assert client.get("/tasks", params={"status": "open"}, headers=h).json() == []
    prof = client.get(f"/contacts/{cid}", headers=h).json()
    assert any(a["kind"] == "task.completed" for a in prof["activities"])


def test_cross_org_isolation(client):
    h1 = signup(client, "crm-f1@example.com", "CRM F1")
    h2 = signup(client, "crm-f2@example.com", "CRM F2")
    cid = client.post("/contacts", json={"name": "Isolated"}, headers=h1).json()["id"]
    assert client.get(f"/contacts/{cid}", headers=h2).status_code == 404
    assert client.patch(f"/contacts/{cid}", json={"name": "x"}, headers=h2).status_code == 404
    assert client.get("/contacts", headers=h2).json() == []
    assert client.get("/activities", headers=h2).json() == []
