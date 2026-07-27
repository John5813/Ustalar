import os

# OpenRouter API kaliti — OPENROUTER_API_KEY yoki AI_INTEGRATIONS_OPENROUTER_API_KEY
OPENROUTER_API_KEY = (
    os.getenv("OPENROUTER_API_KEY")
    or os.getenv("AI_INTEGRATIONS_OPENROUTER_API_KEY")
    or ""
)

# Together AI rasm generatsiyasi uchun
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY", "")

# Modellar
OPENROUTER_TEXT_MODEL = os.getenv("OPENROUTER_TEXT_MODEL", "moonshotai/kimi-k3")
OPENROUTER_VISION_MODEL = os.getenv("OPENROUTER_VISION_MODEL", "google/gemini-2.5-flash")
TOGETHER_IMAGE_MODEL = os.getenv("TOGETHER_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell")

# QA urinishlari soni
MAX_QA_RETRIES = int(os.getenv("MAX_QA_RETRIES", "1"))

# Vaqtinchalik fayllar papkasi
WORK_DIR = os.getenv("WORK_DIR", "/tmp/ppt_premium_work")

# API endpointlar
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
TOGETHER_IMAGE_URL = "https://api.together.xyz/v1/images/generations"
