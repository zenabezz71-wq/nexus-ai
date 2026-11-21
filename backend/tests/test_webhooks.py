"""Inbound webhooks: key-authenticated lead intake, idempotent, rotatable."""
from tests.test_foundation import signup, login, add_member


def _url(client, h):
    r = client.get("/integrations", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["webhook"]["url"]


def test_webhook_lead_intake(client):
    h = signup(client, "wh-a@example.com", "Co WA")
    url = _url(client, h)
    path = url[url.index("/webhooks/"):]

    r = client.post(path, json={"phone": "+201555000001", "name": "Webhook Lead", "goal": "wants a demo"})
    assert r.status_code == 201, r.text
    lid = r.json()["lead_id"]
    assert r.json()["deduped"] is False

    # same phone again -> dedupe, no duplicate
    r = client.post(path, json={"phone": "+201555000001", "name": "Changed name"})
    assert r.status_code == 201 and r.json()["deduped"] is True and r.json()["lead_id"] == lid
    leads = client.get("/leads", headers=h).json()
    assert sum(1 for x in leads if x["phone"].endswith("555000001")) == 1
    lead = [x for x in leads if x["id"] == lid][0]
    assert lead["source"].startswith("webhook:") and lead["status"] == "unclassified"

    # bad key -> 404
    r = client.post("/webhooks/leads/not-a-real-key", json={"phone": "+201555000002"})
    assert r.status_code == 404


def test_webhook_key_rotation_and_permissions(client):
    h = signup(client, "wh-b@example.com", "Co WB")
    old = _url(client, h)
    r = client.post("/integrations/webhook-key/rotate", headers=h)
    assert r.status_code == 200, r.text
    new = r.json()["url"]
    assert new != old
    assert client.post(old[old.index("/webhooks/"):], json={"phone": "+201555000010"}).status_code == 404
    assert client.post(new[new.index("/webhooks/"):], json={"phone": "+201555000010"}).status_code == 201

    # sales member: sees status list but no key, cannot rotate
    org = client.get("/auth/me", headers=h).json()["organization_id"]
    add_member(org, "wh-b-sales@example.com", "sales")
    hs = login(client, "wh-b-sales@example.com")
    r = client.get("/integrations", headers=hs)
    assert r.status_code == 200 and r.json()["webhook"] is None
    assert len(r.json()["integrations"]) == 4
    assert client.post("/integrations/webhook-key/rotate", headers=hs).status_code == 403
