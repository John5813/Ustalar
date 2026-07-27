import json
import logging
import random
import re
import requests

from . import config

log = logging.getLogger("llm_client")

# Narrativ burchaklar — mavzuga mos keladigani tanlanadi
_NARRATIVE_ANGLES = [
    ("sabab-oqibat tahlili",
     "Mavzuning asosiy sabablari va ularning oqibatlarini chuqur ko'rsat. "
     "Har 'detail' slaydida bitta sabab va uning aniq oqibatlarini tushuntir."),
    ("muammo-yechim",
     "Avval hozirgi muammolarni aniq ko'rsat, keyin har biriga yechim taklif qil. "
     "'breakdown' va 'detail' slaydlari muammoni, 'application' esa yechimlarni ochsin."),
    ("tarixiy evolyutsiya",
     "Mavzuni vaqt o'qi bo'ylab ko'rsat: qanday boshlangan, qanday rivojlangan, hozir qayerda. "
     "Har 'detail' slaydida muayyan sana yoki davr bo'lsin."),
    ("amaliy qo'llanma",
     "Nazariyadan ko'ra amaliyotga e'tibor ber. Qadamlar, maslahatlar, nima qilish kerak. "
     "Har qadam 'application' slaydlarida batafsil ko'rsatilsin."),
    ("taqqosli tahlil",
     "Turli yondashuvlar, variantlar yoki tomonlarni qiyoslab ko'rsat. "
     "'comparison' slaydlarida ikki tomonning afzalliklari va kamchiliklari aniq ko'rinsin."),
    ("raqamlar va dalillar",
     "Mazmunni aniq statistika, o'lchovlar va faktlar orqali qur. "
     "Har slaydda kamida bitta aniq raqam yoki o'lchov bo'lsin — manbasi bilan."),
    ("kelajakka nazar",
     "Hozirgi holat + kelgusi 5-10 yildagi o'zgarishlar va imkoniyatlar. "
     "'application' va 'synthesis' slaydlari kelajakdagi qadamlarga yo'naltirilsin."),
    ("mif va haqiqat",
     "Keng tarqalgan noto'g'ri tushunchalarni ko'rsat, so'ng haqiqiy ma'lumot bilan rad qil. "
     "Har 'detail' slaydida bitta mif va uning haqiqiy yechimi."),
]

# ─────────────────────────────────────────── ASOSIY SYSTEM PROMPT

