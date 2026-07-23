import json
import logging
import random
import re
import requests

from . import config

log = logging.getLogger("llm_client")

# Narrativ burchaklar — har safar boshqacha yondashuv
_NARRATIVE_ANGLES = [
    ("tarixiy evolyutsiya",
     "Mavzuni vaqt o'qi bo'ylab ko'rsat: qanday boshlangan, qanday rivojlangan, hozir qayerda. "
     "Har 'detail' slaydida muayyan sana yoki davr bo'lsin."),
    ("muammo-yechim",
     "Avval hozirgi muammolarni, keyin ularning yechimlarini ko'rsat. "
     "'breakdown' va 'detail' slaydlari muammoni chuqurroq ochsin."),
    ("raqamlar va faktlar",
     "Mazmunni statistika va aniq raqamlar orqali qur. "
     "Har slaydda kamida bitta katta raqam yoki foiz bo'lsin."),
    ("inson hikoyasi",
     "Mavzuni real odamlar, foydalanuvchilar yoki mutaxassislar nuqtayi nazaridan ko'rsat. "
     "Iqtibos va mini-misol ko'proq ishlat."),
    ("global-lokal kontrast",
     "Jahon miqyosidagi holat va O'zbekiston/mintaqadagi holat qiyoslab ko'rsat. "
     "Aniq raqamlar bilan farqni ochib ber."),
    ("kelajakka nazar",
     "Hozirgi holat + kelgusi 5-10 yildagi o'zgarishlar. "
     "'application' va 'synthesis' slaydlari kelajak imkoniyatlariga e'tibor qaratsin."),
    ("amaliy qo'llanma",
     "Nazariyadan ko'ra amaliyotga e'tibor ber. Qadamlar, maslahatlar, nima qilish kerak."),
    ("mif va haqiqat",
     "Keng tarqalgan noto'g'ri tushunchalarni ko'rsat, so'ng haqiqatni tushuntir."),
    ("iqtisodiy ta'sir",
     "Mavzuning moliyaviy, iqtisodiy va biznes jihatlariga e'tibor ber. "
     "Har slaydda pul, narx, o'sish yoki tejash ko'rsatkichlari bo'lsin."),
    ("texnik chuqurlik",
     "Mavzuning ichki mexanizmi, qanday ishlashini batafsil tushuntir. "
     "Formulalar, diagrammalar, texnik tafsilotlar."),
]

# ─────────────────────────────────────────── ASOSIY SYSTEM PROMPT

