import os
import json
import time
import logging

logger = logging.getLogger(__name__)

DOC_TOKENS: dict = {}
WEBAPP_DOMAIN: str = ""
BOT = None

_TOKEN_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "temp", "doc_tokens.json"
)
TOKEN_TTL = 1800  # 30 minutes — only used by standalone edit-file flow


def save_tokens_to_disk():
    try:
        os.makedirs(os.path.dirname(_TOKEN_FILE), exist_ok=True)
        now = time.time()
        valid = {k: v for k, v in DOC_TOKENS.items()
                 if v.get("_expires", now + 1) > now}
        with open(_TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(valid, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"save_tokens_to_disk error: {e}")


def load_tokens_from_disk():
    try:
        if not os.path.exists(_TOKEN_FILE):
            return
        with open(_TOKEN_FILE, encoding="utf-8") as f:
            data = json.load(f)
        now = time.time()
        loaded = 0
        for k, v in data.items():
            if v.get("_expires", 0) > now:
                DOC_TOKENS[k] = v
                loaded += 1
        if loaded:
            logger.info(f"Loaded {loaded} active tokens from disk")
    except Exception as e:
        logger.warning(f"load_tokens_from_disk error: {e}")
