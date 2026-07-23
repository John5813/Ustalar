import json
import logging
import random
import re
import requests

from . import config

# Narrativ burchaklar: bir xil mavzu har safar boshqacha burchakdan ko'rsatiladi
_NARRATIVE_ANGLES = [
    ("tarixiy evolyutsiya", "Mavzuni vaqt o'qi bo'ylab ko'rsat: qanday boshlangan, qanday rivojlangan, hozir qayerda. Har 'detail' slaydida muayyan sana yoki davr bo'lsin. Agar ma'lumot dinamikasini ko'rsatish imkoni bo'lsa, xy_chart layout ishlat."),
    ("muammo-yechim", "Avval hozirgi muammolarni, keyin ularning yechimlarini ko'rsat. 'breakdown' va 'detail' slaydlari muammoni chuqurroq ochsin. Taqqoslashda bar_chart ishlat."),
    ("raqamlar va faktlar", "Mazmunni statistika va aniq raqamlar orqali qurilsin. Har slaydda kamida bitta katta raqam yoki foiz bo'lsin. stat_callout va stat_row_triple ko'proq ishlat. Qo'shimcha ravishda bar_chart yoki xy_chart bilan dinamikani ko'rsat."),
    ("inson hikoyasi", "Mavzuni real odamlar, foydalanuvchilar yoki mutaxassislar nuqtayi nazaridan ko'rsat. quote_callout va mini_case_study ko'proq ishlat."),
    ("global-lokal kontrast", "Jahon miqyosidagi holat va O'zbekiston/mintaqadagi holat qiyoslab ko'rsatilsin. comparison_table va two_card_compare ko'proq ishlat. Raqamlarni bar_chart bilan ko'rsat."),
    ("kelajakka nazar", "Hozirgi holat + kelgusi 5-10 yildagi o'zgarishlar. 'application' va 'synthesis' slaydlari kelajak imkoniyatlariga e'tibor qaratsin. Prognoz chizig'ini xy_chart bilan ko'rsat."),
    ("amaliy qo'llanma", "Nazariyadan ko'ra amaliyotga e'tibor ber. Qadamlar, amaliy maslahatlar, nima qilish kerak. timeline_process va agenda_numbered ko'proq ishlat."),
    ("mif va haqiqat", "Keng tarqalgan noto'g'ri tushunchalarni ko'rsat, so'ng haqiqatni tushuntir. definition_spotlight va two_card_compare ko'proq ishlat."),
    ("iqtisodiy ta'sir", "Mavzuning moliyaviy, iqtisodiy va biznes jihatlariga e'tibor ber. Har slaydda pul, narx, o'sish yoki tejash ko'rsatkichlari bo'lsin. bar_chart va stat_row_triple asosiy vosita."),
    ("texnik chuqurlik", "Mavzuning ichki mexanizmi, qanday ishlashini batafsil tushuntir. breakdown va detail slaydlari texnik tafsilotlarni ochsin. Agar formulalar mavjud bo'lsa, math_formula layout SHART ishlat."),
]

log = logging.getLogger("llm_client")

LAYOUT_CATALOG = """
Ruxsat etilgan layout_type'lar va ular tegishli role'lar:
- hook        -> title_dark
- context     -> icon_row_list, stat_callout, image_half_bleed, definition_spotlight
- breakdown   -> three_card_grid, four_card_grid, agenda_numbered, timeline_process, bar_chart, xy_chart
- detail      -> two_card_compare, image_half_bleed, icon_row_list, stat_callout, quote_callout, math_formula, bar_chart, xy_chart
- comparison  -> comparison_table, two_card_compare, stat_row_triple, bar_chart, xy_chart
- application -> image_half_bleed, stat_callout, timeline_process, mini_case_study, bar_chart, math_formula
- synthesis   -> conclusion_dark

YANGI LAYOUTLAR (diagramma va formulalar):
  bar_chart    — raqamli ma'lumotlarni vertikal bar diagrammasi bilan ko'rsatish uchun
  xy_chart     — vaqt yoki o'zgaruvchan qiymatlar orasidagi bog'liqlikni chiziqli grafik bilan ko'rsatish
  math_formula — fizika, kimyo, iqtisodiyot, matematika formulalari + izoh
"""

