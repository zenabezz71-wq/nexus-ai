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


def test_lead_delete(client):
    h = signup(client, "crm-del@example.com", "CRM Del")
    lid = make_lead(client, h)
    client.post(f"/leads/{lid}/feedback", json={"body": "note"}, headers=h)
    contact = client.post(f"/leads/{lid}/convert", headers=h).json()["contact"]
    add_member(org_of(client, h), "crm-del-member@example.com", "salesperson")
    mh = login(client, "crm-del-member@example.com")
    assert client.delete(f"/leads/{lid}", headers=mh).status_code == 403
    r = client.delete(f"/leads/{lid}", headers=h)
    assert r.status_code == 200, r.text
    assert client.get(f"/leads/{lid}", headers=h).status_code == 404
    assert client.get("/leads", headers=h).json() == []
    kept = client.get(f"/contacts/{contact['id']}", headers=h).json()
    assert kept["lead_id"] is None


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


def test_stage_management(client):
    h = signup(client, "crm-stages@example.com", "CRM Stages")
    pipes = client.get("/pipelines", headers=h).json()
    pipe = pipes[0]
    n0 = len(pipe["stages"])
    r = client.post(f"/pipelines/{pipe['id']}/stages", json={"name": "Discovery", "probability": 30}, headers=h)
    assert r.status_code == 201, r.text
    st = r.json()
    assert st["position"] == n0
    r = client.patch(f"/stages/{st['id']}", json={"name": "Discovery Call", "position": 1}, headers=h)
    assert r.json()["name"] == "Discovery Call" and r.json()["position"] == 1
    stages = client.get("/pipelines", headers=h).json()[0]["stages"]
    mine = [x for x in stages if x["id"] == st["id"]][0]
    assert mine["position"] == 1 and mine["name"] == "Discovery Call"
    # cannot delete a stage that holds a deal
    cid = client.post("/contacts", json={"name": "Stage Guard"}, headers=h).json()["id"]
    deal = client.post("/deals", json={"title": "Guard deal", "contact_id": cid}, headers=h).json()
    r = client.delete(f"/stages/{deal['stage_id']}", headers=h)
    assert r.status_code == 409
    # empty stage deletes fine
    r = client.delete(f"/stages/{st['id']}", headers=h)
    assert r.json()["ok"] is True
    stages = client.get("/pipelines", headers=h).json()[0]["stages"]
    assert all(s["id"] != st["id"] for s in stages)
    acts = client.get("/activities", headers=h).json()
    kinds = [a["kind"] for a in acts]
    assert "pipeline.stage_added" in kinds and "pipeline.stage_deleted" in kinds


def test_stage_management_requires_settings_permission(client):
    h = signup(client, "crm-stages2@example.com", "CRM Stages2")
    org = org_of(client, h)
    add_member(org, "crm-sales2@example.com", "sales")
    sales_h = login(client, "crm-sales2@example.com")
    pipe = client.get("/pipelines", headers=h).json()[0]
    r = client.post(f"/pipelines/{pipe['id']}/stages", json={"name": "Nope"}, headers=sales_h)
    assert r.status_code == 403
    r = client.patch(f"/stages/{pipe['stages'][0]['id']}", json={"name": "Nope"}, headers=sales_h)
    assert r.status_code == 403
    r = client.delete(f"/stages/{pipe['stages'][0]['id']}", headers=sales_h)
    assert r.status_code == 403
    # cross-org: another org's stage is invisible
    h2 = signup(client, "crm-stages3@example.com", "CRM Stages3")
    r = client.patch(f"/stages/{pipe['stages'][0]['id']}", json={"name": "Hijack"}, headers=h2)
    assert r.status_code == 404


def test_contacts_export(client):
    h = signup(client, "crm-exp@example.com", "CRM Exp")
    client.post("/contacts", json={"name": "Exp One", "phone": "+201000000009", "tags": ["vip"]}, headers=h)
    r = client.get("/contacts/export", headers=h)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("name,phone,email")
    assert "Exp One" in lines[1] and "vip" in lines[1]
    org = client.get("/auth/me", headers=h).json()["organization_id"]
    add_member(org, "crm-exp-sales@example.com", "sales")
    mh = login(client, "crm-exp-sales@example.com")
    assert client.get("/contacts/export", headers=mh).status_code == 403
