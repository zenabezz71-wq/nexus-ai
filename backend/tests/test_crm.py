from app.database import SessionLocal
from app.models import Lead


def create(client, h, number="+201012345678"):
    return client.post("/webhooks/test", headers=h, json={"name": "Test Lead", "phone": number, "email": "sales@business.test", "consent": True}).json()["lead_id"]


def test_lead_edit_and_feedback(client, token):
    h = {"Authorization": "Bearer "+token}
    ident = create(client, h)
    current = client.get(f"/leads/{ident}", headers=h).json()
    people = client.get("/workspace/salespeople", headers=h).json()
    r = client.patch(f"/leads/{ident}", headers=h, json={"expected_updated_at": current["updated_at"], "status": "contacted", "name": "Edited Lead", "goal": "Requested a later call", "assigned_user_id": people[0]["id"], "amount": 100, "currency": "egp"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "contacted" and data["name"] == "Edited Lead" and data["currency"] == "EGP"
    assert data["assigned_user_id"] == people[0]["id"] and data["consent"]
    note = client.post(f"/leads/{ident}/feedback", headers=h, json={"body": "Called, wants a quote next week."})
    assert note.status_code == 200 and note.json()["feedback"][0]["author"]
    assert note.json()["feedback"][0]["created_at"]
    assert client.get(f"/leads/{ident}", headers=h).json()["feedback"][0]["body"] == "Called, wants a quote next week."
    assert client.post(f"/leads/{ident}/feedback", headers=h, json={"body": "  "}).status_code == 400
    # Stale edits cannot silently overwrite the saved changes.
    assert client.patch(f"/leads/{ident}", headers=h, json={"expected_updated_at": current["updated_at"], "status": "won"}).status_code == 409


def test_contact_change_revokes_consent_and_duplicate_phone(client, token):
    h = {"Authorization": "Bearer "+token}; ident = create(client, h); other = create(client, h, "+201012345679")
    current = client.get(f"/leads/{ident}", headers=h).json()
    assert client.patch(f"/leads/{ident}", headers=h, json={"expected_updated_at": current["updated_at"], "email": "new@business.test"}).json()["consent"] is False
    current = client.get(f"/leads/{ident}", headers=h).json()
    assert client.patch(f"/leads/{ident}", headers=h, json={"expected_updated_at": current["updated_at"], "phone": "+201012345679"}).status_code == 409
    assert client.patch(f"/leads/{ident}", headers=h, json={"expected_updated_at": current["updated_at"], "assigned_user_id": 99999}).status_code == 400
    assert client.patch(f"/leads/{ident}", headers=h, json={"expected_updated_at": current["updated_at"], "status": "invented"}).status_code == 422
    assert client.patch(f"/leads/{ident}", headers=h, json={"expected_updated_at": current["updated_at"], "email": "bad@"}).status_code == 400


def test_crm_scope_and_do_not_contact(client, token):
    h = {"Authorization": "Bearer "+token}; ident = create(client, h)
    current = client.get(f"/leads/{ident}", headers=h).json()
    assert client.patch(f"/leads/{ident}", headers=h, json={"expected_updated_at": current["updated_at"], "do_not_contact": True}).json()["opted_out"]
    assert client.get(f"/leads/{ident}").status_code == 401
    db = SessionLocal(); row = db.get(Lead, ident); row.organization_id = 1; db.commit(); db.close()
    assert client.get(f"/leads/{ident}", headers=h).status_code == 404
    assert client.post(f"/leads/{ident}/feedback", headers=h, json={"body": "No access"}).status_code == 404