REQUIRED_FIELDS_BY_LAYOUT = """
7) MAJBURIY MAYDONLAR — har layout uchun quyidagi maydonlar NULL yoki BO'SH qoldirilsa TAQIQLANGAN:

   title_dark      → title (majburiy), hook_line (majburiy, 8-15 so'z), subtitle (majburiy)

   icon_row_list   → title (majburiy), body (1-2 jumlali kirish matni, majburiy),
                     items: KAMIDA 3 ta [{heading, body}] — bo'sh ro'yxat TAQIQLANGAN

   agenda_numbered → title (majburiy),
                     items: KAMIDA 3 ta [{heading, body}] — bo'sh ro'yxat TAQIQLANGAN

   three_card_grid → title (majburiy),
                     items: AYNAN 3 ta [{heading, body}] — bo'sh ro'yxat TAQIQLANGAN

   four_card_grid  → title (majburiy),
                     items: AYNAN 4 ta [{heading, body}] — bo'sh ro'yxat TAQIQLANGAN

   two_card_compare→ title (majburiy),
                     items: AYNAN 2 ta [{heading, body, example}] — bo'sh ro'yxat TAQIQLANGAN

   comparison_table→ title (majburiy),
                     items: KAMIDA 3 ta [{heading, body}] (heading=xususiyat, body=tafsilot)
                     — bo'sh ro'yxat TAQIQLANGAN

   stat_row_triple → title (majburiy),
                     items: AYNAN 3 ta [{heading: "aniq raqam+birlik", body: "qisqa tavsif"}]
                     — bo'sh ro'yxat TAQIQLANGAN

   stat_callout    → title (majburiy),
                     items: 1 ta [{heading: "katta raqam/fakt", body: "izohi, 1-2 jumla"}]
                     — bo'sh ro'yxat TAQIQLANGAN

   timeline_process→ title (majburiy),
                     items: KAMIDA 3 ta [{heading: "bosqich nomi", body: "qisqa tavsif"}]
                     — bo'sh ro'yxat TAQIQLANGAN

   quote_callout   → title (majburiy, manba/kontekst),
                     body (majburiy — iqtibos matni, 15-30 so'z, to'liq jumla)

   definition_spotlight → title (majburiy — atama nomi),
                     body (majburiy — aniq ta'rif, 20-40 so'z)

   image_half_bleed→ title (majburiy), body (majburiy — 3-5 jumla matn),
                     image_prompt (MAJBURIY — inglizcha, 10-20 so'z, foto-real tavsif)

   mini_case_study → title (majburiy),
                     items: AYNAN 2 ta [{heading: "Muammo"/"Yechim", body: "3-5 jumla"}]
                     — bo'sh ro'yxat TAQIQLANGAN

   conclusion_dark → title (majburiy),
                     key_takeaways: AYNAN 3-4 ta xulosa (har biri to'liq jumla),
                     closing_thought (majburiy — yakunlovchi chuqur/qiziqarli bitta fikr)

   bar_chart       → title (majburiy),
                     body (ixtiyoriy — 1-2 jumlali izoh),
                     chart_data (MAJBURIY): {
                       "x_label": "X o'qi nomi (masalan: Yillar, Davlat, Kategoriya)",
                       "y_label": "Y o'qi nomi (masalan: Daromad, Foiz, Miqdor)",
                       "unit": "birlik (%, mln, kg, °C — yoki bo'sh satr)",
                       "points": [
                         {"label": "2020", "value": 45.2},
                         {"label": "2021", "value": 58.7},
                         {"label": "2022", "value": 72.1},
                         {"label": "2023", "value": 89.4}
                       ]
                     }
                     — kamida 3 ta point bo'lishi SHART, maksimum 8 ta

   xy_chart        → title (majburiy),
                     body (ixtiyoriy — 1-2 jumlali izoh),
                     chart_data (MAJBURIY): {
                       "x_label": "X o'qi nomi (vaqt, parametr)",
                       "y_label": "Y o'qi nomi",
                       "unit": "birlik yoki bo'sh satr",
                       "points": [
                         {"label": "Yanvar", "value": 12.5},
                         {"label": "Fevral", "value": 18.3},
                         {"label": "Mart", "value": 15.8}
                       ]
                     }
                     — kamida 3 ta point bo'lishi SHART, trend ko'rsatish uchun 5-8 ta ideal

   math_formula    → title (majburiy),
                     body (ixtiyoriy — umumiy izoh),
                     math_blocks (MAJBURIY): KAMIDA 2 ta, MAKSIMUM 4 ta [
                       {
                         "formula": "E = mc²",
                         "description": "Energiya massa va yorug'lik tezligining kvadratiga teng. Einstein nisbiylik nazariyasidan."
                       },
                       {
                         "formula": "F = ma",
                         "description": "Kuch — massa va tezlanish ko'paytmasi (Newton 2-qonuni)."
                       }
                     ]
                     — formulalar mavzuga mos, haqiqiy, aniq bo'lsin

8) RASM (image_prompt):
   - image_half_bleed layoutida image_prompt MAJBURIY.
   - context, detail, application rollarida KAMIDA 1 ta slaydda image_prompt bo'lsin.
   - image_prompt ingliz tilida, aniq va foto-real: masalan
     "water droplets falling on dry cracked earth, dramatic lighting, close-up"
   - image_prompt bo'sh qoldirilsa yoki null bo'lsa — image_half_bleed slayd YAROQSIZ hisoblanadi.

9) DIAGRAMMA VA FORMULA QOIDALARI:
   - Mavzuda raqamli ma'lumotlar bo'lsa (statistika, o'sish, taqqoslash) — bar_chart YOKI xy_chart SHART ishlat.
   - Mavzuda ilmiy/matematik asoslar bo'lsa (fizika, kimyo, iqtisodiyot, biologiya, muhandislik) — math_formula SHART ishlat.
   - bar_chart va xy_chart'dagi barcha values aniq haqiqiy raqam bo'lsin (taxminiy ham bo'lsa ham).
   - math_formula da formulalar mavzuga mos va to'g'ri bo'lsin.
"""