SYSTEM_PROMPT_BRIEF = """Sen dunyodagi eng ijodiy taqdimot dizayneri va mazmun mutaxassisisin.

ASOSIY QOIDA: Har slayd YANGI, NOYOB vizual kompozitsiya. Shablon yoki andoza ishlatma.
Har bir slayd bo'sh kanvas — elementlarning joylashuvi, shakli, rangi hammasini o'zing ixtiro qil.

══════════════════════════════════════════════════
SLAYD O'LCHAMI:  13.333" kenglik  ×  7.5" balandlik
Koordinatalar: (0, 0) = yuqori-chap burchak
══════════════════════════════════════════════════

ELEMENT TURLARI VA JSON FORMATI:

① rect — to'rtburchak (yoki yumaloq)
  {"type":"rect","x":0.0,"y":0.0,"w":5.5,"h":7.5,"fill":"1A1A2E","radius":false}
  • x, y, w, h — dyuym
  • fill — hex rang (# belgisisiz)
  • radius: true → yumaloq burchak

② text — matn bloki
  {"type":"text","x":0.8,"y":2.5,"w":6.5,"h":1.8,"text":"Matn","size":40,"bold":true,"italic":false,"color":"FFFFFF","align":"left","font":"Calibri"}
  • size — punkt (sarlavha: 32–52; kichik matn: 13–20)
  • align: "left" | "center" | "right"
  • font: "Calibri" | "Arial" | "Georgia" | "Trebuchet MS"
  • color — hex matn rangi

③ circle — aylana (dekorativ yoki kontentli)
  {"type":"circle","x":10.5,"y":-0.5,"d":3.2,"fill":"E94560"}
  • x, y — yuqori-chap burchakdan (qisman tashqarida ham bo'lishi mumkin — dizayn uchun)
  • d — diametr dyuymda

④ image — AI generatsiya qiladigan rasm (faqat kerak bo'lganda)
  {"type":"image","x":7.2,"y":0.5,"w":5.8,"h":6.5,"prompt":"photorealistic modern laboratory blue lighting cinematic"}
  • prompt — ingliz tilida, foto-real tavsif, 8-20 so'z

══════════════════════════════════════════════════
KOMPOZITSIYA G'OYALARI (har safar YANGILARINI ixtiro qil):

• Chap vertikal tasma: rect w≈4.5 butun balandlikda, matn o'ngda
• O'ng yarim bleed: image yoki rect o'ng tomonda, matn chapda
• Diagonal aksent: katta aylana burchakda qisman ko'rinib turadi
• Pastki horizontal tasma: rect y≈5.5 h≈2 accent rangda, matn yuqorida
• Asimmetrik grid: 60/40 yoki 70/30 bo'linish
• Markaziy focal: katta raqam yoki aylana markazda, matn atrofida
• Ko'p kichik blok: 3–5 ta kichik rect teng taqsimlangan
• Yuqori sarlavha tasma: rect y=0 h≈2 to'q rangda, matn pastda açiq fonda
• Burchakdan burchakka diagonal: 2 ta katta aylana qarama-qarshi burchaklarda
• Nesting: katta rect ichida kichik accent rect
• ...va bulardan butunlay FARQLI kompozitsiya yaraT

══════════════════════════════════════════════════
DIZAYN QOIDALARI:

✓ Kontrast: to'q fon → oq/açık matn; açık fon → to'q matn
✓ Ierarxiya: sarlavha 32–52pt bold; kichik matn 13–20pt
✓ Nafas: elementlar orasida kamida 0.15" bo'shliq
✓ Chekka: matn bloklari slayd chegarasidan ≥0.3" masofada bo'lsin
✓ Rang izchilligi: theme ranglaridan foydalan, har slaydda boshqacha kombinatsiya
✓ Har slayd: kamida 4–10 element

TAQIQLANGAN:
✗ Ikki ketma-ket slaydda bir xil kompozitsiya
✗ Matn rect ustiga yozilmagan (kontrast bo'lmasa o'qib bo'lmaydi)
✗ Elementlar slayd chegarasidan juda uzoqda (x > 13, y > 7.5 — faqat dekorativ aylonalar uchun ruxsat)
✗ Bo'sh slayd (matn yo'q)

══════════════════════════════════════════════════
ROLLAR VA DIZAYN USLUBI:

hook        → Birinchi taassurot. Sarlavha KATTA (44–52pt). Kuchli geometrik element.
              Bir jumlali qiziqarli hook_line matni.
              
context     → Kirish. O'qish qulay, aniq. 1–2 muhim fakt yoki raqam.

breakdown   → Ko'p element. Tuzilmali. Har bir element vizual ajratilgan.

detail      → Chuqur tafsilot. Aniq raqam, sana, misol SHART.

comparison  → Ikki tomon aniq vizual ajratilgan (rang, rect, bo'shliq bilan).

application → Amaliy, ilhomlovchi. Jarayon yoki misol ravshan ko'rinsin.

synthesis   → Final. Asosiy 3–5 fikr. Kuchli esda qoladigan vizual.

══════════════════════════════════════════════════
JAVOB FORMATI — faqat sof JSON (```json bloki yoki boshqa matn YO'Q):

{
  "topic": "mavzu nomi",
  "theme": {
    "primary": "0D1117",
    "accent": "58A6FF",
    "light": "E8F4FD",
    "heading_font": "Calibri",
    "body_font": "Calibri"
  },
  "slides": [
    {
      "index": 1,
      "role": "hook",
      "title": "Sarlavha matni (QA uchun)",
      "key_text": "Asosiy mazmun qisqacha (QA uchun)",
      "canvas": {
        "background": "0D1117",
        "elements": [
          {"type":"rect","x":0,"y":0,"w":5.2,"h":7.5,"fill":"161B22"},
          {"type":"circle","x":10.1,"y":-0.8,"d":3.8,"fill":"1F6FEB"},
          {"type":"circle","x":11.5,"y":5.5,"d":2.0,"fill":"0D419D"},
          {"type":"rect","x":0.7,"y":3.2,"w":0.06,"h":1.4,"fill":"58A6FF"},
          {"type":"text","x":0.8,"y":1.8,"w":3.4,"h":1.0,"text":"MAVZU NOMI","size":14,"bold":false,"italic":true,"color":"58A6FF","align":"left","font":"Calibri"},
          {"type":"text","x":0.8,"y":2.9,"w":3.5,"h":1.8,"text":"Asosiy sarlavha","size":44,"bold":true,"color":"E8F4FD","align":"left","font":"Calibri"},
          {"type":"text","x":0.8,"y":4.8,"w":3.5,"h":0.8,"text":"Hook jumlasi — qiziqtiruvchi savol yoki fakt","size":15,"bold":false,"color":"A0C4E8","align":"left","font":"Calibri"},
          {"type":"text","x":6.0,"y":6.8,"w":7.0,"h":0.5,"text":"Muallif / Sana","size":12,"bold":false,"color":"58A6FF","align":"right","font":"Calibri"}
        ]
      }
    }
  ]
}"""

