import os
import asyncio
import logging
import uuid

from config import TEMP_DIR

logger = logging.getLogger(__name__)


def _get_pdf_page_count(file_path: str) -> int:
    """Return approximate page count from a PDF using PyMuPDF (fitz)."""
    try:
        import fitz
        doc = fitz.open(file_path)
        count = doc.page_count
        doc.close()
        return count
    except Exception as e:
        logger.warning(f"Could not count PDF pages: {e}")
        return 0


def _convert_pdf_sync(input_path: str, output_path: str) -> None:
    """Blocking PDF → DOCX conversion using pdf2docx."""
    from pdf2docx import Converter
    cv = Converter(input_path)
    cv.convert(output_path, start=0, end=None)
    cv.close()


async def convert_pdf_to_docx(file_path: str) -> str:
    """
    Convert a PDF file to DOCX asynchronously.

    Args:
        file_path: Absolute path to the input PDF file.

    Returns:
        Absolute path to the resulting DOCX file (stored in TEMP_DIR).

    Raises:
        Exception: If conversion fails.
    """
    os.makedirs(TEMP_DIR, exist_ok=True)
    out_name = f"converted_{uuid.uuid4().hex[:10]}.docx"
    out_path = os.path.join(TEMP_DIR, out_name)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _convert_pdf_sync, file_path, out_path)

    if not os.path.exists(out_path):
        raise FileNotFoundError(f"Conversion output not found: {out_path}")

    return out_path


def get_pdf_page_count(file_path: str) -> int:
    """Return page count of a PDF (synchronous, safe wrapper)."""
    return _get_pdf_page_count(file_path)


def get_pdf_info(file_path: str) -> dict:
    """Fast PDF scan using PyMuPDF: returns page count, estimated word count, source language.
    
    No DOCX conversion needed — fitz extracts text directly from PDF.
    Returns dict with keys: total_pages, word_count, source_lang.
    """
    import fitz
    import re

    _RU_SPECIFIC = re.compile(r'[ыЫёЁэЭъЪ]')
    _CYRILLIC = re.compile(r'[а-яА-ЯёЁ]')
    _LATIN = re.compile(r'[a-zA-Z]')

    try:
        doc = fitz.open(file_path)
        total_pages = doc.page_count
        total_words = 0
        lang_sample = []

        for i, page in enumerate(doc):
            text = page.get_text()
            total_words += len(text.split())
            if i < 30:
                lang_sample.append(text)

        doc.close()

        sample = " ".join(lang_sample)[:5000]
        ru_specific = len(_RU_SPECIFIC.findall(sample))
        cyrillic = len(_CYRILLIC.findall(sample))
        latin = len(_LATIN.findall(sample))

        if ru_specific > 10:
            source_lang = "ru"
        elif cyrillic > latin * 1.5:
            source_lang = "ru"
        else:
            source_lang = "en"

        return {"total_pages": total_pages, "word_count": total_words, "source_lang": source_lang}

    except Exception as e:
        logger.warning(f"Could not scan PDF info: {e}")
        return {"total_pages": 0, "word_count": 0, "source_lang": "unknown"}


def _extract_pdf_pages_sync(pdf_path: str, from_page: int, to_page: int) -> str:
    """Blocking: extract actual PDF pages [from_page..to_page] and convert to DOCX."""
    import fitz
    os.makedirs(TEMP_DIR, exist_ok=True)

    src = fitz.open(pdf_path)
    total = src.page_count
    p_from = max(0, from_page - 1)
    p_to = min(total - 1, to_page - 1)

    new_pdf = fitz.open()
    new_pdf.insert_pdf(src, from_page=p_from, to_page=p_to)
    src.close()

    tmp_pdf = os.path.join(TEMP_DIR, f"ext_{uuid.uuid4().hex[:10]}.pdf")
    new_pdf.save(tmp_pdf)
    new_pdf.close()

    out_name = f"bt_pages_{from_page}_{to_page}_{uuid.uuid4().hex[:8]}.docx"
    out_path = os.path.join(TEMP_DIR, out_name)
    try:
        _convert_pdf_sync(tmp_pdf, out_path)
    finally:
        if os.path.exists(tmp_pdf):
            os.remove(tmp_pdf)

    return out_path


async def extract_pdf_pages_to_docx(pdf_path: str, from_page: int, to_page: int) -> str:
    """Extract actual PDF pages [from_page..to_page] and convert to DOCX (async)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _extract_pdf_pages_sync, pdf_path, from_page, to_page)


def get_pdf_convert_price(page_count: int) -> int:
    """Return conversion price in som based on page count."""
    from config import PDF_CONVERT_PRICES
    if page_count <= 30:
        return PDF_CONVERT_PRICES["1_30"]
    elif page_count <= 100:
        return PDF_CONVERT_PRICES["31_100"]
    else:
        return PDF_CONVERT_PRICES["101_plus"]