SYSTEM_PROMPT_BRIEF = """Sen professional biznes va ilmiy taqdimot mutaxassisissan. Sening slaydlaring aniq, mazmunli va ko'rinishda professional — McKinsey, TED yoki akademik konferensiyalar darajasida.

ASOSIY TAMOYIL:
Har slayd — bitta aniq g'oyani to'liq tushuntiradi. Matn, raqam va vizual element birgalikda ishlaydi.
Mavzudan KELIB CHIQQAN holda kontent yoz — global bozor ulushi, xalqaro statistika har doim ham kerak emas.
Agar mavzu mahalliy, texnik, shaxsiy yoki ijodiy bo'lsa — shu doiradagi faktlar, misollar, tafsilotlar ishlatilsin.

══════════════════════════════════════════════════
SLAYD O'LCHAMI: 13.333" × 7.5"  |  (0,0) = yuqori-chap
══════════════════════════════════════════════════

ELEMENT TURLARI:

① rect
{"type":"rect","x":0.0,"y":0.0,"w":4.2,"h":7.5,"fill":"1B2A4A","radius":false}
• radius:true — faqat kichik aksent bloklari uchun

② text
{"type":"text","x":0.5,"y":1.0,"w":5.5,"h":1.2,"text":"Matn","size":20,"bold":true,"color":"FFFFFF","align":"left","font":"Calibri"}
• Ko'p qatorli matn: \n bilan ajrating
• size: sarlavha 28–40pt | kichik sarlavha 16–22pt | tana 13–16pt | izoh 11–12pt
• font: "Calibri" | "Georgia" | "Trebuchet MS"

③ circle — kichik aksent uchun, d ≤ 2.0", slayd ichida
{"type":"circle","x":3.8,"y":0.6,"d":0.9,"fill":"E8A020"}

④ image — AI rasm (1–2 ta slaydda, mavzu vizuallik talab qilganda)
{"type":"image","x":7.5,"y":0.8,"w":5.5,"h":5.8,"prompt":"detailed descriptive English prompt, photorealistic, professional, 20-30 words"}

⑤ chart — diagramma (FAQAT raqamli, statistik, ilmiy mavzularda)
{"type":"chart","x":1.0,"y":1.8,"w":8.5,"h":4.2,
 "chart_type":"column",
 "chart_title":"Diagramma sarlavhasi",
 "caption":"Bu diagrammada nima ko'rsatilgani — aniq va ravshan izohlang (1-2 jumla)",
 "categories":["Kat1","Kat2","Kat3"],
 "series":[{"name":"Qator1","values":[45,30,25]}]}

  ⚠️ MAVZU TURI ASOSIDA DIAGRAMMA QOIDASI:

  RAQAMLI/ILMIY mavzular (diagramma qo'yish mumkin):
  → Matematika, fizika, kimyo, biologiya, iqtisod, statistika, texnologiya, tarix (sanalar bilan)
  → Taqqoslash, trend, o'sish, ulush ko'rsatish — slaydning ASOSIY maqsadi bo'lganida

  FALSAFIY/ADABIY/IJODIY mavzular (diagramma MUTLAQO kerak emas):
  → Falsafa, axloq, din, she'riyat, adabiyot, his-tuyg'u, psixologiya (miqdorsiz)
  → "Chiroyli qalb", "Sevgi", "Baxt", "Erkinlik" kabi mavzular

  ✗ Bir taqdimotda 3 tadan ORTIQ diagramma bo'lmasin
  ✗ Diagramma "bezak" uchun qo'yilmasin — haqiqiy ma'lumot yo'q bo'lsa qo'yma

  MAJBURIY: "caption" maydoni HAR DOIM to'ldirilsin — diagrammada nima ko'rsatilgani
  aniq bir-ikki jumlada yozilsin. Masalan:
  "2015–2024 yillarda O'zbekistonda yalpi ichki mahsulot o'sishi (mlrd. so'm)"

══════════════════════════════════════════════════
MATN FORMATI — AI o'zi tanlaydi:

Qachon BULLET ro'yxat:
  • Alohida, teng darajali bandlar (3–6 ta)
  • Qadamlar, xususiyatlar, imkoniyatlar ro'yxati
  Format: "• Birinchi band\n• Ikkinchi band\n• Uchinchi band"

Qachon TO'LIQ PARAGRAF:
  • Tushuntirish, tahlil, kontekst, sabablar
  • Bir-biri bilan bog'liq fikrlar ketma-ketligi
  Format: "Bu hodisa shundan kelib chiqadiki, ... Natijada ... va shu tufayli ..."

Aralash (avval paragraf, keyin bullet):
  • Kirish jumlasi, so'ngra asosiy bandlar
  Format: "Asosiy omillar:\n• Birinchi\n• Ikkinchi"

TAQIQLANGAN: hamma slaydda hamisha bullet — formatsiz, bir xil tuzilma.

══════════════════════════════════════════════════
PROFESSIONAL LAYOUT TIZIMI:

[A] CHAP PANEL + O'NG KONTENT
  • Chap: to'q panel (x=0, w=4.0–4.5, h=7.5) — sarlavha, kichik izoh
  • O'ng: och fon, 3–5 faktblok yoki diagramma + matn

[B] YUQORI TASMA + PASTKI KONTENT
  • Yuqori: to'q tasma (y=0, h=1.6–2.0, w=13.333) — sarlavha
  • Pastda: 2–3 ustunli bloklar yoki batafsil matn + diagramma

[C] IKKI USTUN TAQQOSLASH
  • Chap ustun (w≈6.3): birinchi tomon — sarlavha, matn, metrika
  • Ajratuvchi (w=0.04, to'q rang)
  • O'ng ustun (w≈6.3): ikkinchi tomon — sarlavha, matn, metrika

[D] KARTA TIZIMI (3–4 ta)
  • Yuqori tasma + 3–4 teng karta
  • Har karta: sarlavha + katta raqam/belgi + 2–4 qator izoh

[E] KONTENT + DIAGRAMMA
  • Chap: sarlavha + 3–5 qator tushuntirish matni
  • O'ng: diagramma (chart element)

[F] YARIM MATN + YARIM RASM (har 6 varoqda KAMIDA 1 ta MAJBURIY)
  • Chap yarmi (x=0.4, w=6.0): to'q panel yoki och fon + sarlavha + 4–6 qator matn
  • O'ng yarmi (x=7.0, w=6.0): image element — mavzuning vizual ifodasi
  Bu layout: tabiat, arxitektura, texnologiya, inson, san'at mavzulari uchun ideal.
  Rasm prompti 20–30 so'z, inglizcha, photorealistic.

══════════════════════════════════════════════════
MATN HAJMI — MAJBURIY:

Har slaydda KAMIDA 80 so'z matn bo'lsin (sarlavhalar bilan birga).
Har faktblok/karta ichida: sarlavha + 2–4 qator izoh.
Tana matni 13–16pt — o'qib bo'ladigan, mazmunli jumlalar.

══════════════════════════════════════════════════
RANG QOIDALARI:

• To'q fon → oq/juda och matn (FFFFFF yoki F0F0F0)
• Och fon → to'q matn (primary yoki 1A1A2A)
• TAQIQLANGAN: o'xshash rangdagi fon va shakl (masalan fon #1B3A6B + shakl #1F4080)
• Accent rang — faqat eng muhim elementlar uchun (sarlavha, raqam, aksent chiziq)

══════════════════════════════════════════════════
ROLLAR BO'YICHA:

hook       → Kuchli ochilish. Sarlavha 34–40pt. Katta focal raqam/fakt (52–60pt).
              3–4 qator izoh: nima haqida, nima uchun muhim.

context    → Mavzu fonini tushuntirish. 5–8 qator tuzilmali matn yoki 2 ta faktblok.
              Diagramma qo'shish mumkin (trend, tarix).

breakdown  → Tuzilmali tahlil. [B] yoki [D] layout.
              3–4 blok, har birida sarlavha + 3 qator izoh. Diagramma mumkin.

detail     → Chuqur tafsilot. Aniq raqam, sana, misol MAJBURIY.
              Paragraf formatida 6–10 qator matn. Diagramma juda mos keladi.

comparison → [C] layout MAJBURIY. Har ustunda sarlavha + 4–6 qator matn + metrika.
              Diagramma (bar/column) taqqoslashni kuchaytiradi.

application → Amaliy, qadamli. Bullet yoki raqamlangan qadamlar.
              Har qadam 2–3 qator tushuntirish. Diagramma (line/column) mumkin.

synthesis  → Final xulosa. 4–5 asosiy xulosa + har biri 1–2 qator izoh.
              Yakunlovchi chaqiriq yoki asosiy tavsiya.

══════════════════════════════════════════════════
DIAGRAMMA UCHUN MA'LUMOTLAR:

Faqat REAL, MANTIQIY ma'lumotlar ishlatilsin.
Agar aniq raqam ma'lum bo'lmasa — taxminiy lekin realistik qiymatlar.
Kategoriyalar: 3–7 ta (ko'p bo'lsa o'qilmaydi).
Qiymatlar: bir seriyada 3–7 ta son.

══════════════════════════════════════════════════
QATTIQ TAQIQLAR:

✗ Slaydning yarmi bo'sh (40%+ bo'sh joy)
✗ Faqat sarlavha va raqam — izoh matni yo'q
✗ Dekorativ katta doiralar slayd chegarasidan tashqarida
✗ Mavzudan uzilgan global statistika (kerak bo'lmasa)
✗ Hamma slaydda bir xil bullet format
✗ Chekka: matn bloklari slayd chegarasidan ≥ 0.3" masofada

══════════════════════════════════════════════════
JAVOB: faqat sof JSON (markdown, ``` yoki boshqa matn YO'Q):

{
  "topic": "mavzu",
  "theme": {"primary":"1B2A4A","accent":"E8A020","light":"F4F6F9","heading_font":"Calibri","body_font":"Calibri"},
  "slides": [
    {
      "index": 1, "role": "hook",
      "title": "Sarlavha (QA uchun)",
      "key_text": "Kamida 3 ta to'liq jumla — slayd asosiy g'oyasi",
      "canvas": {
        "background": "F4F6F9",
        "elements": [...]
      }
    }
  ]
}"""

