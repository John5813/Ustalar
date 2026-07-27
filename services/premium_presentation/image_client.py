import base64
import logging
import os
import random
import time
import uuid

import requests

from . import config

log = logging.getLogger("image_client")

# Professional photography prefix — sifatni oshiradi
_QUALITY_PREFIX = (
    "professional photography, photorealistic, sharp focus, high detail, "
    "8k resolution, natural lighting, clean composition, "
)


def _build_prompt(raw_prompt: str) -> str:
    """AI bergan promptga professional sifat prefiksi qo'shadi."""
    return _QUALITY_PREFIX + raw_prompt.strip()


def generate_image(prompt: str, retries: int = 3) -> str | None:
    """Together AI orqali sifatli rasm generatsiya qiladi."""
    if not config.TOGETHER_API_KEY:
        log.warning("TOGETHER_API_KEY yo'q, rasm generatsiyasi o'tkazib yuborildi")
        return None

    enhanced_prompt = _build_prompt(prompt)
    log.info("Rasm so'rovi: %s", enhanced_prompt[:160])

    headers = {
        "Authorization": f"Bearer {config.TOGETHER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.TOGETHER_IMAGE_MODEL,
        "prompt": enhanced_prompt,
        "width": 1280,
        "height": 832,
        "steps": 10,          # 4 → 10: sezilarli sifat oshishi
        "n": 1,
        "seed": random.randint(1, 999999),
    }

    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(
                config.TOGETHER_IMAGE_URL,
                headers=headers,
                json=payload,
                timeout=150,
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

            # b64_json ustuvor
            b64 = item.get("b64_json") or ""
            if b64:
                img_bytes = base64.b64decode(b64)
                with open(out_path, "wb") as f:
                    f.write(img_bytes)
                log.info("Rasm saqlandi (b64): %s", out_path)
                return out_path

            # URL orqali yuklash
            url = item.get("url") or ""
            if url:
                img_resp = requests.get(
                    url, timeout=90, allow_redirects=True,
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
                log.info("Rasm saqlandi (url): %s | %s bayt", out_path, len(content))
                return out_path

            log.error("Together javobida na b64_json na url: %s", item)
            break

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "?"
            body = e.response.text[:300] if e.response else ""
            log.warning("Together HTTP %s (urinish %s/%s): %s | %s", status, attempt, retries, e, body)
            if status == 429:
                wait = 5 * attempt
                log.info("Rate limit — %ss kutilmoqda", wait)
                time.sleep(wait)
                continue
            log.error("Qayta urinish bekor: HTTP %s", status)
            break
        except Exception as e:
            log.warning("Together xato (urinish %s/%s): %s", attempt, retries, e)
            if attempt < retries:
                time.sleep(2 * attempt)

    log.error("Rasm generatsiyasi %s urinishdan keyin muvaffaqiyatsiz: '%s'", retries, prompt[:80])
    return None


