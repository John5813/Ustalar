import base64
import logging
import os
import time
import uuid

import requests

from . import config

log = logging.getLogger("image_client")


def generate_image(prompt: str, retries: int = 3) -> str | None:
    """Together AI orqali rasm generatsiya qiladi, local faylga saqlaydi va yo'lini qaytaradi.
    Xato bo'lsa retry qiladi, oxirida None qaytaradi."""
    if not config.TOGETHER_API_KEY:
        log.warning("TOGETHER_API_KEY yo'q, rasm generatsiyasi o'tkazib yuborildi")
        return None

    headers = {
        "Authorization": f"Bearer {config.TOGETHER_API_KEY}",
        "Content-Type": "application/json",
    }
    # Eslatma: response_format="b64_json" ko'pgina modelda ishlamaydi —
    # Together AI odatda URL qaytaradi. Shu sababli response_format berilmaydi.
    payload = {
        "model": config.TOGETHER_IMAGE_MODEL,
        "prompt": prompt,
        "width": 1024,
        "height": 768,
        "steps": 4,
        "n": 1,
    }

    for attempt in range(1, retries + 1):
        try:
            log.info("Together AI chaqirilmoqda (urinish %s/%s): %s", attempt, retries, prompt[:120])
            resp = requests.post(
                config.TOGETHER_IMAGE_URL,
                headers=headers,
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()

            items = data.get("data") or []
            if not items:
                log.error("Together javobida 'data' bo'sh: %s", str(data)[:400])
                break

            item = items[0]
            os.makedirs(config.WORK_DIR, exist_ok=True)
            out_path = os.path.join(config.WORK_DIR, f"img_{uuid.uuid4().hex[:10]}.png")

            # b64_json ustuvor (ba'zi modellarda bo'ladi)
            b64 = item.get("b64_json") or ""
            if b64:
                img_bytes = base64.b64decode(b64)
                with open(out_path, "wb") as f:
                    f.write(img_bytes)
                log.info("Rasm saqlandi (b64): %s", out_path)
                return out_path

            # URL orqali yuklash — redirect'larni kuzatib boradi
            url = item.get("url") or ""
            if url:
                img_resp = requests.get(
                    url,
                    timeout=90,
                    allow_redirects=True,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                img_resp.raise_for_status()
                content = img_resp.content
                if not content:
                    log.error("URL orqali olingan rasm bo'sh: %s", url)
                    if attempt < retries:
                        time.sleep(2 * attempt)
                        continue
                    break
                with open(out_path, "wb") as f:
                    f.write(content)
                log.info("Rasm saqlandi (url): %s | hajm: %s bayt", out_path, len(content))
                return out_path

            log.error("Together javobida na b64_json na url topildi: %s", item)
            break

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "?"
            body = e.response.text[:300] if e.response else ""
            log.warning("Together HTTP %s xato (urinish %s/%s): %s | %s", status, attempt, retries, e, body)
            if status == 429:
                wait = 5 * attempt
                log.info("Rate limit — %ss kutilmoqda", wait)
                time.sleep(wait)
                continue
            # 400 (model_not_available) va boshqa 4xx — qayta urinish foydasiz
            log.error("Qayta urinish bekor: HTTP %s", status)
            break
        except Exception as e:
            log.warning("Together xato (urinish %s/%s): %s", attempt, retries, e)
            if attempt < retries:
                time.sleep(2 * attempt)

    log.error("Rasm generatsiyasi %s urinishdan keyin ham muvaffaqiyatsiz: '%s'", retries, prompt[:80])
    return None
