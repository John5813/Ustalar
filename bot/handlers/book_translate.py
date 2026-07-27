import logging
import os
import re
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext

from bot.states import BookTranslateStates, DocumentStates
from bot.keyboards import (
    get_main_keyboard,
    get_book_translate_lang_keyboard,
    get_book_translate_payment_keyboard,
    get_post_translation_keyboard,
    get_doc_language_keyboard,
)
from database.database import Database
from translations import get_text
from config import TEMP_DIR
from services.book_translate_service import (
    count_docx_words,
    count_estimated_pages,
    get_page_range_word_count,
    extract_pages_by_range,
    get_book_translate_price,
    translate_docx,
    auto_convert_pdf_to_docx,
    extract_relevant_content_for_topic,
    detect_source_language,
)
from services.converter_service import get_pdf_page_count, get_pdf_info, extract_pdf_pages_to_docx

router = Router()
logger = logging.getLogger(__name__)

BOOK_TRANSLATE_TEXTS = {
    "uz": "\U0001f4da Kitob tarjimasi",
    "ru": "\U0001f4da \u041f\u0435\u0440\u0435\u0432\u043e\u0434 \u043a\u043d\u0438\u0433\u0438",
    "en": "\U0001f4da Book Translation",
}


async def _cleanup_temp_file(state: FSMContext):
    try:
        data = await state.get_data()
        for key in ("local_path", "pdf_path", "range_path"):
            path = data.get(key)
            if path and os.path.exists(path):
                os.remove(path)
    except Exception:
        pass


@router.message(F.text.in_(list(BOOK_TRANSLATE_TEXTS.values())))
async def handle_book_translate_start(message: Message, state: FSMContext, user_lang: str, db: Database, user):
    await state.clear()
    await state.set_state(BookTranslateStates.waiting_for_file)
    await message.answer(get_text(user_lang, "book_translate_send_file"))


from aiogram.filters import Command

@router.message(Command("book"))
async def handle_book_command(message: Message, state: FSMContext, user_lang: str, db: Database, user):
    """Hidden /book command to access book translation feature."""
    await state.clear()
    await state.set_state(BookTranslateStates.waiting_for_file)
    await message.answer(get_text(user_lang, "book_translate_send_file"))


@router.message(BookTranslateStates.waiting_for_file)
async def handle_book_translate_file(message: Message, state: FSMContext, user_lang: str, db: Database, user):
    doc = message.document
    if not doc:
        await message.answer(get_text(user_lang, "book_translate_not_docx"))
        return

    file_name = doc.file_name or ""
    is_pdf = file_name.lower().endswith(".pdf")
    is_docx = file_name.lower().endswith(".docx")

    if not is_pdf and not is_docx:
        await message.answer(get_text(user_lang, "book_translate_not_docx"))
        return

    wait_msg = await message.answer(get_text(user_lang, "book_translate_checking"))
    try:
        os.makedirs(TEMP_DIR, exist_ok=True)
        ext = ".pdf" if is_pdf else ".docx"
        local_path = os.path.join(TEMP_DIR, f"bt_input_{message.from_user.id}_{doc.file_id[-8:]}{ext}")
        file = await message.bot.get_file(doc.file_id)
        await message.bot.download_file(file.file_path, local_path)

        if is_pdf:
            pdf_info = get_pdf_info(local_path)
            total_pages = pdf_info["total_pages"]
            word_count = pdf_info["word_count"]
            source_lang = pdf_info["source_lang"]
            await state.update_data(
                pdf_path=local_path,
                local_path=None,
                original_filename=file_name,
                word_count=word_count,
                total_pages=total_pages,
                source_lang=source_lang,
            )
        else:
            docx_path = local_path
            await state.update_data(local_path=docx_path, original_filename=file_name)
            word_count = count_docx_words(docx_path)
            total_pages = count_estimated_pages(docx_path)
            source_lang = detect_source_language(docx_path)
            await state.update_data(word_count=word_count, total_pages=total_pages, source_lang=source_lang)

        await wait_msg.delete()

        await message.answer(
            get_text(user_lang, "book_translate_enter_range", total=total_pages),
            parse_mode="Markdown"
        )
        await state.set_state(BookTranslateStates.waiting_for_line_range)

    except Exception as e:
        logger.error(f"Error processing book translate file: {e}")
        try:
            await wait_msg.delete()
        except Exception:
            pass
        await message.answer(get_text(user_lang, "book_translate_error"))
        await _cleanup_temp_file(state)
        await state.clear()