# ─────────────────────────────────────────── REGENERATE PROMPT

SYSTEM_PROMPT_REGEN = """Sen professional biznes taqdimot slaydini qayta loyihalaysan.

Slayd o'lchami: 13.333" × 7.5". Element turlari: rect, text, circle, image, chart.

Chart formati: {"type":"chart","x":1.0,"y":2.0,"w":8.0,"h":4.0,"chart_type":"column|bar|line|pie|donut","chart_title":"...","categories":[...],"series":[{"name":"...","values":[...]}]}

Muammoni to'liq bartaraf etgan YANGI professional layout bilan qaytар.

Qoidalar:
- role, index o'zgartirma
- Matn hajmini KAMAYTIRMA — ko'proq izoh qo'sh (kamida 80 so'z)
- Professional layout: chap panel, yuqori tasma, ustun tizimi
- To'q fon → oq matn; och fon → to'q matn
- Diagramma (chart) FAQAT slayd asosan raqamli taqqoslash/trend haqida bo'lsagina qo'sh
  Aks holda (falsafa, tushuntirish, his-tuyg'u, tavsif) — diagramma QILMA, o'rniga matn bloklari yoki rasm
- Agar muammoda "keraksiz" yoki "o'chir" deyilsa — o'sha elementni OLIB TASHLА, o'rnini matn bilan to'ldir
- Faqat sof JSON qaytar

Format:
{
  "index": <n>, "role": "<role>",
  "title": "<sarlavha>", "key_text": "<kamida 3 jumla>",
  "canvas": {"background": "<hex>", "elements": [...]}
}"""


