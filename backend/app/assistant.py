"""AI auto-reply sales assistant (Arabic / Egyptian dialect).

Honest scope of this release:
- The engine is a rule/template based Arabic engine. It does not call any LLM or paid service.
- Replies are produced and stored. Nothing is ever sent to a real customer: the official
  WhatsApp Cloud API webhook is OFF until real Meta credentials and an explicit workspace
  mapping exist, and even then this release only records suggested replies for a salesperson.
- Everything is scoped to the caller's workspace. Opt-out / do-not-contact rules are enforced.
"""
import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, delete, func, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, Session
from .config import settings
from .database import Base, get_db
from .models import Lead, Membership, User, AuditLog, Organization, now
from .auth import current_membership
from .crm import SalesFeedback, LeadSales, detail as lead_detail
from .whatsapp import phone as wa_phone, WhatsAppSuppression
from .outreach import OutreachSuppression, address

router = APIRouter()
DEMO_SOURCE = "assistant_demo"
PROTECTED = {"won", "lost", "contacted", "qualified", "invalid_number"}
MAX_MESSAGE = 2000
MAX_MESSAGES_PER_CONVERSATION = 200
MAX_DEMO_CONVERSATIONS = 50


class Conversation(Base):
    __tablename__ = "assistant_conversations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    channel: Mapped[str] = mapped_column(String(20), default="simulation")
    mode: Mapped[str] = mapped_column(String(10), default="ai")
    needs_attention: Mapped[bool] = mapped_column(Boolean, default=False)
    handoff_reason: Mapped[str] = mapped_column(String(300), default="")
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ConvMessage(Base):
    __tablename__ = "assistant_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("assistant_conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(12))
    body: Mapped[str] = mapped_column(Text)
    delivery: Mapped[str] = mapped_column(String(30), default="simulated")
    provider_message_id: Mapped[str] = mapped_column(String(200), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


# ---------------------------------------------------------------- Arabic NLU
_DIACRITICS = re.compile("[\u064b-\u065f\u0670\u0640]")
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def norm(text):
    t = (text or "").lower().translate(_AR_DIGITS)
    t = _DIACRITICS.sub("", t)
    t = re.sub("[أإآٱ]", "ا", t).replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    t = t.replace("عاوز", "عايز").replace("ايوة", "ايوه")
    t = re.sub(r"[^\w$.\s]", " ", t)
    return " " + re.sub(r"\s+", " ", t).strip() + " "


def has(t, words):
    for w in words:
        w = norm(w)
        if w in t: return True
        core = w.strip()
        if " " not in core and re.search(r"(?<=\s)[وبلفك]" + re.escape(core) + r"(?=\s)", t): return True
    return False


STOP = ["وقف", "وقفوا", "كفايه رسايل", "متبعتليش", "ماتبعتليش", "متكلمنيش", "ماتكلمنيش", "الغي الاشتراك", "الغاء الاشتراك", "شيلني من", "لا تراسلني", "لا تتواصل", "stop", "unsubscribe", "توقف عن"]
HUMAN = ["اكلم حد", "كلم حد", "حد يكلمني", "عايز موظف", "موظف", "مسؤول", "مدير", "شخص حقيقي", "بني ادم", "خدمه العملاء", "ممثل", "human", "representative", "اتصل بيا", "اتصلوا بيا", "كلموني", "كلمني تليفون"]
NOT_INTERESTED = ["مش مهتم", "مش مهتمه", "غير مهتم", "مش عايز", "مش محتاج", "مش محتاجه", "لا شكرا", "ما بدي", "not interested"]
BUY = ["عايز اشتري", "عايز اشترك", "عايز اطلب", "عايز احجز", "اشتري", "اشترك", "احجز", "هشتري", "هشترك", "هحجز", "هدفع", "ادفع", "جاهز", "نبدا", "خلينا نبدا", "اتفقنا", "اقفل", "ابعتلي العقد", "عايز ابدا", "i want to buy", "ready to buy"]
LATER = ["بعدين", "مش دلوقتي", "الاسبوع الجاي", "الشهر الجاي", "كلمني بعد", "فكرني", "لما ارجع"]
PRICE = ["سعر", "اسعار", "بكام", "بكم", "تكلفه", "تكلفة", "باقه", "باقات", "كام", "price", "cost", "pricing"]
DETAILS = ["تفاصيل", "مميزات", "بتعملوا", "بتقدموا", "بتعمل ايه", "خدمات", "ازاي", "عايز اعرف", "استفسار", "ايه هو", "details"]
GREETING = ["السلام عليكم", "سلام عليكم", "اهلا", "مرحبا", "هاي", "صباح", "مساء", "ازيك", "hello", "hi"]
THANKS = ["شكرا", "تسلم", "ميرسي", "thanks", "thank you"]
SOON = ["دلوقتي", "النهارده", "النهاردة", "فورا", "حالا", "بكره", "بكرة", "في اسرع وقت", "اسرع وقت", "الاسبوع ده", "الاسبوع دا", "مستعجل", "ضروري"]
MID = ["الاسبوع الجاي", "اسبوعين", "الشهر ده", "الشهر دا", "خلال شهر", "قريب"]
LATE = ["الشهر الجاي", "شهرين", "تلات شهور", "بعد شهر", "السنه الجايه", "مش مستعجل", "لسه بدري"]
CURRENCIES = [("EGP", ["جنيه", "جنيها", "جنية", "egp", "ج.م"]), ("USD", ["دولار", "usd", "$"]), ("SAR", ["ريال", "sar"]), ("AED", ["درهم", "aed"])]
QUESTIONS = {
    "goal": ["ممكن تقولي بالظبط محتاج إيه أو عايز تحقق إيه؟", "إيه اللي بتدور عليه بالتحديد عشان أرشحلك الأنسب؟"],
    "budget": ["تقريباً ميزانيتك كام عشان أرشحلك الأنسب؟", "عندك ميزانية تقريبية في دماغك؟"],
    "timeline": ["إمتى حابب تبدأ؟ قريب ولا لسه بتقارن؟", "محتاج الموضوع ده يبدأ في أنهي وقت؟"],
    "name": ["وأقدر أناديك بإيه؟", "ممكن أعرف اسم حضرتك؟"],
}
ORDER = ["goal", "budget", "timeline", "name"]


def _pick(options, seed):
    return options[int(hashlib.md5(str(seed).encode()).hexdigest(), 16) % len(options)]


def extract_budget(t, last_asked):
    m = re.search(r"(\d+(?:\.\d+)?)\s*(الف|ألف|الاف|k)?", t)
    cur = next((c for c, ws in CURRENCIES if any(w in t for w in ws)), "")
    if m and (cur or last_asked == "budget"):
        value = float(m.group(1)) * (1000 if m.group(2) else 1)
        if 0 < value < 1e12: return value, cur or "EGP"
    if has(t, ["الفين"]): return 2000.0, cur or "EGP"
    return None, ""


def extract_timeline(t, last_asked):
    if has(t, SOON): return "soon"
    if has(t, LATE): return "later"
    if has(t, MID): return "mid"
    if last_asked == "timeline" and len(t.strip()) > 1 and not has(t, ["مش عارف", "معرفش"]): return "mid"
    return ""


def extract_name(text, last_asked):
    m = re.search(r"(?:اسمي|انا اسمي|أنا اسمي|معاك|معاكم|انا)\s+([\u0600-\u06FFA-Za-z]{2,20})", text or "")
    if m and m.group(1) not in ("عايز", "عاوز", "مهتم", "محتاج", "مش", "بدور", "عايزه", "مهتمه", "محتاجه", "جاهز", "عندي", "كنت", "هدفع", "لسه", "بس", "في", "من", "عاوزه"): return m.group(1)
    if last_asked == "name":
        words = re.findall(r"[\u0600-\u06FFA-Za-z]{2,20}", text or "")
        if 0 < len(words) <= 3: return words[0]
    return ""


def analyse(text, state):
    """Return (intents, new_slot_values) for one customer message."""
    t = norm(text)
    asked = state.get("last_asked", "")
    intents = []
    if has(t, STOP): intents.append("stop")
    if has(t, NOT_INTERESTED): intents.append("not_interested")
    if has(t, HUMAN): intents.append("human")
    if "not_interested" not in intents and has(t, BUY) and not has(t, ["مش جاهز", "مش هشتري", "مش هاشتري", "لسه مش جاهز"]): intents.append("buy")
    if has(t, LATER): intents.append("later")
    if has(t, PRICE): intents.append("price")
    if has(t, DETAILS): intents.append("details")
    if has(t, THANKS): intents.append("thanks")
    greeting_only = has(t, GREETING) and len(t.split()) <= 4
    if greeting_only: intents.append("greeting")
    slots = {}
    budget, cur = extract_budget(t, asked)
    if budget is not None: slots["budget"], slots["currency"] = budget, cur
    tl = extract_timeline(t, asked)
    if tl: slots["timeline"] = tl
    nm = extract_name(text, asked)
    if nm: slots["name"] = nm
    substantive = len(t.split()) >= 3 and not greeting_only and not ({"stop", "not_interested", "thanks", "price", "details", "human", "buy", "later"} & set(intents))
    if substantive and not state.get("goal") and not (asked in ("budget", "timeline") and slots):
        slots["goal"] = (text or "").strip()[:300]
    return intents, slots


def score_of(state, intents):
    s = 0.0
    if state.get("goal"): s += 1
    if state.get("budget") is not None: s += 1
    s += {"soon": 2, "mid": 1}.get(state.get("timeline", ""), 0)
    if "price" in intents or state.get("asked_price"): s += 1
    if "details" in intents: s += .5
    if "buy" in intents: s += 3
    return s


def compose(org_name, lead_name, state, intents, seed, status_after, slots):
    parts = []
    first = not state.get("greeted")
    if "stop" in intents:
        return "تمام، تم إيقاف الرسائل ومش هنتواصل معاك تاني. شكراً لوقتك 🙏"
    if "not_interested" in intents:
        return "تمام جداً، شكراً على صراحتك 🙏 لو احتجت أي حاجة في أي وقت إحنا موجودين."
    if first or "greeting" in intents:
        parts.append(f"أهلاً بيك في {org_name} 👋" if first else "أهلاً بيك 👋")
    if "human" in intents:
        parts.append("طبعاً، هبلغ حد من فريق المبيعات يكلمك في أقرب وقت. ولو تحب تكتبلي الأول إيه اللي محتاجه عشان نوفر وقتك.")
    elif "buy" in intents:
        parts.append("جميل جداً، ده قرار ممتاز! هنقل طلبك فوراً لحد من فريق المبيعات يكمل معاك خطوات البدء والتفاصيل النهائية.")
    elif "later" in intents:
        parts.append("ولا يهمك، هنرجعلك في الوقت اللي يناسبك. قولي بس امتى تحب نتواصل؟" if not state.get("timeline") else "ولا يهمك، هنرجعلك في الوقت اللي يناسبك 🙏")
    elif "price" in intents:
        parts.append("الأسعار بتختلف حسب احتياجك بالظبط، ومش عايز أديك رقم مش مناسب. ممثل المبيعات هيبعتلك عرض سعر واضح.")
    elif "details" in intents:
        parts.append("بكل سرور أشرحلك. فريقنا هيبعتلك التفاصيل الكاملة، وأنا هجهز الأول فهم سريع لاحتياجك.")
    elif "thanks" in intents:
        parts.append("العفو، في خدمتك دايماً 🙏")
    elif not parts or (len(parts) == 1 and "greeting" not in intents and not first):
        got = [k for k in ("budget", "timeline", "goal", "name") if k in slots]
        acks = {"budget": "تمام، سجلت الميزانية 👍", "timeline": "ممتاز، سجلت التوقيت 👍", "goal": "فهمت احتياجك، شكراً على التوضيح 👍", "name": "تشرفت بيك يا " + str(state.get("name", "")) + " 😊"}
        parts.append(acks[got[0]] if got else "تمام، سجلت كلامك 👍")
    asked = state.setdefault("asked_count", {})
    nxt = next((k for k in ORDER if not state.get(k) and state.get(k) != 0 and asked.get(k, 0) < 2), None)
    if status_after == "hot_lead" or "buy" in intents: nxt = None
    if nxt:
        state["last_asked"] = nxt
        asked[nxt] = asked.get(nxt, 0) + 1
        parts.append(_pick(QUESTIONS[nxt], seed + nxt))
    else:
        state["last_asked"] = ""
        if status_after == "hot_lead" and "buy" not in intents and "human" not in intents:
            parts.append("وأنا بلغت مندوب المبيعات، هيتواصل معاك في أقرب وقت 🙌")
        elif "buy" not in intents and "human" not in intents and "thanks" not in intents:
            parts.append("شكراً على المعلومات، هنراجعها ونرجعلك بالتفاصيل 🙌")
    return " ".join(parts)


def run_engine(db, org, lead, conv, text, user_id):
    """Apply one customer message. Returns the assistant reply text or None."""
    state = dict(conv.state or {})
    intents, slots = analyse(text, state)
    if "price" in intents: state["asked_price"] = True
    for k, v in slots.items():
        if k == "goal" and state.get("goal"): continue
        state[k] = v
    state["intents"] = sorted(set(state.get("intents", [])) | set(intents))
    score = score_of(state, intents)
    state["score"] = score
    old_status, new_status, reason, confidence = lead.status, lead.status, "", lead.confidence

    if "stop" in intents or lead.opted_out:
        if "stop" in intents and not lead.opted_out:
            lead.opted_out, lead.consent = True, False
            email = address(lead.email)
            if email and not db.get(OutreachSuppression, (lead.organization_id, email)): db.add(OutreachSuppression(organization_id=lead.organization_id, recipient=email))
            number = wa_phone(lead.phone)
            if number and not org.trial_only and not db.get(WhatsAppSuppression, number): db.add(WhatsAppSuppression(recipient=number))
        if old_status not in PROTECTED or "stop" in intents:
            new_status, reason, confidence = "not_interested", "AI assistant: customer asked to stop contact", .97
    elif old_status not in PROTECTED:
        if "not_interested" in intents: new_status, reason, confidence = "not_interested", "AI assistant: customer said they are not interested", .9
        elif "buy" in intents or (score >= 3 and state.get("timeline") in ("soon", "mid")): new_status, reason, confidence = "hot_lead", "AI assistant: clear buying signal" if "buy" in intents else f"AI assistant: qualified and urgent (score {score:g})", .9 if "buy" in intents else .8
        elif "later" in intents and old_status != "hot_lead": new_status, reason, confidence = "follow_up", "AI assistant: customer asked to be contacted later", .85
        elif score >= 1.5 and old_status in ("unclassified", "cold_lead", "follow_up"): new_status, reason, confidence = "warm_lead", f"AI assistant: engaged and partly qualified (score {score:g})", .65
        elif old_status == "unclassified" and score >= 1: new_status, reason, confidence = "warm_lead", "AI assistant: customer engaged", .5
    # update the lead record (CRM)
    if state.get("goal") and not lead.goal: lead.goal = state["goal"]
    if state.get("budget") is not None and lead.amount is None: lead.amount, lead.currency = state["budget"], state.get("currency", "")
    if state.get("name") and (not lead.name or "تجريبي" in lead.name and lead.name.startswith("عميل")):
        lead.name = state["name"] + (" (تجريبي)" if lead.source == DEMO_SOURCE else "")
    notes = []
    if new_status != old_status:
        lead.status, lead.confidence, lead.classification_reason = new_status, confidence, reason
        notes.append(f"🤖 المساعد الآلي غيّر التصنيف من {old_status} إلى {new_status}. السبب: {reason}")
    handoff = ""
    if "human" in intents: handoff = "العميل طلب التحدث مع موظف"
    elif new_status == "hot_lead" and old_status != "hot_lead": handoff = "عميل ساخن: " + reason.replace("AI assistant: ", "")
    if "stop" in intents: notes.append("🚫 العميل طلب إيقاف التواصل. تم تسجيل عدم التواصل وإيقاف الرد الآلي.")
    if handoff and not conv.needs_attention:
        conv.needs_attention, conv.handoff_reason = True, handoff
        summary = f"🔥 تنبيه تسليم لفريق المبيعات: {handoff}."
        if state.get("goal"): summary += f" الاحتياج: {state['goal'][:120]}."
        if state.get("budget") is not None: summary += f" الميزانية: {state['budget']:g} {state.get('currency', '')}."
        if state.get("timeline"): summary += " التوقيت: " + {"soon": "قريب جداً", "mid": "متوسط", "later": "بعيد"}[state["timeline"]] + "."
        notes.append(summary)
        db.add(AuditLog(organization_id=org.id, actor_user_id=user_id, action="assistant.handoff", details={"lead_id": lead.id, "conversation_id": conv.id, "reason": handoff}))
    for n in notes: db.add(SalesFeedback(organization_id=org.id, lead_id=lead.id, author_user_id=user_id, body=n))
    lead.updated_at = now()
    # decide on a reply
    reply = None
    if lead.opted_out and "stop" not in intents: reply = None
    elif conv.mode == "human": reply = None
    else:
        seed = f"{conv.id}:{len(state.get('intents', []))}:{state.get('score')}:{text}"
        reply = compose(org.name, lead.name, state, intents, seed, lead.status, slots)
        state["greeted"] = True
    conv.state = state
    conv.updated_at = now()
    return reply


# ----------------------------------------------------------------- helpers
def stamp(v): return v.isoformat() if v else None


def own_conversation(db, ident, org):
    conv = db.scalar(select(Conversation).where(Conversation.id == ident, Conversation.organization_id == org))
    if not conv: raise HTTPException(404, "Conversation not found in workspace")
    return conv


def conversation_view(db, conv, full=True):
    lead = db.get(Lead, conv.lead_id)
    msgs = db.scalars(select(ConvMessage).where(ConvMessage.conversation_id == conv.id, ConvMessage.organization_id == conv.organization_id).order_by(ConvMessage.id)).all()
    st = conv.state or {}
    out = {"id": conv.id, "channel": conv.channel, "mode": conv.mode, "needs_attention": conv.needs_attention, "handoff_reason": conv.handoff_reason,
           "updated_at": stamp(conv.updated_at), "lead_id": lead.id, "lead_name": lead.name, "lead_status": lead.status,
           "last_message": msgs[-1].body[:120] if msgs else "", "message_count": len(msgs)}
    if full:
        out["messages"] = [{"id": m.id, "role": m.role, "body": m.body, "delivery": m.delivery, "created_at": stamp(m.created_at)} for m in msgs]
        out["lead"] = lead_detail(db, lead) | {"confidence": lead.confidence, "reason": lead.classification_reason}
        out["qualification"] = {"goal": st.get("goal", ""), "budget": st.get("budget"), "currency": st.get("currency", ""), "timeline": st.get("timeline", ""), "name": st.get("name", ""), "score": st.get("score", 0), "intents": st.get("intents", [])}
        out["engine"] = "rule_based_arabic"
    return out


def owner_user_id(db, org):
    return db.scalar(select(Membership.user_id).join(User, User.id == Membership.user_id).where(Membership.organization_id == org, Membership.is_active == True, User.is_active == True).order_by(Membership.role != "owner", Membership.id))


def deliver_inbound(db, org, conv, text, user_id, provider_id=""):
    """Store a customer message, run the engine, store the reply. Nothing is sent externally."""
    if db.scalar(select(func.count(ConvMessage.id)).where(ConvMessage.conversation_id == conv.id)) >= MAX_MESSAGES_PER_CONVERSATION:
        raise HTTPException(429, "This conversation reached its message limit")
    lead = db.get(Lead, conv.lead_id)
    db.add(ConvMessage(organization_id=org.id, conversation_id=conv.id, role="customer", body=text, delivery="received", provider_message_id=provider_id))
    if conv.mode == "human" and not conv.needs_attention:
        conv.needs_attention, conv.handoff_reason = True, "العميل رد على محادثة مستلمة يدوياً"
    reply = run_engine(db, org, lead, conv, text, user_id)
    if reply:
        delivery = "simulated" if conv.channel == "simulation" else "suggested_not_sent"
        db.add(ConvMessage(organization_id=org.id, conversation_id=conv.id, role="assistant", body=reply, delivery=delivery))
    db.add(AuditLog(organization_id=org.id, actor_user_id=user_id, action="assistant.message", details={"conversation_id": conv.id, "lead_id": lead.id, "replied": bool(reply), "channel": conv.channel}))


class StartInput(BaseModel):
    customer_name: str = Field(default="", max_length=60)


class MessageInput(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_MESSAGE)


# --------------------------------------------------------------- endpoints
def whatsapp_blockers():
    missing = []
    if not settings.assistant_whatsapp_enabled: missing.append("Assistant WhatsApp webhook is disabled")
    if not settings.whatsapp_app_secret: missing.append("Meta app secret is not configured")
    if not settings.whatsapp_webhook_verify_token: missing.append("Webhook verify token is not configured")
    if not settings.whatsapp_phone_number_id: missing.append("WhatsApp phone number ID is not configured")
    if settings.assistant_whatsapp_org_id <= 0: missing.append("No workspace is mapped to the WhatsApp number")
    return missing


@router.get("/assistant/status")
def assistant_status(ctx=Depends(current_membership)):
    return {"engine": "rule_based_arabic", "llm": False, "demo_mode": True,
            "note": "Rule and template based Arabic assistant. No AI model or paid service is called. Demo replies are never sent to anyone.",
            "whatsapp_live": False, "whatsapp_blockers": whatsapp_blockers() + ["Automatic WhatsApp replies are not implemented in this release; live messages would only be recorded as suggested replies"]}


@router.get("/assistant/conversations")
def list_conversations(ctx=Depends(current_membership), db: Session=Depends(get_db)):
    rows = db.scalars(select(Conversation).where(Conversation.organization_id == ctx["organization_id"]).order_by(Conversation.needs_attention.desc(), Conversation.updated_at.desc()).limit(50)).all()
    return [conversation_view(db, c, full=False) for c in rows]


@router.post("/assistant/simulations", status_code=201)
def start_simulation(data: StartInput, ctx=Depends(current_membership), db: Session=Depends(get_db)):
    org = ctx["organization_id"]
    if (db.scalar(select(func.count(Lead.id)).where(Lead.organization_id == org, Lead.source == DEMO_SOURCE)) or 0) >= MAX_DEMO_CONVERSATIONS:
        raise HTTPException(429, "Too many demo conversations. Delete some first.")
    name = re.sub(r"\s+", " ", data.customer_name).strip() or "عميل"
    for _ in range(5):
        number = "+20199" + "".join(str(secrets.randbelow(10)) for _ in range(7))
        if not db.scalar(select(Lead.id).where(Lead.organization_id == org, Lead.phone == number)): break
    lead = Lead(organization_id=org, name=name + " (تجريبي)", phone=number, source=DEMO_SOURCE, status="unclassified", consent=False)
    db.add(lead); db.flush()
    conv = Conversation(organization_id=org, lead_id=lead.id, channel="simulation", state={})
    db.add(conv); db.flush()
    db.add(AuditLog(organization_id=org, actor_user_id=ctx["user"].id, action="assistant.simulation_started", details={"conversation_id": conv.id, "lead_id": lead.id}))
    db.commit()
    return conversation_view(db, conv)


@router.get("/assistant/conversations/{conv_id}")
def get_conversation(conv_id: int, ctx=Depends(current_membership), db: Session=Depends(get_db)):
    return conversation_view(db, own_conversation(db, conv_id, ctx["organization_id"]))


@router.post("/assistant/conversations/{conv_id}/messages")
def simulate_customer_message(conv_id: int, data: MessageInput, ctx=Depends(current_membership), db: Session=Depends(get_db)):
    conv = own_conversation(db, conv_id, ctx["organization_id"])
    if conv.channel != "simulation": raise HTTPException(400, "Only demo conversations accept simulated customer messages")
    text = data.body.strip()
    if not text: raise HTTPException(400, "Message cannot be blank")
    org = db.get(Organization, ctx["organization_id"])
    deliver_inbound(db, org, conv, text, ctx["user"].id)
    db.commit()
    return conversation_view(db, conv)


@router.post("/assistant/conversations/{conv_id}/takeover")
def takeover(conv_id: int, ctx=Depends(current_membership), db: Session=Depends(get_db)):
    conv = own_conversation(db, conv_id, ctx["organization_id"])
    conv.mode, conv.needs_attention, conv.updated_at = "human", False, now()
    db.add(SalesFeedback(organization_id=conv.organization_id, lead_id=conv.lead_id, author_user_id=ctx["user"].id, body="👤 مندوب المبيعات استلم المحادثة. الرد الآلي متوقف."))
    db.add(AuditLog(organization_id=conv.organization_id, actor_user_id=ctx["user"].id, action="assistant.takeover", details={"conversation_id": conv.id}))
    lead = db.get(Lead, conv.lead_id); lead.updated_at = now()
    db.commit()
    return conversation_view(db, conv)


@router.post("/assistant/conversations/{conv_id}/release")
def release(conv_id: int, ctx=Depends(current_membership), db: Session=Depends(get_db)):
    conv = own_conversation(db, conv_id, ctx["organization_id"])
    conv.mode, conv.updated_at = "ai", now()
    db.add(AuditLog(organization_id=conv.organization_id, actor_user_id=ctx["user"].id, action="assistant.release", details={"conversation_id": conv.id}))
    db.commit()
    return conversation_view(db, conv)


@router.post("/assistant/conversations/{conv_id}/ack")
def acknowledge(conv_id: int, ctx=Depends(current_membership), db: Session=Depends(get_db)):
    conv = own_conversation(db, conv_id, ctx["organization_id"])
    conv.needs_attention, conv.updated_at = False, now()
    db.add(AuditLog(organization_id=conv.organization_id, actor_user_id=ctx["user"].id, action="assistant.alert_acknowledged", details={"conversation_id": conv.id}))
    db.commit()
    return conversation_view(db, conv)


@router.post("/assistant/conversations/{conv_id}/human-reply")
def human_reply(conv_id: int, data: MessageInput, ctx=Depends(current_membership), db: Session=Depends(get_db)):
    conv = own_conversation(db, conv_id, ctx["organization_id"])
    if conv.mode != "human": raise HTTPException(409, "Take over the conversation before replying as a human")
    lead = db.get(Lead, conv.lead_id)
    if lead.opted_out: raise HTTPException(409, "This contact opted out of communication")
    delivery = "simulated" if conv.channel == "simulation" else "not_sent_whatsapp_gated"
    db.add(ConvMessage(organization_id=conv.organization_id, conversation_id=conv.id, role="human", body=data.body.strip(), delivery=delivery))
    conv.updated_at = now()
    db.commit()
    return conversation_view(db, conv)


@router.delete("/assistant/conversations/{conv_id}")
def delete_demo(conv_id: int, ctx=Depends(current_membership), db: Session=Depends(get_db)):
    conv = own_conversation(db, conv_id, ctx["organization_id"])
    lead = db.get(Lead, conv.lead_id)
    if conv.channel != "simulation" or lead.source != DEMO_SOURCE: raise HTTPException(400, "Only demo conversations can be deleted")
    db.execute(delete(ConvMessage).where(ConvMessage.conversation_id == conv.id))
    db.execute(delete(Conversation).where(Conversation.id == conv.id))
    db.execute(delete(SalesFeedback).where(SalesFeedback.lead_id == lead.id))
    db.execute(delete(LeadSales).where(LeadSales.lead_id == lead.id))
    db.execute(delete(Lead).where(Lead.id == lead.id, Lead.organization_id == ctx["organization_id"]))
    db.commit()
    return {"deleted": True}


# ---------------------------------------------- WhatsApp Cloud API (gated OFF)
@router.get("/assistant/whatsapp/webhook", response_class=PlainTextResponse)
def assistant_verify(request: Request):
    q = request.query_params
    if not whatsapp_blockers() and q.get("hub.mode") == "subscribe" and hmac.compare_digest(q.get("hub.verify_token", ""), settings.whatsapp_webhook_verify_token):
        return q.get("hub.challenge", "")
    raise HTTPException(403, "Verification failed")


@router.post("/assistant/whatsapp/webhook")
async def assistant_webhook(request: Request, db: Session=Depends(get_db)):
    if whatsapp_blockers(): raise HTTPException(503, "Assistant WhatsApp webhook is not enabled")
    raw = await request.body()
    if len(raw) > 1000000: raise HTTPException(413, "Payload too large")
    expected = "sha256=" + hmac.new(settings.whatsapp_app_secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(request.headers.get("x-hub-signature-256", ""), expected): raise HTTPException(403, "Invalid signature")
    try: payload = json.loads(raw)
    except ValueError: raise HTTPException(400, "Invalid JSON")
    org = db.get(Organization, settings.assistant_whatsapp_org_id)
    user_id = owner_user_id(db, org.id) if org else None
    if not org or not user_id: raise HTTPException(503, "Mapped workspace is unavailable")
    from .rls import org_context
    org_context(db, org.id)
    handled = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            if str(value.get("metadata", {}).get("phone_number_id", "")) != settings.whatsapp_phone_number_id: continue
            for msg in value.get("messages", []):
                text = str(msg.get("text", {}).get("body", "")).strip()[:MAX_MESSAGE]
                number = "+" + re.sub(r"\D", "", str(msg.get("from", "")))
                wamid = str(msg.get("id", ""))[:200]
                if not text or not wa_phone(number): continue
                if wamid and db.scalar(select(ConvMessage.id).where(ConvMessage.organization_id == org.id, ConvMessage.provider_message_id == wamid)): continue
                lead = db.scalar(select(Lead).where(Lead.organization_id == org.id, Lead.phone == number))
                if not lead:
                    lead = Lead(organization_id=org.id, phone=number, name=str(next((c.get("profile", {}).get("name", "") for c in value.get("contacts", [])), ""))[:200], source="whatsapp_inbound", status="unclassified", consent=False)
                    db.add(lead); db.flush()
                conv = db.scalar(select(Conversation).where(Conversation.organization_id == org.id, Conversation.lead_id == lead.id, Conversation.channel == "whatsapp"))
                if not conv:
                    conv = Conversation(organization_id=org.id, lead_id=lead.id, channel="whatsapp", state={}); db.add(conv); db.flush()
                deliver_inbound(db, org, conv, text, user_id, wamid)
                handled += 1
    db.commit()
    return {"ok": True, "handled": handled}