@router.message(BookTranslateStates.waiting_for_line_range)
async def handle_line_range_input(message: Message, state: FSMContext, user_lang: str, db: Database, user):
    text = (message.text or "").strip()
    data = await state.get_data()
    total_pages = data.get("total_pages", 0)
    word_count = data.get("word_count", 0)
    local_path = data.get("local_path", "")

    if text == "0":
        # Butun kitob
        price = get_book_translate_price(word_count)
        await state.update_data(price=price, page_from=None, page_to=None)
        await message.answer(
            get_text(user_lang, "book_translate_full_price", count=word_count, price=price),
            parse_mode="Markdown"
        )
        await message.answer(
            get_text(user_lang, "book_translate_select_lang"),
            reply_markup=get_book_translate_lang_keyboard(user_lang)
        )
        await state.set_state(BookTranslateStates.waiting_for_target_lang)
        return

    # "22-55" yoki "22 55" formatini parse qilish
    match = re.match(r'^(\d+)\s*[-–\s]\s*(\d+)$', text.strip())
    if not match:
        await message.answer(get_text(user_lang, "book_translate_range_invalid"))
        return

    from_p = int(match.group(1))
    to_p = int(match.group(2))

    if from_p < 1 or to_p > total_pages or from_p >= to_p:
        await message.answer(
            get_text(user_lang, "book_translate_range_out", total=total_pages),
            parse_mode="Markdown"
        )
        return

    pdf_path = data.get("pdf_path")
    if pdf_path:
        avg_words = word_count / total_pages if total_pages > 0 else 300
        range_words = max(1, round((to_p - from_p + 1) * avg_words))
    else:
        range_words = get_page_range_word_count(local_path, from_p, to_p)
        if range_words == 0:
            range_words = (to_p - from_p + 1) * 300

    price = get_book_translate_price(range_words)
    await state.update_data(price=price, page_from=from_p, page_to=to_p, range_words=range_words)

    await message.answer(
        get_text(user_lang, "book_translate_range_info",
                 from_p=from_p, to_p=to_p, word_count=range_words, price=price),
        parse_mode="Markdown"
    )
    await message.answer(
        get_text(user_lang, "book_translate_select_lang"),
        reply_markup=get_book_translate_lang_keyboard(user_lang)
    )
    await state.set_state(BookTranslateStates.waiting_for_target_lang)


@router.callback_query(F.data == "bt_back_to_menu")
async def handle_bt_back(callback: CallbackQuery, state: FSMContext, user_lang: str):
    await callback.answer()
    await _cleanup_temp_file(state)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await state.clear()
    await callback.message.answer(
        get_text(user_lang, "book_translate_main_menu"),
        reply_markup=get_main_keyboard(user_lang)
    )


@router.callback_query(F.data.startswith("bt_lang_"), BookTranslateStates.waiting_for_target_lang)
async def handle_bt_lang_selection(callback: CallbackQuery, state: FSMContext, user_lang: str, db: Database, user):
    await callback.answer()
    target_lang = callback.data.split("_")[-1]
    data = await state.get_data()
    source_lang = data.get("source_lang", "unknown")

    # Agar kitob ruscha bo'lib, foydalanuvchi ham rus tilini tanlasa — bekor qilish
    if source_lang == "ru" and target_lang == "ru":
        await callback.message.answer(
            get_text(user_lang, "book_translate_same_lang_warning"),
            reply_markup=get_book_translate_lang_keyboard(user_lang)
        )
        return

    price = data.get("price", 15000)
    balance = user.balance if user else 0

    await state.update_data(target_lang=target_lang)
    await state.set_state(BookTranslateStates.waiting_for_payment)

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(
        get_text(user_lang, "payment_choose", price=price, balance=balance),
        reply_markup=get_book_translate_payment_keyboard(user_lang, price, balance)
    )


