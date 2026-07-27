import logging
import re
import os
import asyncio
import aiohttp
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

MAX_WORDS = 15000
MAX_CHARS = 60000
FETCH_TIMEOUT = 30

SUPPORTED_SCHEMES = ("http", "https")

MAX_URLS = 5

INSTRUCTIONS = {
    "uz": (
        "🌐 <b>Kitob yoki sayt manzilini yuboring</b>\n\n"
        "Istalgan ochiq sayt yoki kitob sahifasining URL manzilini yuboring — bot matnni o'qib, hujjat yaratadi.\n\n"
        "💡 <b>Bir vaqtda 5 tagacha manzil yuborishingiz mumkin</b> — har birini yangi qatorga yozing.\n\n"
        "<b>Qanday URL topish mumkin?</b>\n\n"
        "1️⃣ Brauzerda (Chrome, Safari va h.k.) istalgan saytni oching\n"
        "2️⃣ Yuqoridagi manzil satrini bosing — u ko'k rangga bo'yaladi\n"
        "3️⃣ Nusxalang (Copy) va shu yerga yuboring\n\n"
        "<b>Yaxshi ishlaydi:</b>\n"
        "✅ Wikipedia maqolalari — uz.wikipedia.org, ru.wikipedia.org\n"
        "✅ Xabar saytlari — gazeta.uz, kun.uz, bbc.com va b.\n"
        "✅ To'g'ridan PDF havolalar — https://.../.pdf\n"
        "✅ Ro'yxatdan o'tmasdan o'qiladigan har qanday sahifa\n\n"
        "<b>Ishlamaydi:</b>\n"
        "❌ YouTube, Instagram, Telegram\n"
        "❌ Parol yoki login talab qiladigan saytlar\n\n"
        "URL manzilni yuboring 👇"
    ),
    "ru": (
        "🌐 <b>Отправьте ссылку на книгу или сайт</b>\n\n"
        "Отправьте URL любой открытой страницы — бот прочитает текст и создаст документ.\n\n"
        "💡 <b>Можно отправить до 5 ссылок одновременно</b> — каждую с новой строки.\n\n"
        "<b>Как получить URL?</b>\n\n"
        "1️⃣ Откройте любой сайт в браузере (Chrome, Safari и т.д.)\n"
        "2️⃣ Нажмите на адресную строку вверху — она выделится синим\n"
        "3️⃣ Скопируйте (Copy) и отправьте сюда\n\n"
        "<b>Работает хорошо:</b>\n"
        "✅ Статьи Wikipedia — ru.wikipedia.org, uz.wikipedia.org\n"
        "✅ Новостные сайты — gazeta.uz, bbc.com, rbc.ru и др.\n"
        "✅ Прямые ссылки на PDF — https://.../.pdf\n"
        "✅ Любые страницы без регистрации\n\n"
        "<b>Не работает:</b>\n"
        "❌ YouTube, Instagram, Telegram\n"
        "❌ Сайты с паролём или логином\n\n"
        "Отправьте ссылку(и) 👇"
    ),
    "en": (
        "🌐 <b>Send a link to a book or website</b>\n\n"
        "Send the URL of any open webpage — the bot will read the text and create a document.\n\n"
        "💡 <b>You can send up to 5 links at once</b> — put each on a new line.\n\n"
        "<b>How to get a URL?</b>\n\n"
        "1️⃣ Open any website in your browser (Chrome, Safari, etc.)\n"
        "2️⃣ Tap the address bar at the top — it will highlight\n"
        "3️⃣ Copy it and send it here\n\n"
        "<b>Works well with:</b>\n"
        "✅ Wikipedia articles — en.wikipedia.org\n"
        "✅ News sites — bbc.com, cnn.com, and others\n"
        "✅ Direct PDF links — https://.../.pdf\n"
        "✅ Any page accessible without login\n\n"
        "<b>Does not work:</b>\n"
        "❌ YouTube, Instagram, Telegram\n"
        "❌ Sites requiring a password or login\n\n"
        "Send link(s) 👇"
    ),
}


def extract_urls_from_text(text: str) -> list[str]:
    """Extract up to MAX_URLS valid-looking URLs from a multi-line message."""
    urls = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("http://") or line.startswith("https://"):
            urls.append(line)
            if len(urls) >= MAX_URLS:
                break
    return urls


