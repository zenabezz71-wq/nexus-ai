"""In-app notifications: assignment events, lazy overdue reminder, read flows."""
from tests.test_foundation import signup, add_member, login


def _org(client, h):
    return client.get("/auth/me", headers=h).json()


def test_assignment_notifications_and_read(client):
    h = signup(client, "notif-a@example.com", "Notif A")
    org = _org(client, h)["organization_id"]
    add_member(org, "notif-a-sales@example.com", "sales")
    uid = client.get("/auth/me", headers=login(client, "notif-a-sales@example.com")).json()["id"]
    t = client.post("/tasks", json={"title": "Follow up"}, headers=h).json()
    client.patch(f"/tasks/{t['id']}", json={"assigned_to": uid}, headers=h)
    c = client.post("/contacts", json={"name": "Nadir"}, headers=h).json()
    d = client.post("/deals", json={"title": "Big one", "contact_id": c["id"]}, headers=h).json()
    client.patch(f"/deals/{d['id']}", json={"assigned_to": uid}, headers=h)

    mh = login(client, "notif-a-sales@example.com")
    r = client.get("/notifications", headers=mh)
    assert r.status_code == 200, r.text
    body = r.json()
    kinds = [n["kind"] for n in body["notifications"]]
    assert "task.assigned" in kinds and "deal.assigned" in kinds
    assert body["unread"] == len(body["notifications"]) >= 2
    nid = body["notifications"][0]["id"]
    assert client.post(f"/notifications/{nid}/read", headers=mh).json()["read"] is True
    assert client.get("/notifications", headers=mh).json()["unread"] == body["unread"] - 1
    marked = client.post("/notifications/read-all", headers=mh).json()["marked"]
    assert marked == body["unread"] - 1
    assert client.get("/notifications", headers=mh).json()["unread"] == 0
    # owner's notifications are separate: assigning to someone else notifies only them
    owner_notes = client.get("/notifications", headers=h).json()["notifications"]
    assert not [n for n in owner_notes if n["kind"] in ("task.assigned", "deal.assigned")]


def test_lazy_overdue_reminder(client):
    h = signup(client, "notif-b@example.com", "Notif B")
    client.post("/tasks", json={"title": "Old task", "due_at": "2020-01-01T09:00:00"}, headers=h)
    first = client.get("/notifications", headers=h).json()
    reminders = [n for n in first["notifications"] if n["kind"] == "tasks.overdue_reminder"]
    assert len(reminders) == 1 and "1 overdue" in reminders[0]["body"]
    second = client.get("/notifications", headers=h).json()
    assert len([n for n in second["notifications"] if n["kind"] == "tasks.overdue_reminder"]) == 1
