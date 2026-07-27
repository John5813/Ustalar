import logging
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import string
import random

logger = logging.getLogger(__name__)

def generate_random_code(length: int = 8) -> str:
    """Generate random alphanumeric code"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def format_balance(amount: int) -> str:
    """Format balance amount with thousands separator"""
    return f"{amount:,}"

def format_datetime(dt: datetime) -> str:
    """Format datetime for display"""
    return dt.strftime("%d.%m.%Y %H:%M")

def format_date(dt: datetime) -> str:
    """Format date for display"""
    return dt.strftime("%d.%m.%Y")

def is_valid_channel_id(channel_id: str) -> bool:
    """Validate Telegram channel ID format"""
    return channel_id.startswith("-100") and len(channel_id) >= 10

def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text to specified length"""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."

def sanitize_filename(filename: str) -> str:
    """Sanitize filename by removing invalid characters"""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    return filename

def calculate_document_sections(min_pages: int, max_pages: int, document_type: str) -> int:
    """Calculate number of sections based on page count and document type"""
    if document_type == "independent_work":
        if max_pages <= 15:
            return 6
        elif max_pages <= 20:
            return 9
        elif max_pages <= 25:
            return 12
        else:
            return 15
    elif document_type == "referat":
        if max_pages <= 10:
            return 4
        elif max_pages <= 12:
            return 5
        else:
            return 6
    else:
        return 5  # default

def validate_topic(topic: str) -> bool:
    """Validate topic input"""
    if not topic or len(topic.strip()) < 3:
        return False
    if len(topic.strip()) > 200:
        return False
    return True

def get_slide_image_positions(slide_count: int) -> List[int]:
    """Get positions for slides that should have images (1, 3, 6, 9, etc.)"""
    positions = [1, 3, 6, 9, 12, 15, 18, 21, 24, 27, 30]
    return [pos for pos in positions if pos <= slide_count]

def format_user_link(username: Optional[str], telegram_id: int, first_name: Optional[str] = None) -> str:
    """Format user link for admin messages"""
    if username:
        return f"@{username}"
    elif first_name:
        return f"[{first_name}](tg://user?id={telegram_id})"
    else:
        return f"[User](tg://user?id={telegram_id})"

def parse_page_range(page_range_str: str) -> tuple:
    """Parse page range string like '10_15' to (10, 15)"""
    try:
        parts = page_range_str.split('_')
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return 10, 15  # default

def get_document_price(document_type: str, count_data: dict = None) -> int:
    """Get price for document type and parameters"""
    from config import PRESENTATION_PRICES, DOCUMENT_PRICES
    
    if document_type == "presentation":
        slide_count = count_data.get('slide_count', 10) if count_data else 10
        return PRESENTATION_PRICES.get(slide_count, 5000)
    elif document_type in ["independent_work", "referat"]:
        if count_data:
            min_pages = count_data.get('min_pages', 10)
            max_pages = count_data.get('max_pages', 15)
            page_key = f"{min_pages}_{max_pages}"
        else:
            page_key = "10_15"  # default
        return DOCUMENT_PRICES.get(page_key, 5000)
    
    return 5000  # default price

def is_promocode_expired(expires_at: datetime) -> bool:
    """Check if promocode is expired"""
    return datetime.now() > expires_at

def calculate_broadcast_delay(total_users: int) -> float:
    """Calculate delay between broadcast messages to avoid rate limits"""
    # Telegram allows ~30 messages per second for bots
    # Add small delay to be safe
    if total_users > 100:
        return 0.05  # 50ms delay
    return 0.03  # 30ms delay

async def safe_send_message(bot, chat_id: int, text: str, **kwargs) -> bool:
    """Safely send message with error handling"""
    try:
        await bot.send_message(chat_id, text, **kwargs)
        return True
    except Exception as e:
        logger.error(f"Failed to send message to {chat_id}: {e}")
        return False

def validate_payment_amount(amount: int) -> bool:
    """Validate payment amount"""
    # Valid payment amounts based on keyboard options
    valid_amounts = [15000, 25000, 50000, 100000]
    return amount in valid_amounts

def clean_html_tags(text: str) -> str:
    """Remove HTML tags from text"""
    import re
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text)

def split_long_message(text: str, max_length: int = 4000) -> List[str]:
    """Split long message into chunks"""
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        
        # Find last newline within limit
        cut_point = text.rfind('\n', 0, max_length)
        if cut_point == -1:
            cut_point = max_length
        
        chunks.append(text[:cut_point])
        text = text[cut_point:].lstrip('\n')
    
    return chunks

def get_progress_bar(current: int, total: int, length: int = 20) -> str:
    """Generate progress bar string"""
    if total == 0:
        return "▓" * length
    
    filled = int(length * current / total)
    return "█" * filled + "░" * (length - filled)

def escape_markdown(text: str) -> str:
    """Escape markdown special characters"""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text