async def fetch_multiple_urls(urls: list[str]) -> dict:
    """
    Fetch and combine text from multiple URLs in parallel.

    Returns:
        {
            "combined_content": str,
            "total_word_count": int,
            "results": list of {"url": str, "title": str, "word_count": int, "ok": bool, "error": str}
        }
    """
    tasks = [fetch_book_from_url(url) for url in urls]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    parts = []
    results = []
    total_words = 0

    for url, res in zip(urls, raw_results):
        if isinstance(res, Exception):
            reason = str(res) if isinstance(res, ValueError) else "fetch_failed"
            results.append({"url": url, "title": url, "word_count": 0, "ok": False, "error": reason})
        else:
            parts.append(res["content"])
            total_words += res["word_count"]
            results.append({"url": url, "title": res["title"], "word_count": res["word_count"], "ok": True, "error": ""})

    combined = "\n\n---\n\n".join(parts)
    if len(combined) > MAX_CHARS:
        combined = combined[:MAX_CHARS]

    return {
        "combined_content": combined,
        "total_word_count": total_words,
        "results": results,
    }

BLOCKED_DOMAINS = (
    "youtube.com", "youtu.be",
    "instagram.com", "facebook.com", "twitter.com", "x.com",
    "tiktok.com", "vk.com", "ok.ru",
    "netflix.com", "spotify.com",
)


def validate_url(url: str) -> tuple[bool, str]:
    """Return (ok, error_reason). error_reason is empty string if ok."""
    url = url.strip()
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "parse_error"

    if parsed.scheme not in SUPPORTED_SCHEMES:
        return False, "bad_scheme"

    if not parsed.netloc:
        return False, "no_host"

    domain = parsed.netloc.lower().lstrip("www.")
    for blocked in BLOCKED_DOMAINS:
        if domain == blocked or domain.endswith("." + blocked):
            return False, "blocked_domain"

    return True, ""


def _extract_text_from_html(html: str) -> tuple[str, str]:
    """Extract main text and title from HTML using BeautifulSoup."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    title = ""
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)

    for tag in soup(["script", "style", "nav", "footer", "header",
                     "aside", "advertisement", "noscript", "form",
                     "button", "input", "select", "textarea"]):
        tag.decompose()

    main = (
        soup.find("article") or
        soup.find("main") or
        soup.find(id=re.compile(r"content|article|main|body", re.I)) or
        soup.find(class_=re.compile(r"content|article|main|body|text", re.I)) or
        soup.find("body") or
        soup
    )

    text = main.get_text(separator="\n", strip=True)

    lines = []
    for line in text.splitlines():
        line = line.strip()
        if len(line) > 20:
            lines.append(line)

    return "\n\n".join(lines), title


async def _fetch_pdf_text(url: str) -> tuple[str, str]:
    """Download PDF from URL and extract text using PyMuPDF (fitz)."""
    import tempfile
    import fitz

    tmp_path = None
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; EduBot/1.0)"}
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=FETCH_TIMEOUT),
                headers=headers,
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    raise ValueError(f"HTTP {resp.status}")
                content_len = resp.headers.get("Content-Length")
                if content_len and int(content_len) > 20 * 1024 * 1024:
                    raise ValueError("pdf_too_large")
                data = await resp.read()
                if len(data) > 20 * 1024 * 1024:
                    raise ValueError("pdf_too_large")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
            f.write(data)
            tmp_path = f.name

        doc = fitz.open(tmp_path)
        pages_text = []
        word_count = 0
        for page in doc:
            text = page.get_text().strip()
            if text:
                pages_text.append(text)
                word_count += len(text.split())
                if word_count >= MAX_WORDS:
                    break
        doc.close()

        raw_text = "\n\n".join(pages_text)
        if not raw_text or word_count < 30:
            raise ValueError("empty_pdf")

        title = url.split("/")[-1].replace(".pdf", "").replace("-", " ").replace("_", " ")[:100]
        return raw_text, title

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


async def _fetch_html_text(url: str) -> tuple[str, str]:
    """Fetch HTML page and extract text."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "uz,ru;q=0.9,en;q=0.8",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=FETCH_TIMEOUT),
            headers=headers,
            allow_redirects=True,
        ) as resp:
            if resp.status != 200:
                raise ValueError(f"HTTP {resp.status}")
            content_type = resp.headers.get("Content-Type", "").lower()
            if "pdf" in content_type:
                raise ValueError("redirect_to_pdf")
            html = await resp.text(errors="replace")

    return _extract_text_from_html(html)


