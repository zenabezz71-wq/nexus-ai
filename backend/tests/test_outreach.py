import hashlib
import hmac
import json
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
import httpx
import pytest
from app.config import settings
from app.database import SessionLocal
from app.models import Lead, User, Membership
from app.outreach import OutreachQuota, OutreachSend
from app.whatsapp import WhatsAppSend, WhatsAppSuppression

@pytest.fixture
def h(token): return {"Authorization": f"Bearer {token}"}

@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def blocked(*args, **kwargs): raise AssertionError("Unexpected external HTTP call")
    monkeypatch.setattr(httpx, "post", blocked)
    monkeypatch.setattr(httpx, "get", blocked)

@pytest.fixture
def configured(monkeypatch):
    for key, value in dict(outreach_enabled=True, brevo_api_key="test-not-a-real-key", outreach_sender_email="sender@business.test", outreach_sender_name="Test Business", outreach_sender_verified=True, outreach_postal_address="Test postal address, test fixture only", outreach_public_api_url="https://test.example", outreach_daily_cap=250).items(): monkeypatch.setattr(settings, key, value)

@pytest.fixture
def wa_configured(monkeypatch):
    for key, value in dict(whatsapp_enabled=True, whatsapp_access_token="test-not-a-real-token", whatsapp_phone_number_id="123", whatsapp_business_account_id="456", whatsapp_template_name="test_offer", whatsapp_template_language="en_US", whatsapp_app_secret="test-secret", whatsapp_webhook_verify_token="test-verify", whatsapp_cost_acknowledged=True, whatsapp_daily_cap=20).items(): monkeypatch.setattr(settings, key, value)
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(200, json={"data": [{"name": "test_offer", "language": "en_US", "status": "APPROVED", "category": "MARKETING", "components": [{"type": "BODY", "text": "Hi {{1}}, a promotional offer. Reply STOP to opt out."}]}]}))


def lead(client, h, *, phone="+201012345678", email="recipient@business.test", consent=True, name="Mona"):
    r = client.post("/webhooks/test", headers=h, json={"name": name, "phone": phone, "email": email, "consent": consent})
    assert r.status_code == 200
    return r.json()["lead_id"]


def preview(client, h, ident, path="/outreach"):
    r = client.post(path+"/preview", headers=h, json={"lead_ids": [ident]})
    assert r.status_code == 200, r.text
    return r.json()


def send(client, h, p, path="/outreach"):
    return client.post(path+"/send", headers=h, json={"review_token": p["review_token"]})


def test_default_off(client, h):
    ident = lead(client, h)
    p = preview(client, h, ident)
    assert p["messages"][0]["recipient"] == "recipient@business.test"
    assert "Live sending is disabled (demo mode)" in p["blockers"]
    assert send(client, h, p).status_code == 409
    assert client.get("/outreach/status", headers=h).json()["attempts_today"] == 0
    assert client.get("/whatsapp/status", headers=h).json()["ready"] is False


def test_missing_consent_invalid_and_sample_rejected(client, h):
    ids = [lead(client, h, consent=False), lead(client, h, phone="+201012345679", email="bad\r\n@bad.com"), lead(client, h, phone="+201012345680", email="sample@example.com")]
    p = client.post("/outreach/preview", headers=h, json={"lead_ids": ids}).json()
    assert len(p["messages"]) == 1 and p["messages"][0]["demo_only"] and len(p["skipped"]) == 2


def test_success_dedup_and_audit(client, h, configured, monkeypatch):
    sent = []
    def mock(*args, **kwargs): sent.append(kwargs["json"]); return httpx.Response(201, json={"messageId": "test-id"})
    monkeypatch.setattr(httpx, "post", mock)
    ident = lead(client, h)
    p = preview(client, h, ident)
    assert "Mona" in p["messages"][0]["body"] and "Unsubscribe:" in p["messages"][0]["body"]
    assert send(client, h, p).json()["results"][0]["status"] == "accepted"
    assert sent[0]["textContent"] == p["messages"][0]["body"]
    assert send(client, h, p).status_code == 409
    assert not preview(client, h, ident)["messages"]
    status = client.get("/outreach/status", headers=h).json()
    assert status["attempts_today"] == 1 and status["remaining_today"] == 249
    assert status["logs"][0]["provider_message_id"] == "test-id"


def test_content_change_invalidates_review(client, h, configured):
    ident = lead(client, h)
    p = preview(client, h, ident)
    assert client.put("/outreach/template", headers=h, json={"subject": "New subject", "body": "Hi {name}"}).status_code == 200
    assert send(client, h, p).status_code == 409


def test_optout_survives_new_lead_and_consent_update(client, h, configured):
    ident = lead(client, h)
    p = preview(client, h, ident)
    token = parse_qs(urlparse(p["messages"][0]["body"].split("Unsubscribe: ")[1]).query)["token"][0]
    assert client.get("/outreach/unsubscribe", params={"token": token}).status_code == 200
    # GET is a confirmation page, not an opt-out caused by link scanners.
    assert preview(client, h, ident)["messages"]
    assert client.post("/outreach/unsubscribe", data={"token": token}).status_code == 200
    assert client.post("/outreach/unsubscribe", data={"token": token}).status_code == 200
    assert send(client, h, p).status_code == 409
    another = lead(client, h, phone="+201012345679", email=" RECIPIENT@BUSINESS.TEST ")
    assert not preview(client, h, another)["messages"]
    assert client.get("/outreach/unsubscribe", params={"token": "tampered"}).status_code == 400


