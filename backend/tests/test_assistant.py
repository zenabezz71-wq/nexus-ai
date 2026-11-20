import hashlib, hmac, json
from app.database import SessionLocal
from app.config import settings
from app.models import Lead
from app.assistant import ConvMessage, Conversation, analyse, norm
from sqlalchemy import select

DATA = {"email": "company@example.org", "password": "CompanyPassword123!", "company_name": "شركة الأمل", "full_name": "Owner"}
def signup(client, **v):
    r = client.post('/auth/signup', json=DATA | v); assert r.status_code == 201
    return {"Authorization": "Bearer " + r.json()["access_token"]}
def auth(token): return {"Authorization": "Bearer " + token}
def start(client, h, name=""):
    r = client.post('/assistant/simulations', json={"customer_name": name}, headers=h); assert r.status_code == 201
    return r.json()
def say(client, h, cid, text):
    r = client.post(f'/assistant/conversations/{cid}/messages', json={"body": text}, headers=h); assert r.status_code == 200, r.text
    return r.json()

def test_arabic_normalisation_and_intents():
    assert "اشتري" in norm("أشتري") and "ايه" in norm("إيه")
    i, s = analyse("عايز اعرف الأسعار بكام", {})
    assert "price" in i and "details" in i
    i, s = analyse("ميزانيتي ٥٠٠٠ جنيه", {"last_asked": "budget"})
    assert s["budget"] == 5000 and s["currency"] == "EGP"
    i, s = analyse("مش مهتم شكرا", {}); assert "not_interested" in i and "buy" not in i
    i, s = analyse("أنا جاهز أبدأ النهاردة وهدفع", {}); assert "buy" in i and s["timeline"] == "soon"
    i, s = analyse("مش جاهز دلوقتي", {}); assert "buy" not in i
    i, s = analyse("كلمني بعد أسبوعين", {}); assert "later" in i
    i, s = analyse("عايز اكلم حد من الفريق", {}); assert "human" in i

def test_qualification_flow_updates_crm_and_flags_hot(client):
    h = signup(client)
    conv = start(client, h)
    assert conv["engine"] == "rule_based_arabic" and conv["lead"]["source"] == "assistant_demo"
    c = say(client, h, conv["id"], "السلام عليكم")
    assert "شركة الأمل" in c["messages"][-1]["body"] and c["messages"][-1]["delivery"] == "simulated"
    c = say(client, h, conv["id"], "عايز اعمل حملة اعلانية لمشروعي الجديد")
    assert c["qualification"]["goal"].startswith("عايز اعمل") and c["lead"]["goal"]
    assert c["lead"]["status"] == "warm_lead"
    c = say(client, h, conv["id"], "ميزانيتي ١٠ الاف جنيه")
    assert c["qualification"]["budget"] == 10000 and c["lead"]["amount"] == 10000 and c["lead"]["currency"] == "EGP"
    assert not c["needs_attention"]
    c = say(client, h, conv["id"], "عايز ابدا النهاردة وهدفع")
    assert c["lead"]["status"] == "hot_lead" and c["needs_attention"]
    assert any("تنبيه تسليم" in n["body"] for n in c["lead"]["feedback"])
    assert any("غيّر التصنيف" in n["body"] for n in c["lead"]["feedback"])
    assert c["messages"][-1]["role"] == "assistant"

def test_human_takeover_stops_auto_reply_and_release(client):
    h = signup(client); cid = start(client, h)["id"]
    say(client, h, cid, "اهلا")
    assert client.post(f'/assistant/conversations/{cid}/human-reply', json={"body": "x"}, headers=h).status_code == 409
    c = client.post(f'/assistant/conversations/{cid}/takeover', headers=h).json(); assert c["mode"] == "human"
    n = len(c["messages"]); c = say(client, h, cid, "عايز اعرف تفاصيل اكتر")
    assert len(c["messages"]) == n + 1 and c["messages"][-1]["role"] == "customer" and c["needs_attention"]
    c = client.post(f'/assistant/conversations/{cid}/human-reply', json={"body": "أهلا، معاك سارة"}, headers=h).json()
    assert c["messages"][-1]["role"] == "human" and c["messages"][-1]["delivery"] == "simulated"
    c = client.post(f'/assistant/conversations/{cid}/ack', headers=h).json(); assert not c["needs_attention"]
    c = client.post(f'/assistant/conversations/{cid}/release', headers=h).json(); assert c["mode"] == "ai"
    n = len(c["messages"]); c = say(client, h, cid, "شكرا"); assert len(c["messages"]) == n + 2

def test_human_request_flags_handoff(client):
    h = signup(client); cid = start(client, h)["id"]
    c = say(client, h, cid, "عايز اكلم حد من المبيعات"); assert c["needs_attention"] and "موظف" in c["handoff_reason"]

def test_stop_request_opts_out_and_silences(client):
    h = signup(client); cid = start(client, h)["id"]
    c = say(client, h, cid, "وقف الرسائل متبعتليش تاني")
    assert c["lead"]["opted_out"] and c["lead"]["status"] == "not_interested" and not c["lead"]["consent"]
    n = len(c["messages"]); c = say(client, h, cid, "اهلا تاني")
    assert len(c["messages"]) == n + 1 and c["messages"][-1]["role"] == "customer"
    assert client.post(f'/assistant/conversations/{cid}/takeover', headers=h).status_code == 200
    assert client.post(f'/assistant/conversations/{cid}/human-reply', json={"body": "hi"}, headers=h).status_code == 409

