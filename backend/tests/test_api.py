def test_health(client):assert client.get("/health").json()["ok"] is True
def test_summary_requires_auth(client):assert client.get("/dashboard/summary").status_code==401
def test_webhook_and_lead_list(client,token):
    h={"Authorization":f"Bearer {token}"}
    r=client.post("/webhooks/meta-lead-ads",headers=h,json={"external_id":"abc","name":"Mona","phone":"+201001112233","consent":False})
    assert r.status_code==200 and r.json()["result"]=="created" and r.json()["consent"] is False
    assert client.get("/leads",headers=h).json()[0]["name"]=="Mona"
def test_unauthenticated_webhook_rejected(client):
    assert client.post("/webhooks/ads",json={"phone":"+201001112233"}).status_code==401