@router.callback_query(F.data == "bt_back_from_payment", BookTranslateStates.waiting_for_payment)
async def handle_bt_back_from_payment(callback: CallbackQuery, state: FSMContext, user_lang: str):
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        get_text(user_lang, "book_translate_select_lang"),
        reply_markup=get_book_translate_lang_keyboard(user_lang)
    )
    await state.set_state(BookTranslateStates.waiting_for_target_lang)


@router.callback_query(F.data == "pay_balance_book_translate", BookTranslateStates.waiting_for_payment)
async def handle_bt_pay_balance(callback: CallbackQuery, state: FSMContext, user_lang: str, db: Database, user):
    await callback.answer()
    data = await state.get_data()
    price = data.get("price", 15000)
    balance = user.balance if user else 0

    if balance < price:
        await callback.message.answer(get_text(user_lang, "insufficient_balance"))
        return

    local_path = data.get("local_path")
    target_lang = data.get("target_lang", "en")
    original_filename = data.get("original_filename", "document.docx")
    page_from = data.get("page_from")
    page_to = data.get("page_to")

    await state.set_state(BookTranslateStates.translating)
    try:
        await callback.message.delete()
    except Exception:
        pass

    processing_msg = await callback.message.answer(get_text(user_lang, "book_translate_processing"))

    pdf_path = data.get("pdf_path")
    range_path = None
    full_pdf_docx = None
    translate_path = local_path
    try:
        if page_from and page_to:
            logger.info(f"Extracting pages {page_from}-{page_to} for user {user.telegram_id}")
            if pdf_path and os.path.exists(pdf_path):
                range_path = await extract_pdf_pages_to_docx(pdf_path, page_from, page_to)
            else:
                range_path = extract_pages_by_range(local_path, page_from, page_to)
            translate_path = range_path
        elif pdf_path and os.path.exists(pdf_path) and not local_path:
            logger.info(f"Converting full PDF to DOCX for user {user.telegram_id}")
            full_pdf_docx = await auto_convert_pdf_to_docx(pdf_path)
            translate_path = full_pdf_docx

        logger.info(f"Starting translation for user {user.telegram_id}: lang={target_lang}, pages={page_from}-{page_to or 'ALL'}")
        out_path = await translate_docx(translate_path, target_lang)
        await db.update_user_balance(user.telegram_id, -price)
        logger.info(f"Translation complete for user {user.telegram_id}: {out_path}")

        base, ext = os.path.splitext(original_filename)
        if base.lower().endswith(".pdf"):
            base = base[:-4]
        lang_suffixes = {"uz": "_uz", "ru": "_ru", "en": "_en"}
        if page_from and page_to:
            out_filename = f"{base}_v{page_from}_{page_to}{lang_suffixes.get(target_lang, f'_{target_lang}')}.docx"
        else:
            out_filename = f"{base}{lang_suffixes.get(target_lang, f'_{target_lang}')}.docx"

        doc_file = FSInputFile(out_path, filename=out_filename)
        try:
            await processing_msg.delete()
        except Exception:
            pass
        await callback.message.answer_document(
            document=doc_file,
            caption=get_text(user_lang, "book_translate_done")
        )
        # Mualiflik huquqi haqida eslatma
        await callback.message.answer(get_text(user_lang, "book_translate_copyright_note"))

        book_topic = base[:100]
        await state.update_data(book_topic=book_topic, translated_path=out_path)
        await state.set_state(BookTranslateStates.post_translation)
        await callback.message.answer(
            get_text(user_lang, "book_translate_post_services"),
            reply_markup=get_post_translation_keyboard(user_lang)
        )

    except Exception as e:
        logger.error(f"Error translating docx: {e}")
        try:
            await processing_msg.delete()
        except Exception:
            pass
        await callback.message.answer(
            get_text(user_lang, "book_translate_error"),
            reply_markup=get_main_keyboard(user_lang)
        )
        await state.clear()
    finally:
        try:
            if local_path and os.path.exists(local_path):
                os.remove(local_path)
            pdf_path = data.get("pdf_path")
            if pdf_path and os.path.exists(pdf_path):
                os.remove(pdf_path)
            if range_path and os.path.exists(range_path):
                os.remove(range_path)
            if full_pdf_docx and os.path.exists(full_pdf_docx):
                os.remove(full_pdf_docx)
        except Exception:
            pass


