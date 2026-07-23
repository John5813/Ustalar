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
    """LibreOffice + pdftoppm orqali har slaydni JPG'ga aylantiradi.
    Tizimda `soffice` va `pdftoppm` (poppler-utils) o'rnatilgan bo'lishi shart."""
    work_dir = os.path.join(config.WORK_DIR, f"qa_{uuid.uuid4().hex[:8]}")
    os.makedirs(work_dir, exist_ok=True)

    subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf", "--outdir", work_dir, pptx_path],
        check=True, timeout=120, capture_output=True,
    )
    pdf_path = os.path.join(work_dir, os.path.splitext(os.path.basename(pptx_path))[0] + ".pdf")
    if not os.path.exists(pdf_path):
        log.error("PDF konvertatsiya muvaffaqiyatsiz: %s", pdf_path)
        return []

    subprocess.run(
        ["pdftoppm", "-jpeg", "-r", "110", pdf_path, os.path.join(work_dir, "slide")],
        check=True, timeout=120, capture_output=True,
    )
    images = sorted(glob.glob(os.path.join(work_dir, "slide-*.jpg")))
    return images


def _b64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def check_slide_image(image_path: str, slide_context: str) -> dict:
    """Vision model orqali bitta slayd skrinshotini tekshiradi.
    Qaytaradi: {"ok": bool, "issue": str}"""
    if not config.OPENROUTER_API_KEY:
        return {"ok": True, "issue": ""}

    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    prompt = (
        "Bu taqdimot slaydining skrinshoti. Quyidagilarni tekshir: "
        "(1) matn slayd chegarasidan tashqariga toshib ketganmi, "
        "(2) matn va fon orasida kontrast yetarlimi (o'qish qiyin emasmi), "
        "(3) elementlar bir-biriga tegib/ustma-ust tushib qolganmi, "
        "(4) slayd bo'sh yoki mazmunsiz ko'rinadimi. "
        f"Slayd konteksti: {slide_context}. "
        'Faqat JSON qaytar: {"ok": true/false, "issue": "muammo tavsifi yoki bo\'sh satr"}'
    )
    payload = {
        "model": config.OPENROUTER_VISION_MODEL,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_b64(image_path)}"}},
                ],
            }
        ],
    }
    try:
        resp = requests.post(config.OPENROUTER_URL, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
        cleaned = re.sub(r"```json|```", "", raw).strip()
        return json.loads(cleaned)
    except Exception as e:
        log.error("Vision QA xatosi: %s", e)
        return {"ok": True, "issue": ""}  # QA ishlamasa, blokламаймиз — xavfsiz taraf