# ─────────────────────────────────────────── YORDAMCHI FUNKSIYALAR

def _clean_json(raw: str) -> str:
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1:
        cleaned = cleaned[start:end + 1]
    return cleaned


def _salvage_partial_json(text: str) -> dict | None:
    try:
        slides_start = text.find('"slides"')
        if slides_start == -1:
            return None
        arr_start = text.find("[", slides_start)
        if arr_start == -1:
            return None

        depth = 0
        i = arr_start
        last_good_end = arr_start + 1
        while i < len(text):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    last_good_end = i + 1
            elif ch == "]" and depth == 0:
                break
            i += 1

        slides_str = text[arr_start:last_good_end] + "]"
        slides = json.loads(slides_str)
        if not slides:
            return None

        try:
            prefix = text[:arr_start]
            topic_match = re.search(r'"topic"\s*:\s*"([^"]+)"', prefix)
            topic = topic_match.group(1) if topic_match else "Mavzu"
            theme_start = prefix.find('"theme"')
            theme = {"primary": "1B2A4A", "accent": "E8A020", "light": "F4F6F9",
                     "heading_font": "Calibri", "body_font": "Calibri"}
            if theme_start != -1:
                t_open = prefix.find("{", theme_start)
                t_close = prefix.find("}", t_open)
                if t_open != -1 and t_close != -1:
                    theme = json.loads(prefix[t_open:t_close + 1])
        except Exception:
            topic = "Mavzu"
            theme = {"primary": "1B2A4A", "accent": "E8A020", "light": "F4F6F9",
                     "heading_font": "Calibri", "body_font": "Calibri"}

        return {"topic": topic, "theme": theme, "slides": slides}
    except Exception as ex:
        log.warning("Partial salvage muvaffaqiyatsiz: %s", ex)
        return None


