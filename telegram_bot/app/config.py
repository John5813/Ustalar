import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY", "")

# Matn/JSON generatsiyasi uchun model (structured-output'ni yaxshi ushlaydigan kuchli model tanlang)
OPENROUTER_TEXT_MODEL = os.getenv("OPENROUTER_TEXT_MODEL", "anthropic/claude-sonnet-4.6")

# Slayd skrinshotlarini "ko'rib" sifat nazoratini qiladigan vision model
OPENROUTER_VISION_MODEL = os.getenv("OPENROUTER_VISION_MODEL", "anthropic/claude-sonnet-4.6")

# Together AI rasm modeli
# FLUX.1-schnell-Free dedicated endpoint talab qiladi — serverless versiya: FLUX.1-schnell
TOGETHER_IMAGE_MODEL = os.getenv("TOGETHER_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell")

# Har taqdimot uchun QA-tuzatish (regenerate) urinishlari soni
MAX_QA_RETRIES = int(os.getenv("MAX_QA_RETRIES", "2"))

# Vaqtinchalik fayllar papkasi
WORK_DIR = os.getenv("WORK_DIR", "/tmp/ppt_bot_work")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
TOGETHER_IMAGE_URL = "https://api.together.xyz/v1/images/generations"