def test_protected_status_not_overwritten(client):
    h = signup(client); conv = start(client, h)
    with SessionLocal() as db:
        lead = db.get(Lead, conv["lead_id"]); lead.status = "won"; db.commit()
    c = say(client, h, conv["id"], "عايز اشتري تاني"); assert c["lead"]["status"] == "won"

def test_workspace_isolation(client):
    a = signup(client); b = signup(client, email="other@example.org", company_name="Other")
    ca = start(client, a); cid = ca["id"]; say(client, a, cid, "عايز اشتري")
    assert client.get(f'/assistant/conversations/{cid}', headers=b).status_code == 404
    for path in ("messages", "takeover", "release", "ack"):
        r = client.post(f'/assistant/conversations/{cid}/{path}', json={"body": "x"}, headers=b); assert r.status_code == 404
    assert client.delete(f'/assistant/conversations/{cid}', headers=b).status_code == 404
    assert client.get('/assistant/conversations', headers=b).json() == []
    assert len(client.get('/assistant/conversations', headers=a).json()) == 1

def test_demo_leads_hidden_from_metrics_and_deletable(client):
    h = signup(client); conv = start(client, h); say(client, h, conv["id"], "عايز اشتري")
    assert client.get('/leads', headers=h).json() == []
    assert client.get('/dashboard/summary', headers=h).json()["total_leads"] == 0
    assert client.get('/dashboard/analytics', headers=h).json()["total"] == 0
    assert client.get(f'/leads/{conv["lead_id"]}', headers=h).status_code == 200
    assert client.delete(f'/assistant/conversations/{conv["id"]}', headers=h).json() == {"deleted": True}
    assert client.get(f'/leads/{conv["lead_id"]}', headers=h).status_code == 404

def test_validation(client):
    h = signup(client); cid = start(client, h)["id"]
    assert client.post(f'/assistant/conversations/{cid}/messages', json={"body": ""}, headers=h).status_code == 422
    assert client.post(f'/assistant/conversations/{cid}/messages', json={"body": "x" * 2001}, headers=h).status_code == 422
    assert client.get('/assistant/conversations').status_code == 401
    st = client.get('/assistant/status', headers=h).json(); assert st["llm"] is False and st["whatsapp_live"] is False

def test_webhook_gated_off(client, monkeypatch):
    assert client.get('/assistant/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=x&hub.challenge=1').status_code == 403
    assert client.post('/assistant/whatsapp/webhook', content=b"{}").status_code == 503
    # partially configured is still off
    monkeypatch.setattr(settings, "whatsapp_app_secret", "s"); monkeypatch.setattr(settings, "assistant_whatsapp_enabled", True)
    assert client.post('/assistant/whatsapp/webhook', content=b"{}").status_code == 503

def test_webhook_when_fully_configured_is_signed_scoped_and_never_sends(client, monkeypatch):
    h = signup(client)
    with SessionLocal() as db: org = db.scalar(select(Lead.organization_id)) or 1
    me = client.get('/auth/me', headers=h).json()
    for k, v in dict(whatsapp_app_secret="sec", whatsapp_webhook_verify_token="vt", whatsapp_phone_number_id="123", assistant_whatsapp_enabled=True, assistant_whatsapp_org_id=me["organization_id"]).items(): monkeypatch.setattr(settings, k, v)
    assert client.get('/assistant/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=vt&hub.challenge=77').text == "77"
    body = {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "123"}, "messages": [{"from": "201012345678", "id": "wamid.1", "text": {"body": "عايز اشتري دلوقتي"}}]}}]}]}
    raw = json.dumps(body).encode()
    assert client.post('/assistant/whatsapp/webhook', content=raw, headers={"x-hub-signature-256": "sha256=bad"}).status_code == 403
    sig = "sha256=" + hmac.new(b"sec", raw, hashlib.sha256).hexdigest()
    r = client.post('/assistant/whatsapp/webhook', content=raw, headers={"x-hub-signature-256": sig}); assert r.json()["handled"] == 1
    assert client.post('/assistant/whatsapp/webhook', content=raw, headers={"x-hub-signature-256": sig}).json()["handled"] == 0
    convs = client.get('/assistant/conversations', headers=h).json(); assert len(convs) == 1 and convs[0]["channel"] == "whatsapp" and convs[0]["needs_attention"]
    full = client.get(f'/assistant/conversations/{convs[0]["id"]}', headers=h).json()
    assert full["messages"][-1]["delivery"] == "suggested_not_sent" and full["lead"]["consent"] is False and full["lead"]["status"] == "hot_lead"
    # wrong phone_number_id is ignored
    body["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"] = "999"; raw = json.dumps(body).encode()
    sig = "sha256=" + hmac.new(b"sec", raw, hashlib.sha256).hexdigest()
    assert client.post('/assistant/whatsapp/webhook', content=raw, headers={"x-hub-signature-256": sig}).json()["handled"] == 0