# ─────────────────────────────────────────── REGENERATE PROMPT

SYSTEM_PROMPT_REGEN = """Sen bitta taqdimot slaydini vizual jihatdan qayta loyihalaysan.

Slayd o'lchami: 13.333" × 7.5"
Element turlari: rect, text, circle, image (koordinatalar dyuymda)

Foydalanuvchi slaydning eski JSON va muammoni beradi.
Muammoni bartaraf etadigan YANGI vizual kompozitsiya bilan canvas qaytар.

Qoidalar:
- role va index o'zgartirma
- title va key_text mazmunini saqlagan holda canvas.elements ni butunlay qayta ixtiro qil
- Muammoni to'liq bartaraf et (kontrast, ustma-ustlik, o'qilish va h.k.)
- Faqat sof JSON qaytar, boshqa hech narsa yozma

Format:
{
  "index": <n>,
  "role": "<role>",
  "title": "<sarlavha>",
  "key_text": "<mazmun>",
  "canvas": {
    "background": "<hex>",
    "elements": [...]
  }
}"""


# ─────────────────────────────────────────── YORDAMCHI FUNKSIYALAR

def _clean_json(raw: str) -> str:
    """Markdown kod bloklarini va boshqotirmalarni tozalaydi."""
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()
    # Birinchi { dan oxirgi } gacha kesib olish
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1:
        cleaned = cleaned[start:end + 1]
    return cleaned