SYSTEM_PROMPT_BRIEF = f"""Sen taqdimot mazmuni va dizaynini rejalashtiruvchi mutaxassissan.
Foydalanuvchi bergan mavzu bo'yicha 8-10 slaydlik taqdimot uchun QAT'IY JSON formatida javob ber.
Javobda JSON'dan tashqari HECH QANDAY matn, izoh yoki markdown belgisi (```) bo'lmasin.

QOIDALAR:

1) MANTIQIY KETMA-KETLIK — har slayd "role" maydoniga ega bo'lishi SHART, va rollar aynan shu tartibda kelishi kerak
   (ba'zilari bir necha marta takrorlanishi mumkin, lekin tartib buzilmasin):
   hook(1) -> context(1) -> breakdown(1-2) -> detail(2-4) -> comparison(0-1) -> application(0-1) -> synthesis(1)
   - "detail" slaydlari bir-birini takrorlamasin, har biri YANGI axborot qo'shsin.
   - hook faqat 1-slaydda, synthesis faqat oxirgi slaydda bo'ladi.

2) MANTIQIY SHABLON TANLASH — har slayd uchun "layout_type" faqat shu role'ga ruxsat etilgan ro'yxatdan tanlansin:
{LAYOUT_CATALOG}
   Ketma-ket ikki slayd bir xil layout_type ishlatmasin.

3) BOSHLANISH VA YAKUN:
   - hook slaydida "hook_line" maydoni bo'lsin: 8-15 so'zli qiziqarli savol yoki ajablantiruvchi fakt.
   - synthesis slaydida "key_takeaways" (3-4 ta aniq, bir-birini takrorlamaydigan xulosa) va
     "closing_thought" (mavzuni yakunlovchi chuqur/qiziqarli bitta fikr) maydonlari bo'lsin.

4) ANIQ MA'LUMOT (GROUNDING) — umumiy, hech narsa demaydigan jumlalar TAQIQLANGAN
   (masalan: "bu muhim mavzu", "keling ko'rib chiqamiz"). Har "detail" va "comparison" slaydida
   kamida bitta aniq raqam, sana, atoqli ot yoki aniq misol bo'lishi SHART.

5) DIZAYN:
   - "palette": mavzu mantig'iga mos 3 ta hex rang (primary, secondary, accent) — masalan tabiat mavzusi
     uchun yashil tonlar, texnologiya uchun ko'k/neon, tarix uchun jigarrang/oltin, tibbiyot uchun oq/moviy.
     Rangni mavzudan mantiqan kelib chiqib TANLA, oldindan belgilangan jadvaldan emas.
   - "font_pair": {{heading, body}} — ikkita mos shrift nomi (masalan Georgia+Calibri, Cambria+Arial).
   - "motif": "icon_circle" | "numbered_badge" | "rounded_frame" — bittasini tanla, butun taqdimotda shu ishlatiladi.

6) MATN HAJMI — har slaydda matn hajmini nazorat qil:
   - Bitta items.body maydoni 120 belgidan oshmasin.
   - Umumiy body maydoni 200 belgidan oshmasin.
   - stat_callout da heading faqat raqam+birlik (masalan "2.4 mlrd" yoki "78%").

{REQUIRED_FIELDS_BY_LAYOUT}

JSON STRUKTURASI:
{{
  "topic": "...",
  "palette": {{"primary": "#RRGGBB", "secondary": "#RRGGBB", "accent": "#RRGGBB"}},
  "font_pair": {{"heading": "...", "body": "..."}},
  "motif": "numbered_badge",
  "slides": [
    {{
      "index": 1, "role": "hook", "layout_type": "title_dark",
      "title": "...", "hook_line": "...", "subtitle": "..."
    }},
    {{
      "index": 2, "role": "context", "layout_type": "icon_row_list",
      "title": "...", "body": "Kirish matni...",
      "items": [
        {{"heading": "...", "body": "..."}},
        {{"heading": "...", "body": "..."}},
        {{"heading": "...", "body": "..."}}
      ]
    }},
    {{
      "index": 3, "role": "breakdown", "layout_type": "bar_chart",
      "title": "O'sish dinamikasi",
      "body": "2019-2023 yillar orasidagi yillik o'sish sur'ati.",
      "chart_data": {{
        "x_label": "Yillar",
        "y_label": "O'sish sur'ati",
        "unit": "%",
        "points": [
          {{"label": "2019", "value": 5.8}},
          {{"label": "2020", "value": 1.9}},
          {{"label": "2021", "value": 7.4}},
          {{"label": "2022", "value": 9.1}},
          {{"label": "2023", "value": 11.3}}
        ]
      }}
    }},
    {{
      "index": 4, "role": "detail", "layout_type": "math_formula",
      "title": "Asosiy tenglamalar",
      "body": "Mavzuning matematik asoslari.",
      "math_blocks": [
        {{"formula": "F = ma", "description": "Ikkinchi harakat qonuni: kuch massa va tezlanish ko'paytmasiga teng."}},
        {{"formula": "E = 1/2 mv²", "description": "Kinetik energiya — massa va tezlik kvadratining yarmi."}}
      ]
    }},
    {{
      "index": 5, "role": "detail", "layout_type": "image_half_bleed",
      "title": "...", "body": "...",
      "image_prompt": "photorealistic image of ... detailed description in english"
    }}
  ]
}}

Real mavzuga mos, faktik jihatdan asosli, o'zbek tilida (agar foydalanuvchi boshqa til so'ramasa) yoz.
Har bir slayd uchun BARCHA MAJBURIY maydonlarni to'ldirganingga ishonch hosil qil.
"""


