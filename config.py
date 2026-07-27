import os

# Bot configuration - no default values for security
BOT_TOKEN = os.getenv("BOT_TOKEN")
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
FAL_API_KEY = os.getenv("FAL_API_KEY")

# Telegram Stars conversion rate: 1 Star ≈ 165 so'm (bot developer receive rate)
STARS_RATE = 165

# Media generation prices (in so'm)
IMAGE_PRICE = 2000
IMAGE_EDIT_PRICE = 2000

# Legacy single-model video prices (kept for backward compat)
VIDEO_PRICES = {5: 5000, 10: 10000}

# Per-model video prices (in so'm) — always max duration:
# Grok Video:   $0.10/s × 10s = $1.00 → 12,500 som → charge 18,000
# Veo 3.1:      $0.15/s × 10s = $1.50 → 18,750 som → charge 26,000
# Kling v3 Pro: $0.14/s × 10s = $1.40 → 17,500 som → charge 24,000
VIDEO_MODEL_PRICES = {
    "grok":  18_000,
    "veo":   26_000,
    "kling": 24_000,
}
IMG2VIDEO_PRICE = 13_000
VID2VID_PRICE = 5000

def som_to_stars(price_som: int) -> int:
    """Convert som price to equivalent Telegram Stars (ceiling)"""
    import math
    return math.ceil(price_som / STARS_RATE)

# Validate required environment variables
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")
# TOGETHER_API_KEY is optional - images won't be generated if not provided

# Admin configuration
ADMIN_IDS = list(map(int, filter(None, os.getenv("ADMIN_IDS", "5304482470").split(",")))) if os.getenv("ADMIN_IDS") else [5304482470]

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot.db")

# Payment configuration
PAYMENT_CARD = os.getenv("PAYMENT_CARD", "9860160606136655")
PAYMENT_CARD_2 = os.getenv("PAYMENT_CARD_2", "9860160104562378")
PAYMENT_CARD_OWNER = os.getenv("PAYMENT_CARD_OWNER", "Moʻydinov Javlonbek")

# Payment amounts with descriptions (for reference - actual values in keyboards.py)
PAYMENT_OPTIONS_REFERENCE = [
    (10000, "10,000 so'm"),
    (15000, "15,000 so'm"),
    (20000, "20,000 so'm"),
    (25000, "25,000 so'm")
]

# PDF to DOCX conversion prices (in som) based on page count
PDF_CONVERT_PRICES = {
    "1_30": 5000,
    "31_100": 10000,
    "101_plus": 20000,
}

# Book translation prices (in som) based on word count
BOOK_TRANSLATE_PRICES = {
    5000: 15_000,
    15000: 30_000,
    40000: 60_000,
    999999999: 100_000,
}

# Article prices (in som)
ARTICLE_PRICES = {
    "4_5": 5000,
    "5_7": 7000,
    "7_10": 10000,
}

# Dynamic pricing based on slide/page count (in som)
PRESENTATION_PRICES = {
    10: 5000,
    15: 7000,
    20: 10000
}

DOCUMENT_PRICES = {
    "10_15": 5000,
    "15_20": 7000,
    "20_25": 10000,
    "25_30": 12000,
    "tezis": 5000
}

# Course work prices (with chapters)
COURSE_WORK_PRICES = {
    "15_20_3": 10000,
    "20_25_3": 15000,
    "25_30_3": 20000,
    "30_35_3": 25000
}

# Diploma work prices (same structure as course work)
DIPLOMA_WORK_PRICES = {
    "15_20_2": 10000,
    "20_25_2": 15000,
    "25_30_3": 20000,
    "30_35_3": 25000
}

# Graduation qualifying work prices (bitiruv malakaviy ishi)
GRADUATION_WORK_PRICES = {
    "30_40_3": 35000,
    "40_50_3": 50000,
    "50_60_3": 65000,
    "60_70_3": 80000,
}

# Master's dissertation prices (Magistrlik dissertatsiyasi)
DISSERTATION_PRICES = {
    "60_70_3":  90000,
    "70_80_3":  110000,
    "80_90_4":  140000,
    "90_100_4": 170000,
}

# Extras prices (in so'm) added on top of base document price
EXTRAS_PRICES = {
    "formulas":   1000,
    "images":     2000,
    "tables":     1000,
    "glossary":   1000,
    "statistics": 1000,
}

# AI configuration (DeepSeek via OpenRouter)
AI_INTEGRATIONS_OPENROUTER_API_KEY = os.getenv("AI_INTEGRATIONS_OPENROUTER_API_KEY")
AI_INTEGRATIONS_OPENROUTER_BASE_URL = os.getenv("AI_INTEGRATIONS_OPENROUTER_BASE_URL")

MAX_TOKENS = 4000
TEMPERATURE = 0.7

# Available AI Models for OpenRouter (samarali modellar)
AI_MODELS = {
    "gemini_25_flash": {
        "id": "google/gemini-2.5-flash",
        "name": "Gemini 2.5 Flash",
        "price": "$0.30/1M",
        "description": "Tez va yuqori sifatli"
    },
    "gemini_25_flash_lite": {
        "id": "google/gemini-2.5-flash-lite",
        "name": "Gemini 2.5 Flash Lite",
        "price": "$0.10/1M",
        "description": "Eng tez, arzon"
    },
    "gemini_20_flash": {
        "id": "google/gemini-2.0-flash-001",
        "name": "Gemini 2.0 Flash",
        "price": "$0.10/1M",
        "description": "Tez, ishonchli"
    },
    "gpt_4o_mini": {
        "id": "openai/gpt-4o-mini",
        "name": "GPT-4o Mini",
        "price": "$0.15/1M",
        "description": "OpenAI, tez va aqlli"
    },
    "claude_haiku": {
        "id": "anthropic/claude-3.5-haiku",
        "name": "Claude 3.5 Haiku",
        "price": "$0.80/1M",
        "description": "Sifatli, aniq javoblar"
    },
    "qwen3_14b": {
        "id": "qwen/qwen3-14b",
        "name": "Qwen3 14B",
        "price": "$0.06/1M",
        "description": "Eng arzon, yaxshi sifat"
    },
    "llama_33_70b": {
        "id": "meta-llama/llama-3.3-70b-instruct",
        "name": "Llama 3.3 70B",
        "price": "$0.10/1M",
        "description": "Open-source, kuchli"
    }
}

# Default AI model
DEFAULT_AI_MODEL = "gemini_25_flash"

# File paths
DOCUMENTS_DIR = "generated_documents"
TEMP_DIR = "temp"

# Ensure directories exist
os.makedirs(DOCUMENTS_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