def _salvage_partial_json(text: str) -> dict | None:
    """Yarim qolgan JSON dan to'liq slaydlarni saqlab qolishga urinadi."""
    try:
        # "slides" arrayini topib, oxirgi to'liq elementgacha kesib olamiz
        slides_start = text.find('"slides"')
        if slides_start == -1:
            return None
        arr_start = text.find("[", slides_start)
        if arr_start == -1:
            return None

        # To'liq slaydlarni bittama-bitta o'qib saqlaymiz
        depth = 0
        slides_json_end = arr_start
        i = arr_start
        last_good_end = arr_start + 1  # empty array fallback
        while i < len(text):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    last_good_end = i + 1  # bu slayd tugadi
            elif ch == "]" and depth == 0:
                slides_json_end = i
                break
            i += 1

        slides_str = text[arr_start:last_good_end] + "]"
        slides = json.loads(slides_str)
        if not slides:
            return None

        # topic va theme ni olishga urinish
        try:
            prefix = text[:arr_start]
            topic_match = re.search(r'"topic"\s*:\s*"([^"]+)"', prefix)
            topic = topic_match.group(1) if topic_match else "Mavzu"

            theme_start = prefix.find('"theme"')
            theme = {"primary": "0D1117", "accent": "58A6FF", "light": "E8F4FD",
                     "heading_font": "Calibri", "body_font": "Calibri"}
            if theme_start != -1:
                t_open = prefix.find("{", theme_start)
                t_close = prefix.find("}", t_open)
                if t_open != -1 and t_close != -1:
                    theme = json.loads(prefix[t_open:t_close + 1])
        except Exception:
            topic = "Mavzu"
            theme = {"primary": "0D1117", "accent": "58A6FF", "light": "E8F4FD",
                     "heading_font": "Calibri", "body_font": "Calibri"}

        return {"topic": topic, "theme": theme, "slides": slides}
    except Exception as ex:
        log.warning("Partial salvage muvaffaqiyatsiz: %s", ex)
        return None


def _call_openrouter(system_prompt: str, user_prompt: str, temperature: float = 0.9) -> dict:
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
    except json.JSONDecodeError as e:
        log.error("JSON parse xato. Xom javob (birinchi 2000 belgi): %s", raw[:2000])
        # Partial JSON salvage: oxirgi to'liq slaydgacha kesib olishga urinish
        salvaged = _salvage_partial_json(cleaned)
        if salvaged:
            log.warning("Partial JSON salvage muvaffaqiyatli: %d slayd", len(salvaged.get("slides", [])))
            return salvaged
        raise


# ─────────────────────────────────────────── ASOSIY FUNKSIYALAR

def generate_brief(topic: str) -> dict:
    """Mavzu bo'yicha to'liq JSON brief generatsiya qiladi — erkin vizual kanvas bilan."""
    angle_name, angle_desc = random.choice(_NARRATIVE_ANGLES)

    user_prompt = (
        f"Mavzu: {topic}\n\n"
        f"NARRATIV BURCHAK: «{angle_name}»\n"
        f"{angle_desc}\n\n"
        "Yuqoridagi system qoidalar va bu narrativ burchakka qat'iy amal qilib, "
        "to'liq JSON brief tuz. Har bir slayd uchun NOYOB vizual kompozitsiya ixtiro qil — "
        "hech bir slayd boshqasiga o'xshamasin. "
        "Slaydlar soni: 7–9 ta (ortiqcha uzaytirma). "
        "Har slaydda 4–8 element bo'lsin (ixcham saqlа). "
        "Agar mavzuda raqamlar bo'lsa, 'detail' yoki 'comparison' slaydida aniq raqam ko'rsat. "
        "Agar vizual tasvir kuchaytirsa, 'image' elementidan foydalan (1–2 ta slaydda)."
    )
    return _call_openrouter(SYSTEM_PROMPT_BRIEF, user_prompt, temperature=0.95)


def regenerate_slide(topic: str, slide_json: dict, feedback: str) -> dict:
    """QA yoki grounding-check muvaffaqiyatsiz bo'lganda, bitta slaydni qayta loyihalaydi."""
    user_prompt = (
        f"Mavzu: {topic}\n"
        f"Muammo: {feedback}\n"
        f"Eski slayd JSON:\n{json.dumps(slide_json, ensure_ascii=False)}\n\n"
        "Muammoni bartaraf etgan yangi slayd JSON qaytar."
    )
    return _call_openrouter(SYSTEM_PROMPT_REGEN, user_prompt, temperature=0.85)