def _call_openrouter(system_prompt: str, user_prompt: str, temperature: float = 0.7) -> dict:
    if not config.OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY topilmadi")

    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.OPENROUTER_TEXT_MODEL,
        "temperature": temperature,
        "max_tokens": 16000,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    resp = requests.post(config.OPENROUTER_URL, headers=headers, json=payload, timeout=180)
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"]
    cleaned = _clean_json(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        log.error("JSON parse xato. Xom javob (2000 belgi): %s", raw[:2000])
        salvaged = _salvage_partial_json(cleaned)
        if salvaged:
            log.warning("Partial JSON salvage: %d slayd", len(salvaged.get("slides", [])))
            return salvaged
        raise


# ─────────────────────────────────────────── ASOSIY FUNKSIYALAR

def _base_rules(topic: str, slide_count: int) -> str:
    """Barcha brief va chunk promptlari uchun umumiy qoidalar."""
    return (
        f"• Slaydlar soni: AYNAN {slide_count} ta\n"
        "• Har slaydda KAMIDA 80 so'z matn\n"
        "• Mavzuga mos ma'lumotlar — global statistika faqat kerak bo'lganda\n"
        "• Matn formati (bullet/paragraf) mazmunga qarab tanlangsin\n"
        "• Rang kontrasti qat'iy: to'q fon → oq matn, och fon → to'q matn\n"
        "• key_text har slayd uchun kamida 3 ta to'liq jumla\n"
        f"• Har 6 slaydda KAMIDA 1 ta [F] layout: chap-matn o'ng-rasm (agar mavzu vizuallikka mos)\n"
        "• Diagramma (chart): FAQAT raqamli/ilmiy/statistik mavzularda va FAQAT kerak joyda\n"
        "  Falsafiy, adabiy, ijodiy mavzularda diagramma MUTLAQO kerak emas\n"
        "  Diagramma qo'shsang — 'caption' maydoni MAJBURIY to'ldirsin\n"
        "• Vizual tasvir kerak bo'lsa image element (20–30 so'zli inglizcha prompt)"
    )


def generate_brief(topic: str, slide_count: int = 8) -> dict:
    angle_name, angle_desc = random.choice(_NARRATIVE_ANGLES)

    user_prompt = (
        f"Mavzu: {topic}\n\n"
        f"NARRATIV YONDASHUV: «{angle_name}»\n"
        f"{angle_desc}\n\n"
        "Qoidalar:\n"
        + _base_rules(topic, slide_count)
    )
    return _call_openrouter(SYSTEM_PROMPT_BRIEF, user_prompt, temperature=0.72)


def generate_brief_chunk(
    topic: str,
    chunk_size: int,
    chunk_num: int,
    total_chunks: int,
    is_first: bool,
    is_last: bool,
    prev_summary: str | None,
) -> dict:
    """Taqdimotning bir bo'lagini (chunk_size ta slayd) generatsiya qiladi."""
    if is_first:
        role_hint = (
            "Bu BIRINChI bo'lak.\n"
            "Birinchi slayd: role='hook' (MAJBURIY).\n"
            "Keyin: context, breakdown va detail slaydlari."
        )
    elif is_last:
        role_hint = (
            f"Bu OXIRGI bo'lak ({chunk_num+1}/{total_chunks}).\n"
            "Oxirgi slayd: role='synthesis' (MAJBURIY).\n"
            "Application slaydlaridan keyin synthesis bilan yoping."
        )
    else:
        role_hint = (
            f"Bu {chunk_num+1}/{total_chunks}-bo'lak (o'rtadagi).\n"
            "breakdown, detail, comparison, application rollaridan foydalaning (tartibda).\n"
            "Birinchi yoki oxirgi bo'lak emas — hook va synthesis QILMANG."
        )

    prev_ctx = (
        f"\nOLDINGI BO'LAK XULOSASI (takrorlanmaslik uchun):\n{prev_summary}\n"
        if prev_summary else ""
    )

    user_prompt = (
        f"Mavzu: {topic}\n"
        f"Bo'lak: {chunk_num+1}/{total_chunks} | {chunk_size} ta slayd\n"
        f"{prev_ctx}\n"
        f"{role_hint}\n\n"
        "Qoidalar:\n"
        + _base_rules(topic, chunk_size) +
        "\n• Avvalgi bo'lak bilan takrorlanmaslik — yangi g'oyalar, yangi faktlar\n"
        "• Mantiqiy bog'lanish: avvalgi slaydlar mavzusini davom ettir"
    )
    return _call_openrouter(SYSTEM_PROMPT_BRIEF, user_prompt, temperature=0.72)


def get_chunk_summary(slides_raw: list) -> str:
    """Keyingi bo'lak uchun avvalgi bo'lak qisqacha xulosasini tuzadi."""
    parts = []
    for s in slides_raw:
        title = s.get("title", "")
        key = (s.get("key_text", "") or "")[:120]
        role = s.get("role", "")
        parts.append(f"[{role}] {title}: {key}")
    return "\n".join(parts)


def regenerate_slide(topic: str, slide_json: dict, feedback: str) -> dict:
    user_prompt = (
        f"Mavzu: {topic}\n"
        f"Muammo: {feedback}\n"
        f"Eski slayd JSON:\n{json.dumps(slide_json, ensure_ascii=False)}\n\n"
        "Muammoni bartaraf etgan professional yangi slayd JSON qaytar. "
        "Agar ma'lumotlar taqqoslansa — diagramma qo'sh. "
        "Matn hajmini KAMAYTIRMA."
    )
    return _call_openrouter(SYSTEM_PROMPT_REGEN, user_prompt, temperature=0.6)
