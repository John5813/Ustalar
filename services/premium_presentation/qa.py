import base64
import glob
import json
import logging
import os
import re
import subprocess
import uuid

import requests

from . import config

log = logging.getLogger("qa")


def pptx_to_images(pptx_path: str) -> list[str]:
    """LibreOffice + pdftoppm orqali har slaydni JPG'ga aylantiradi."""
    work_dir = os.path.join(config.WORK_DIR, f"qa_{uuid.uuid4().hex[:8]}")
    os.makedirs(work_dir, exist_ok=True)

    try:
        subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf", "--outdir", work_dir, pptx_path],
            check=True, timeout=120, capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log.error("LibreOffice mavjud emas yoki xato: %s", e)
        return []

    pdf_path = os.path.join(work_dir, os.path.splitext(os.path.basename(pptx_path))[0] + ".pdf")
    if not os.path.exists(pdf_path):
        log.error("PDF konvertatsiya muvaffaqiyatsiz: %s", pdf_path)
        return []

    try:
        subprocess.run(
            ["pdftoppm", "-jpeg", "-r", "150", pdf_path, os.path.join(work_dir, "slide")],
            check=True, timeout=120, capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log.error("pdftoppm mavjud emas yoki xato: %s", e)
        return []

    images = sorted(glob.glob(os.path.join(work_dir, "slide-*.jpg")))
    return images


def _b64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def check_slide_image(image_path: str, slide_context: str) -> dict:
    """Vision model orqali bitta slayd skrinshotini qat'iy mezon bo'yicha tekshiradi."""
    if not config.OPENROUTER_API_KEY:
        return {"ok": True, "issue": "", "remove": None}

    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = f"""Professional taqdimot slaydini QATTIQ va HALOL baholа. Har bir muammoni aniq ko'rsat.

MEZONLAR (birontasi buzilsa — ok:false):

1. MATN O'LCHAMI
   Sarlavha ≥ 28pt, kichik sarlavha ≥ 16pt, tana matni ≥ 13pt bo'lishi SHART.
   Juda kichik, o'qilmaydigan matn ko'rsak — ok:false.

2. MATN USTMA-UST (ENG MUHIM)
   Ikki yoki undan ko'p matn bloki bir-birining ustiga chiqib, matn o'qilmay qolibdimi?
   Agar ha — ok:false, muammoni aniq yoz: qaysi matnlar ustma-ust chiqqan.

3. KONTRAST
   To'q fon ustida to'q matn — o'qish qiyinmi? Agar ha — ok:false.
   Och fon ustida och matn — ko'rinmayaptimi? Agar ha — ok:false.

4. BO'SH JOY
   Slayd maydonining 40%+ bo'sh yoki mazmunsizmi? — ok:false.

5. PROFESSIONAL KO'RINISH
   Teatral, bolalarcha, bezak uchun bezak elementlar? — ok:false.

6. TOSHIB KETISH
   Matn yoki element slayd chegarasidan tashqariga chiqibdimi? — ok:false.

7. KERAKSIZ ELEMENT
   Mavzu {slide_context} uchun diagramma (chart) mantiqsizmi?
   Masalan: falsafiy, adabiy, his-tuyg'u mavzusida bema'ni diagramma — ok:false, remove:"chart".
   Mavzuga aloqasiz yoki sifatsiz rasm — ok:false, remove:"image".

Slayd konteksti: {slide_context}

MUHIM: Har qanday aniq muammoda ok:false qaytar. "Yaxshi ko'rinadi" — etarli emas.
Faqat JSON: {{"ok": true/false, "issue": "aniq muammo tavsifi yoki bo'sh", "remove": null}}"""

    payload = {
        "model": config.OPENROUTER_VISION_MODEL,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{_b64(image_path)}",
                        "detail": "high"
                    }},
                ],
            }
        ],
    }
    try:
        resp = requests.post(config.OPENROUTER_URL, headers=headers, json=payload, timeout=90)
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
        cleaned = re.sub(r"```json|```", "", raw).strip()
        result = json.loads(cleaned)
        log.info("Vision QA: ok=%s | %s", result.get("ok"), result.get("issue", "")[:120])
        return result
    except Exception as e:
        log.error("Vision QA xatosi: %s", e)
        return {"ok": True, "issue": "", "remove": None}
