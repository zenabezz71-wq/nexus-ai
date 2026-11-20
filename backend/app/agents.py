from .config import settings
LABELS={"hot_lead","warm_lead","cold_lead","not_interested","follow_up","unclassified"}
def baseline(text):
    t=(text or "").lower()
    if any(x in t for x in ["stop","unsubscribe","مش مهتم","غير مهتم","لا تراسل"]):return "not_interested",.95,"Explicit rejection or stop request"
    if any(x in t for x in ["اتصل","بعدين","الأسبوع القادم","later","next week","follow up"]):return "follow_up",.84,"Requests later contact"
    if any(x in t for x in ["السعر","مهتم","تفاصيل","عايز","أريد","price","interested","demo","quote"]):return "hot_lead",.78,"Purchase or information signal"
    if text and len(text.strip())>10:return "warm_lead",.55,"Some engagement; intent is not conclusive"
    return "unclassified",.35,"Insufficient information"
async def classify(text):
    fallback=baseline(text)
    if not settings.openai_api_key:return fallback
    try:
        from openai import AsyncOpenAI
        import json
        c=AsyncOpenAI(api_key=settings.openai_api_key)
        r=await c.chat.completions.create(model=settings.openai_model,temperature=0,response_format={"type":"json_object"},messages=[
          {"role":"system","content":"Classify lead intent. JSON: status, confidence, reason. Allowed statuses: hot_lead,warm_lead,cold_lead,not_interested,follow_up,unclassified. Never infer consent. Respect opt-outs."},
          {"role":"user","content":text[:5000]}])
        d=json.loads(r.choices[0].message.content or "{}"); label=d.get("status")
        if label not in LABELS:return fallback
        return label,max(0,min(1,float(d.get("confidence",.5)))),str(d.get("reason","AI classification"))[:500]
    except Exception:return fallback
class AgentOrchestrator:
    def __init__(self):self.tools={}
    def register(self,name,handler):self.tools[name]=handler
    async def execute(self,name,**kwargs):
        if name not in self.tools:raise ValueError("Tool is not registered")
        return await self.tools[name](**kwargs)
orchestrator=AgentOrchestrator()