def test_quota_atomic_boundary_and_hard_cap(client, h, configured, monkeypatch):
    monkeypatch.setattr(settings, "outreach_daily_cap", 900)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(201, json={"messageId": "id"}))
    db = SessionLocal(); db.add(OutreachQuota(day=datetime.now(timezone.utc).date().isoformat(), used=289)); db.commit(); db.close()
    a = lead(client, h)
    b = lead(client, h, phone="+201012345679", email="second@business.test")
    assert send(client, h, preview(client, h, a)).json()["results"][0]["status"] == "accepted"
    result = send(client, h, preview(client, h, b))
    assert result.json()["results"][0]["status"] == "not_sent"
    assert client.get("/outreach/status", headers=h).json()["attempts_today"] == 290


@pytest.mark.parametrize("outcome,status", [(429,"rejected"), (500,"rejected"), ("timeout","unknown")])
def test_provider_failure_no_retry(client, h, configured, monkeypatch, outcome, status):
    def mock(*args, **kwargs):
        if outcome == "timeout": raise httpx.ReadTimeout("timeout")
        return httpx.Response(outcome)
    monkeypatch.setattr(httpx, "post", mock)
    ident = lead(client, h)
    p = preview(client, h, ident)
    assert send(client, h, p).json()["results"][0]["status"] == status
    assert send(client, h, p).status_code == 409
    assert client.get("/outreach/status", headers=h).json()["attempts_today"] == 1


def test_workspace_and_role_checks(client, h, configured):
    ident = lead(client, h)
    db = SessionLocal(); item = db.get(Lead, ident); item.organization_id = 1; db.commit(); db.close()
    assert client.post("/outreach/preview", headers=h, json={"lead_ids": [ident]}).status_code == 404
    db = SessionLocal(); user = db.query(User).filter_by(email="test@example.com").one(); membership = db.query(Membership).filter_by(user_id=user.id).one(); membership.role = "member"; db.commit(); db.close()
    assert client.post("/outreach/preview", headers=h, json={"lead_ids": [ident]}).status_code == 403
    assert client.put("/outreach/template", headers=h, json={"subject": "a", "body": "b"}).status_code == 403


def test_duplicate_email_selection(client, h, configured):
    a = lead(client, h)
    b = lead(client, h, phone="+201012345679")
    p = client.post("/outreach/preview", headers=h, json={"lead_ids": [a, b]}).json()
    assert len(p["messages"]) == 1 and len(p["skipped"]) == 1


def test_wa_template_send_and_signed_stop(client, h, wa_configured, monkeypatch):
    sent = []
    def mock(*args, **kwargs): sent.append(kwargs["json"]); return httpx.Response(200, json={"messages": [{"id": "wamid.test"}]})
    monkeypatch.setattr(httpx, "post", mock)
    ident = lead(client, h)
    p = preview(client, h, ident, "/whatsapp")
    assert p["messages"][0]["body"].startswith("Hi Mona")
    assert send(client, h, p, "/whatsapp").json()["results"][0]["status"] == "accepted"
    assert sent[0]["type"] == "template" and sent[0]["to"] == "201012345678"
    assert send(client, h, p, "/whatsapp").status_code == 409
    payload = {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "123"}, "messages": [{"from": "201012345678", "text": {"body": "STOP"}}], "statuses": [{"id": "wamid.test", "status": "delivered"}]}}]}]}
    raw = json.dumps(payload).encode()
    assert client.post("/whatsapp/webhook", content=raw).status_code == 403
    signature = "sha256="+hmac.new(b"test-secret", raw, hashlib.sha256).hexdigest()
    assert client.post("/whatsapp/webhook", content=raw, headers={"x-hub-signature-256": signature}).status_code == 200
    assert client.post("/whatsapp/webhook", content=raw, headers={"x-hub-signature-256": signature}).status_code == 200
    db = SessionLocal(); assert db.get(WhatsAppSuppression, "201012345678"); assert db.get(Lead, ident).opted_out; assert db.query(WhatsAppSend).one().status == "delivered"; db.close()
    assert client.get("/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "test-verify", "hub.challenge": "1234"}).text == "1234"


def test_wa_unsupported_template_blocks(client, h, wa_configured, monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(200, json={"data": []}))
    ident = lead(client, h)
    assert client.post("/whatsapp/preview", headers=h, json={"lead_ids": [ident]}).status_code == 409


def test_wa_not_configured_preview_is_honest(client, h):
    ident = lead(client, h)
    p = preview(client, h, ident, "/whatsapp")
    assert p["messages"][0]["demo_only"] and not p["review_token"] and p["blockers"]


def test_demo_contacts_can_preview_but_never_send(client, h, configured, wa_configured):
    ident = lead(client, h, email="sample@example.com", name="Demo Person")
    for path in ("/outreach", "/whatsapp"):
        p = preview(client, h, ident, path)
        assert p["messages"][0]["demo_only"]
        assert any("preview-only" in x for x in p["blockers"])
        assert send(client, h, p, path).status_code == 409
