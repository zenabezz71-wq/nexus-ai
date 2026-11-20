import re,phonenumbers
ALIASES={"name":["name","full name","الاسم"],"phone":["phone","mobile","phone number","رقم الهاتف","الموبايل","رقم التليفون"],"email":["email","e-mail","البريد الإلكتروني","الايميل"],"currency":["currency","العملة","العمله"],"amount":["amount","value","المبلغ","القيمة"],"goal":["goal","purpose","contact goal","هدف التواصل","الغرض"],"message":["message","contact message","رسالة التواصل","الرسالة"],"consent":["consent","opt in","permission","موافقة التواصل","موافقة"]}
def normalize_headers(cols):
    out={}
    for c in cols:
        k=str(c).strip().lower()
        for canonical,aliases in ALIASES.items():
            if k==canonical or k in [a.lower() for a in aliases]: out[c]=canonical;break
    return out
def normalize_phone(raw):
    raw=str(raw or "").strip()
    if not raw:return "",False
    try:
        n=phonenumbers.parse(raw,"EG")
        if phonenumbers.is_valid_number(n):return phonenumbers.format_number(n,phonenumbers.PhoneNumberFormat.E164),True
    except Exception: pass
    return re.sub(r"\D","",raw),False
def parse_bool(v): return str(v or "").strip().lower() in {"true","1","yes","y","نعم","موافق","موافقة"}
