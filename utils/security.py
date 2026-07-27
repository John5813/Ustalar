"""
Security utilities for sanitizing user input
"""
import re
import logging

logger = logging.getLogger(__name__)

def sanitize_user_input(text: str, max_length: int = 200) -> str:
    """
    Sanitize user input for AI prompts to prevent injection attacks
    
    Args:
        text: Raw user input
        max_length: Maximum allowed length
        
    Returns:
        Sanitized text safe for AI prompts
    """
    if not text or not isinstance(text, str):
        return ""
    
    # 1. Remove leading/trailing whitespace
    text = text.strip()
    
    # 2. Limit length
    if len(text) > max_length:
        text = text[:max_length]
        logger.warning(f"Input truncated from {len(text)} to {max_length} characters")
    
    # 3. Remove newlines and tabs - replace with spaces
    text = text.replace('\n', ' ').replace('\t', ' ').replace('\r', ' ')
    
    # 4. Remove multiple spaces
    text = ' '.join(text.split())
    
    # 5. Escape special characters that could break prompts
    text = text.replace('"', "'")  # Replace double quotes with single quotes
    text = text.replace('`', "'")  # Replace backticks
    
    # 6. Block common prompt injection patterns (case insensitive)
    dangerous_patterns = [
        r'ignore\s+(previous|all|everything)',
        r'new\s+instructions?',
        r'system\s+prompt',
        r'forget\s+(everything|all)',
        r'you\s+are\s+now',
        r'disregard\s+(previous|all)',
        r'override\s+instructions?',
    ]
    
    text_lower = text.lower()
    for pattern in dangerous_patterns:
        if re.search(pattern, text_lower):
            logger.warning(f"Blocked potential injection attempt: {text}")
            return "Academic topic"  # Safe fallback
    
    # 7. Remove any remaining control characters
    text = ''.join(char for char in text if ord(char) >= 32 or char in ['\n', '\t'])
    
    return text

_IMAGE_BLOCKLIST = [
    # NSFW / explicit
    r'\b(nude|naked|nsfw|porn|sex|xxx|erotic|fetish)\b',
    r'\b(genital|nipple|breast|topless|pantie|underwear|lingerie)\b',
    # Violence / gore
    r'\b(gore|bloody|decapitat|behead|murder|massacre|torture|mutilat)\b',
    # Weapons aimed at people / extremism
    r'\b(suicide|terrorist|isis|nazi|swastika)\b',
    # Minors in unsafe contexts
    r'\b(child|kid|minor|underage|teen)\s+(nude|naked|sex|porn|erotic)\b',
    # Real public figures (avoid likeness misuse)
    r'\b(putin|trump|biden|zelensky|xi\s+jinping|kim\s+jong)\b',
]


def sanitize_image_prompt(prompt: str, max_length: int = 800) -> str | None:
    """Validate a prompt before sending it to an image-generation API.

    Returns the cleaned prompt, or None if it should be rejected entirely.
    Together / Fal models can produce policy-violating images and bill us for
    them; a quick blocklist + length cap catches most abuse cases before the
    request leaves the bot.
    """
    if not prompt or not isinstance(prompt, str):
        return None
    p = prompt.strip()
    if not p:
        return None
    if len(p) > max_length:
        p = p[:max_length]
    low = p.lower()
    for pat in _IMAGE_BLOCKLIST:
        if re.search(pat, low):
            logger.warning(f"Blocked image prompt: pattern={pat!r}")
            return None
    # Strip control chars and collapse whitespace.
    p = ''.join(c for c in p if ord(c) >= 32 or c in ('\n', '\t'))
    p = ' '.join(p.split())
    return p


def validate_topic_length(text: str, min_length: int = 3, max_length: int = 200) -> bool:
    """
    Validate topic/outline length
    
    Args:
        text: Input text
        min_length: Minimum allowed length
        max_length: Maximum allowed length
        
    Returns:
        True if valid, False otherwise
    """
    if not text or not isinstance(text, str):
        return False
    
    text = text.strip()
    length = len(text)
    
    return min_length <= length <= max_length