async def fetch_book_from_url(url: str) -> dict:
    """
    Fetch and extract text from a URL.

    Returns:
        {
            "title": str,
            "content": str,
            "word_count": int,
        }

    Raises:
        ValueError with a key:
            "bad_scheme", "no_host", "blocked_domain",
            "fetch_failed", "too_short", "pdf_too_large", "empty_pdf"
    """
    url = url.strip()
    ok, reason = validate_url(url)
    if not ok:
        raise ValueError(reason)

    parsed = urlparse(url)
    is_pdf = parsed.path.lower().endswith(".pdf")

    try:
        if is_pdf:
            text, title = await _fetch_pdf_text(url)
        else:
            text, title = await _fetch_html_text(url)
    except ValueError:
        raise
    except asyncio.TimeoutError:
        raise ValueError("fetch_failed")
    except Exception as e:
        logger.warning(f"URL fetch error for {url}: {e}")
        raise ValueError("fetch_failed")

    text = text.strip()
    if not text or len(text.split()) < 30:
        raise ValueError("too_short")

    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]

    words = text.split()
    if len(words) > MAX_WORDS:
        words = words[:MAX_WORDS]
        text = " ".join(words)

    word_count = len(text.split())

    if not title:
        title = parsed.netloc + parsed.path
    title = title[:120]

    return {
        "title": title,
        "content": text,
        "word_count": word_count,
    }


def get_error_message(reason: str, lang: str) -> str:
    msgs = {
        "uz": {
            "bad_scheme":     "❌ URL noto'g'ri. <code>https://</code> bilan boshlanishi kerak.",
            "no_host":        "❌ URL noto'g'ri formatda. To'liq manzil yuboring.",
            "blocked_domain": "❌ Bu sayt qo'llab-quvvatlanmaydi (YouTube, Instagram va h.k.).",
            "fetch_failed":   "❌ Sahifani ochib bo'lmadi. Sayt bloklanganmi yoki URL noto'g'rimi?",
            "too_short":      "❌ Sahifada o'qiladigan matn topilmadi. Boshqa URL yuboring.",
            "pdf_too_large":  "❌ PDF fayl juda katta (20 MB dan oshiq). Kichikroq fayl yuboring.",
            "empty_pdf":      "❌ PDF dan matn ajratib bo'lmadi. Skanerlangan rasm bo'lishi mumkin.",
            "parse_error":    "❌ URL noto'g'ri. To'liq manzilni nusxalab yuboring.",
        },
        "ru": {
            "bad_scheme":     "❌ Неверный URL. Должен начинаться с <code>https://</code>.",
            "no_host":        "❌ Неверный формат URL. Отправьте полный адрес.",
            "blocked_domain": "❌ Этот сайт не поддерживается (YouTube, Instagram и т.д.).",
            "fetch_failed":   "❌ Не удалось открыть страницу. Сайт заблокирован или URL неверный?",
            "too_short":      "❌ На странице не найден читаемый текст. Попробуйте другой URL.",
            "pdf_too_large":  "❌ PDF слишком большой (более 20 МБ). Отправьте файл поменьше.",
            "empty_pdf":      "❌ Не удалось извлечь текст из PDF. Возможно, это сканированное изображение.",
            "parse_error":    "❌ Неверный URL. Скопируйте и отправьте полный адрес.",
        },
        "en": {
            "bad_scheme":     "❌ Invalid URL. Must start with <code>https://</code>.",
            "no_host":        "❌ Invalid URL format. Send the full address.",
            "blocked_domain": "❌ This site is not supported (YouTube, Instagram, etc.).",
            "fetch_failed":   "❌ Could not open the page. Is the site blocked or is the URL wrong?",
            "too_short":      "❌ No readable text found on the page. Try a different URL.",
            "pdf_too_large":  "❌ PDF is too large (over 20 MB). Please use a smaller file.",
            "empty_pdf":      "❌ Could not extract text from PDF. It may be a scanned image.",
            "parse_error":    "❌ Invalid URL. Copy and send the full address.",
        },
    }
    lang_msgs = msgs.get(lang, msgs["uz"])
    return lang_msgs.get(reason, lang_msgs["fetch_failed"])