@router.callback_query(F.data.startswith("bt_post_"), BookTranslateStates.post_translation)
async def handle_post_translation_service(callback: CallbackQuery, state: FSMContext, user_lang: str, db: Database, user):
    await callback.answer()
    action = callback.data.replace("bt_post_", "")

    data = await state.get_data()

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if action == "no_thanks":
        await state.clear()
        await callback.message.answer(
            get_text(user_lang, "book_translate_main_menu"),
            reply_markup=get_main_keyboard(user_lang)
        )
        return

    doc_type_map = {
        "presentation": "presentation",
        "referat": "referat",
        "course_work": "course_work",
        "article": "maqola",
    }
    doc_type = doc_type_map.get(action, "referat")

    doc_type_labels = {
        "uz": {"presentation": "taqdimot", "referat": "referat", "course_work": "kurs ishi", "maqola": "maqola"},
        "ru": {"presentation": "презентация", "referat": "реферат", "course_work": "курсовая", "maqola": "статья"},
        "en": {"presentation": "presentation", "referat": "research paper", "course_work": "course work", "maqola": "article"},
    }
    lang_labels = doc_type_labels.get(user_lang, doc_type_labels["uz"])
    doc_type_label = lang_labels.get(doc_type, doc_type)

    await state.update_data(document_type=doc_type)
    await state.set_state(BookTranslateStates.waiting_for_doc_topic)

    await callback.message.answer(
        get_text(user_lang, "book_translate_ask_topic", doc_type=doc_type_label)
    )


@router.message(BookTranslateStates.waiting_for_doc_topic)
async def handle_book_translate_doc_topic(message: Message, state: FSMContext, user_lang: str, db: Database, user):
    """Mavzu kiritilgandan so'ng kitobdan tegishli ma'lumotni topib hujjat tayyorlash"""
    topic = (message.text or "").strip()
    if len(topic) < 3:
        await message.answer(get_text(user_lang, "topic_too_short"))
        return

    data = await state.get_data()
    doc_type = data.get("document_type", "referat")
    book_topic = data.get("book_topic", "")
    translated_path = data.get("translated_path", "")

    wait_msg = await message.answer(get_text(user_lang, "book_translate_extracting"))

    book_content = ""
    try:
        if translated_path and os.path.exists(translated_path):
            from docx import Document as DocxDocument
            docx_doc = DocxDocument(translated_path)
            paragraphs = []
            word_count = 0
            for para in docx_doc.paragraphs:
                text = para.text.strip()
                if not text:
                    continue
                paragraphs.append(text)
                word_count += len(text.split())
                if word_count > 15000:
                    break
            raw_content = "\n\n".join(paragraphs)
            if len(raw_content) > 60000:
                raw_content = raw_content[:60000]
            try:
                os.remove(translated_path)
            except Exception:
                pass
            book_content = await extract_relevant_content_for_topic(raw_content, topic, user_lang)
    except Exception as e:
        logger.warning(f"Could not read translated file: {e}")

    try:
        await wait_msg.delete()
    except Exception:
        pass

    await state.update_data(
        topic=topic,
        book_content=book_content,
        book_context=True,
    )
    await state.set_state(DocumentStates.waiting_for_doc_language)

    await message.answer(
        get_text(user_lang, "select_doc_language"),
        reply_markup=get_doc_language_keyboard(user_lang)
    )