def _clean_json(raw: str) -> str:
    cleaned = re.sub(r"```json|```", "", raw).strip()
    return cleaned


def _call_openrouter(system_prompt: str, user_prompt: str, temperature: float = 0.9) -> dict:
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.OPENROUTER_TEXT_MODEL,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    resp = requests.post(config.OPENROUTER_URL, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    raw = data["choices"][0]["message"]["content"]
    cleaned = _clean_json(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        log.error("JSON parse xato. Xom javob: %s", raw[:2000])
        raise


def generate_brief(topic: str) -> dict:
    """Mavzu bo'yicha to'liq JSON brief generatsiya qiladi (palette, layout, matn)."""
    angle_name, angle_desc = random.choice(_NARRATIVE_ANGLES)
    user_prompt = (
        f"Mavzu: {topic}\n\n"
        f"NARRATIV BURCHAK: «{angle_name}»\n"
        f"{angle_desc}\n\n"
        "Yuqoridagi qoidalar VA bu narrativ burchakka qat'iy amal qilib, to'liq JSON brief tuz. "
        "Bu burchak butun taqdimot tuzilmasi, slaydlar ketma-ketligi va mazmuniga ta'sir qilsin. "
        "Agar mavzuda raqamlar bor bo'lsa, kamida BITTA bar_chart yoki xy_chart slayd QO'SH. "
        "Agar mavzuda ilmiy formulalar bor bo'lsa, math_formula slayd QO'SH."
    )
    return _call_openrouter(SYSTEM_PROMPT_BRIEF, user_prompt, temperature=0.92)


def regenerate_slide(topic: str, slide_json: dict, feedback: str) -> dict:
    """QA yoki grounding-check muvaffaqiyatsiz bo'lganda, faqat bitta slaydni qayta yozadi."""
    system_prompt = (
        "Sen bitta taqdimot slaydini qayta yozasan. Foydalanuvchi sizga eski slayd JSON'ini va "
        "muammoni beradi. Faqat shu slaydning yangilangan JSON'ini qaytar (boshqa hech narsa yozma). "
        "role va layout_type maydonlarini o'zgartirma, faqat matn mazmunini yaxshila. "
        "Agar layout_type='bar_chart' yoki 'xy_chart' bo'lsa, chart_data maydonini to'g'ri formatda yoz. "
        "Agar layout_type='math_formula' bo'lsa, math_blocks maydonini to'liq yoz."
    )
    user_prompt = (
        f"Mavzu: {topic}\n"
        f"Eski slayd JSON: {json.dumps(slide_json, ensure_ascii=False)}\n"
        f"Muammo: {feedback}\n"
        "Yangilangan slayd JSON'ini ber."
    )
    return _call_openrouter(system_prompt, user_prompt, temperature=0.8)
