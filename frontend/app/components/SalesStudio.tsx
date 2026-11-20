"use client";
import {useState} from "react";
// SALES_STUDIO_LOGIC_START
type SalesFacts={product:string;price:string;delivery:string;policy:string};
type SalesScenario="price"|"expensive"|"delivery"|"later"|"confirm"|"stop";
function salesReply(f:SalesFacts,scenario:SalesScenario,formal:boolean){
 const product=f.product.trim()||"المنتج";
 const price=f.price.trim();const delivery=f.delivery.trim();const policy=f.policy.trim();
 const facts:string[]=[];const missing:string[]=[];
 if(f.product.trim())facts.push("اسم المنتج");
 const usePrice=()=>{if(price){facts.push("السعر");return formal?`السعر: ${price}.`:`السعر ${price}.`}missing.push("السعر");return formal?"السعر يحتاج إلى تأكيد من مسؤول المبيعات.":"هنتأكد من السعر مع مسؤول المبيعات الأول."};
 const useDelivery=()=>{if(delivery){facts.push("التوصيل");return `تفاصيل التوصيل: ${delivery}.`}missing.push("التوصيل");return formal?"ما منطقة التوصيل المطلوبة؟ نحتاج إلى تأكيد التكلفة والموعد.":"التوصيل لأنهي منطقة؟ محتاجين نأكد التكلفة والميعاد الأول."};
 const usePolicy=()=>{if(policy){facts.push("السياسة / الميزة");return policy+"."}missing.push("سياسة أو ميزة مؤكدة");return ""};
 let text="";
 if(scenario==="price")text=formal?`أهلاً بك! بخصوص ${product}، ${usePrice()} ما الذي تود معرفته قبل اتخاذ قرارك؟`:`أهلاً بيك! بالنسبة لـ${product}، ${usePrice()} تحب تعرف إيه عنه قبل ما تقرر؟`;
 if(scenario==="expensive")text=formal?`أتفهم أهمية الميزانية. بخصوص ${product}، ${usePrice()} ${usePolicy()} ما الميزانية المناسبة لك؟ لن نؤكد خصماً أو عرضاً دون مراجعة.`:`فاهم إن الميزانية مهمة. بالنسبة لـ${product}، ${usePrice()} ${usePolicy()} إيه الميزانية المناسبة ليك؟ مش هنأكد خصم أو عرض من غير مراجعة.`;
 if(scenario==="delivery")text=`${formal?"أهلاً بك!":"أهلاً بيك!"} ${useDelivery()}`;
 if(scenario==="later")text=formal?`بالتأكيد، خذ وقتك في التفكير بشأن ${product}. هل ترغب في أن نتابع معك لاحقاً؟ وإذا وافقت، فما الموعد المناسب؟`:`أكيد، خد وقتك في التفكير في ${product}. تحب نتابع معاك بعدين؟ ولو موافق، أنهي وقت يناسبك؟`;
 if(scenario==="confirm")text=formal?`نراجع تفاصيل ${product} قبل تأكيد أي طلب: ${usePrice()} ${useDelivery()} ${usePolicy()} هل هذه التفاصيل مناسبة لك؟ هذه مراجعة فقط وليست تأكيداً للطلب.`:`نراجع تفاصيل ${product} قبل ما نأكد أي طلب: ${usePrice()} ${useDelivery()} ${usePolicy()} التفاصيل دي مناسبة ليك؟ دي مراجعة بس، مش تأكيد للطلب.`;
 if(scenario==="stop")text=formal?"نحترم رغبتك في عدم تلقي رسائل أخرى. شكراً لإبلاغنا.":"بنحترم رغبتك إنك ما تستقبلش رسائل تانية. شكراً إنك بلغتنا.";
 return {text:text.replace(/ +/g," "),facts:[...new Set(facts)],missing:[...new Set(missing)]};
}
// SALES_STUDIO_LOGIC_END
export default function SalesStudio(){
 const [facts,setFacts]=useState<SalesFacts>({product:"",price:"",delivery:"",policy:""});
 const [scenario,setScenario]=useState<SalesScenario>("price");const [formal,setFormal]=useState(false);const [demo,setDemo]=useState(false);
 const [result,setResult]=useState<ReturnType<typeof salesReply>|null>(null);const [draft,setDraft]=useState("");const [notice,setNotice]=useState("");
 function invalidate(){setResult(null);setDraft("");setNotice("")}
 function sample(){setFacts({product:"شنطة قماش (مثال تجريبي)",price:"٣٥٠ جنيه مصري",delivery:"داخل القاهرة: ٥٠ جنيه، خلال ٣ أيام عمل",policy:"يمكن معاينة الشنطة عند الاستلام وفق سياسة المتجر التجريبي"});setDemo(true);invalidate()}
 function reset(){setFacts({product:"",price:"",delivery:"",policy:""});setDemo(false);invalidate()}
 async function copy(){try{await navigator.clipboard.writeText(draft);setNotice("تم نسخ المسودة. راجعها قبل أي إرسال.")}catch{setNotice("النسخ التلقائي غير متاح. حدّد النص وانسخه يدوياً.")}}
 const field=(key:keyof SalesFacts,label:string,placeholder:string)=><label style={{display:"flex",flexDirection:"column",gap:8,fontSize:14}} key={key}>{label}<input style={{width:"100%",minWidth:0}} maxLength={key==="product"?100:300} value={facts[key]} placeholder={placeholder} onChange={e=>{setFacts({...facts,[key]:e.target.value});invalidate()}}/></label>;
 return <section id="sales-studio" className="panel" dir="rtl" lang="ar" style={{scrollMarginTop:20,padding:24}}>
  <span className="eyebrow" dir="ltr">EGYPTIAN SALES REPLY STUDIO</span><h2 style={{fontSize:26,marginBottom:8}}>من اعتراض العميل لرد جاهز للمراجعة</h2>
  <p style={{lineHeight:1.9,color:"#536487",maxWidth:780}}>اكتب حقائق منتجك، واختار الموقف. جهّز مسودة بالمصري أو بالفصحى من غير ما نخترع سعر أو خصم أو ميعاد توصيل. جرّب فوراً، من غير حساب أو ربط واتساب.</p>
  <p className="tag" style={{display:"inline-block",lineHeight:1.8}}>أداة قوالب محلية، مش ذكاء اصطناعي توليدي. لا تحفظ المدخلات ولا ترسل رسائل أو بيانات لأي خادم.</p>
  <div className="row" style={{margin:"12px 0 20px"}}><button type="button" className="btn alt" onClick={sample}>جرّب بيانات مثال</button><button type="button" className="btn alt" onClick={reset}>مسح البيانات</button>{demo&&<strong style={{color:"#805600"}}>بيانات تجريبية فقط، مش عرض بيع حقيقي</strong>}</div>
  <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(min(100%,260px),1fr))",gap:24}}>
   <div style={{display:"grid",gap:16,alignContent:"start"}}>
    {field("product","المنتج أو الخدمة","مثال: اسم المنتج")}{field("price","السعر المؤكد مع العملة (اختياري)","مثال: ٣٥٠ جنيه مصري، شامل الضريبة")}{field("delivery","تكلفة ومدة ونطاق التوصيل المؤكدة (اختياري)","اكتب التفاصيل المؤكدة فقط")}{field("policy","ميزة أو سياسة مؤكدة (اختياري)","بلاش وعود أو ضمانات غير مؤكدة")}
    <label style={{display:"grid",gap:8}}>موقف العميل<select value={scenario} onChange={e=>{setScenario(e.target.value as SalesScenario);invalidate()}}><option value="price">بكام؟</option><option value="expensive">السعر غالي</option><option value="delivery">الشحن بكام وهيوصل إمتى؟</option><option value="later">هفكر وأرد عليك</option><option value="confirm">مراجعة التفاصيل قبل الطلب</option><option value="stop">مش عايز رسائل تاني</option></select></label>
    <label style={{display:"grid",gap:8}}>أسلوب الرد<select value={formal?"formal":"egyptian"} onChange={e=>{setFormal(e.target.value==="formal");invalidate()}}><option value="egyptian">مصري بسيط</option><option value="formal">عربي فصحى</option></select></label>
    <button className="btn" type="button" onClick={()=>{const r=salesReply(facts,scenario,formal);setResult(r);setDraft(r.text);setNotice("")}}>جهّز مسودة الرد</button>
   </div>
   <div style={{background:"#f5f7ff",borderRadius:14,padding:20,minWidth:0}}>
    <h3 style={{marginTop:0}}>مسودتك تحت سيطرتك</h3>{!result?<p style={{lineHeight:1.9,color:"#536487"}}>اختار موقف واضغط &quot;جهّز مسودة الرد&quot;. لو في معلومة ناقصة هنوضحها بدل ما نخمنها. استخدم بيانات منتج فقط، من غير بيانات عملاء شخصية.</p>:<>
     {demo&&<p className="alert">المسودة مبنية على مثال تجريبي. لا تستخدم أسعار أو سياسات المثال مع عميل حقيقي.</p>}
     {result.missing.length>0&&<p className="alert" role="status">معلومات محتاجة تأكيد: {result.missing.join("، ")}. الرد لا يؤكد التفاصيل الناقصة.</p>}
     <label style={{display:"grid",gap:8}}>راجع وعدّل قبل النسخ<textarea rows={9} value={draft} onChange={e=>{setDraft(e.target.value);setNotice("")}} style={{width:"100%",lineHeight:1.9,resize:"vertical",background:"#fff"}}/></label>
     <p style={{fontSize:13,lineHeight:1.8}}>مصدر تفاصيل القالب: {result.facts.length?result.facts.join("، ")+" من مدخلاتك فقط.":"صياغة عامة، بلا سعر أو وعد مضاف."} التعديلات اليدوية مسؤوليتك في المراجعة.</p>
     {scenario==="stop"&&<p className="alert">مهم: الأداة لا تغيّر سجل العميل ولا توقف حملاتك. سجّل إلغاء الاشتراك وامنع التواصل في نظامك قبل استخدام المسودة.</p>}
     {scenario==="later"&&<p className="muted">طلب موافقة فقط. لا تنشئ هذه الأداة تذكيراً أو متابعة تلقائية.</p>}
     <button className="btn" type="button" disabled={!draft.trim()} onClick={copy}>نسخ المسودة فقط</button>
    </>}<p role="status" style={{minHeight:24,lineHeight:1.8}}>{notice}</p>
    <p style={{fontSize:12,lineHeight:1.9,color:"#536487"}}>مفيش إرسال تلقائي أو ربط بالـCRM في الأداة دي. لا تؤكد توافر المنتج أو تسجيل الطلب إلا بعد مراجعة فعلية. إعادة تحميل الصفحة تمسح المدخلات.</p>
   </div>
  </div>
 </section>
  }
