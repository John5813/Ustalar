"""
Icon matching service for slide decoration.
Finds the best matching PNG icon for a given text string.
"""
import os
import re
import logging
from typing import Optional
from data.icons_map import ICONS_MAP

logger = logging.getLogger(__name__)

ICONS_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets', 'icons')
DEFAULT_ICON = "default.png"


def _icon_path(filename: str) -> str:
    return os.path.join(ICONS_DIR, filename)


_PNG_SIGNATURE = b'\x89PNG'

def _icon_exists(filename: str) -> bool:
    path = _icon_path(filename)
    if not os.path.isfile(path):
        return False
    try:
        with open(path, 'rb') as f:
            return f.read(4) == _PNG_SIGNATURE
    except Exception:
        return False


def find_icon_path(text: str, used: set[str] | None = None) -> Optional[str]:
    """
    Given any text (slide title, column content, keyword),
    returns the absolute path to the best matching 96x96 PNG icon.
    Falls back to default.png if nothing matches.
    Returns None only when default.png is also missing/invalid.

    Args:
        text: Text to match against the icon map.
        used: Set of already-used icon filenames (e.g. {"education.png"}).
              Matching icons in this set are skipped so icons don't repeat.
    """
    used = used or set()

    def _available(filename: str) -> bool:
        return filename not in used and _icon_exists(filename)

    if not text:
        if _available(DEFAULT_ICON):
            return _icon_path(DEFAULT_ICON)
        return None

    text_lower = text.lower()

    # 1) Try multi-word phrases first (longer matches win)
    sorted_keys = sorted(ICONS_MAP.keys(), key=len, reverse=True)
    for keyword in sorted_keys:
        if len(keyword) > 3 and keyword in text_lower:
            filename = ICONS_MAP[keyword]
            if _available(filename):
                return _icon_path(filename)

    # 2) Tokenize and match individual words
    tokens = re.split(r"[\s\-_/,;:.!?()\[\]]+", text_lower)
    for token in tokens:
        token = token.strip("'\"")
        if len(token) < 3:
            continue
        if token in ICONS_MAP:
            filename = ICONS_MAP[token]
            if _available(filename):
                return _icon_path(filename)

    # 3) Partial/substring match on tokens
    for token in tokens:
        if len(token) < 4:
            continue
        for keyword, filename in ICONS_MAP.items():
            if len(keyword) < 4:
                continue
            if token in keyword or keyword in token:
                if _available(filename):
                    return _icon_path(filename)

    # 4) Fallback to default (only if not used)
    if _available(DEFAULT_ICON):
        return _icon_path(DEFAULT_ICON)

    return None


def find_icon_path_for_column(
    keyword: str,
    content: str,
    used: set[str] | None = None,
) -> Optional[str]:
    """
    Find the best matching icon by combining keyword and content text.
    Both keyword and content contribute equally to the match.

    Args:
        keyword: Column keyword / title.
        content: Column body text.
        used: Set of already-used icon filenames to skip (deduplication).
              Pass a shared mutable set across all columns on a slide (and
              across all slides in a presentation) to avoid any repetition.
    Returns None only when default.png is also missing/invalid.
    """
    combined = f"{keyword} {content}".strip()
    return find_icon_path(combined, used=used)
