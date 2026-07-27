import logging
import os

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile, LabeledPrice
from aiogram.fsm.context import FSMContext

from bot.states import ConverterStates
from bot.keyboards import get_main_keyboard, get_payment_choice_keyboard
from database.database import Database
from translations import get_text
from config import som_to_stars, TEMP_DIR, STARS_RATE
from services.converter_service import (
    convert_pdf_to_docx,
    get_pdf_page_count,
    get_pdf_convert_price,
)

router = Router()
logger = logging.getLogger(__name__)

PDF_CONVERT_BUTTON_TEXTS = {
    "📄 PDF → DOCX",
}


@router.message(F.text.in_(PDF_CONVERT_BUTTON_TEXTS))
async def handle_pdf_convert_menu(message: Message, state: FSMContext, user_lang: str, db: Database, user):
    """Handle '📄 PDF → DOCX' button from main menu."""
    await state.clear()
    await state.set_state(ConverterStates.waiting_for_pdf)
    await message.answer(get_text(user_lang, "pdf_convert_send_file"))


@router.message(ConverterStates.waiting_for_pdf, F.document)
async def handle_pdf_file(message: Message, state: FSMContext, user_lang: str, db: Database, user):
    """Receive the PDF file, show info and price, ask for payment confirmation."""
    doc = message.document

    if not doc.file_name or not doc.file_name.lower().endswith(".pdf"):
        await message.answer(get_text(user_lang, "pdf_convert_not_pdf"))
        return

    try:
        os.makedirs(TEMP_DIR, exist_ok=True)
        file_path = os.path.join(TEMP_DIR, f"pdf_in_{doc.file_id[-12:]}.pdf")
        await message.bot.download(doc, destination=file_path)

        page_count = get_pdf_page_count(file_path)
        price = get_pdf_convert_price(page_count if page_count > 0 else 1)
        stars = som_to_stars(price)
        balance = user.balance if user else 0

        await state.update_data(
            pdf_file_path=file_path,
            pdf_filename=doc.file_name,
            pdf_pages=page_count,
            price=price,
        )

        pages_display = page_count if page_count > 0 else "?"
        info_text = get_text(
            user_lang,
            "pdf_convert_file_info",
            filename=doc.file_name,
            pages=pages_display,
            price=price,
        )

        await message.answer(
            info_text,
            reply_markup=get_payment_choice_keyboard(
                user_lang,
                price,
                stars,
                balance,
                balance_callback="pay_balance_pdf",
                back_callback="back_from_pdf_payment",
            ),
            parse_mode="HTML",
        )
        await state.set_state(ConverterStates.waiting_for_payment)

    except Exception as e:
        logger.error(f"Error handling PDF file: {e}")
        await message.answer(get_text(user_lang, "pdf_convert_error"))
        await state.clear()


@router.message(ConverterStates.waiting_for_pdf)
async def handle_pdf_wrong_input(message: Message, user_lang: str):
    """Reject anything that is not a document while waiting for PDF."""
    await message.answer(get_text(user_lang, "pdf_convert_send_file"))


@router.callback_query(ConverterStates.waiting_for_payment, F.data == "pay_balance_pdf")
async def pay_balance_pdf_handler(callback: CallbackQuery, state: FSMContext, db: Database, user_lang: str, user):
    """Handle balance payment for PDF conversion."""
    if not user:
        await callback.answer("Xatolik!", show_alert=True)
        return

    data = await state.get_data()
    price = data.get("price", 0)

    if user.balance < price:
        await callback.answer(get_text(user_lang, "insufficient_balance"), show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)

    await _do_conversion(callback.message, state, db, user_lang, user, price, data, deduct_balance=True)


@router.callback_query(ConverterStates.waiting_for_payment, F.data.startswith("pay_stars_"))
async def pay_stars_pdf_handler(callback: CallbackQuery, state: FSMContext, user_lang: str, user):
    """Send a Telegram Stars invoice for PDF conversion.

    This handler is registered before payments.router, so the state filter
    ensures it intercepts Stars button presses only when the user is in the
    PDF conversion payment state.
    """
    if not user:
        await callback.answer("Xatolik!", show_alert=True)
        return

    try:
        parts = callback.data.split("_")
        price_stars = int(parts[2])
        price_som = int(parts[3])

        title = get_text(user_lang, "stars_invoice_title")
        description = get_text(
            user_lang,
            "stars_invoice_description",
            stars=price_stars,
            som=price_som,
        )

        await callback.message.answer_invoice(
            title=title,
            description=description,
            payload=f"pdf_convert_{user.telegram_id}_{price_som}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=title, amount=price_stars)],
        )
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer()
    except Exception as e:
        logger.error(f"Stars PDF invoice error: {e}")
        await callback.answer("❌ Xatolik yuz berdi", show_alert=True)


@router.callback_query(ConverterStates.waiting_for_payment, F.data == "back_from_pdf_payment")
async def back_from_pdf_payment(callback: CallbackQuery, state: FSMContext, user_lang: str):
    """Cancel payment step and return to waiting for PDF."""
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.set_state(ConverterStates.waiting_for_pdf)
    await callback.message.answer(get_text(user_lang, "pdf_convert_send_file"))


@router.message(ConverterStates.waiting_for_payment, F.successful_payment)
async def successful_payment_pdf_handler(message: Message, state: FSMContext, db: Database, user_lang: str, user):
    """Handle successful Stars payment while in PDF conversion payment state."""
    payment = message.successful_payment
    if not payment.invoice_payload.startswith("pdf_convert_"):
        return

    try:
        parts = payment.invoice_payload.split("_")
        price_som = int(parts[-1])
    except (IndexError, ValueError):
        price_som = payment.total_amount * STARS_RATE

    data = await state.get_data()
    await _do_conversion(message, state, db, user_lang, user, price_som, data, deduct_balance=False)


async def _do_conversion(
    message: Message,
    state: FSMContext,
    db: Database,
    user_lang: str,
    user,
    price: int,
    data: dict,
    deduct_balance: bool = True,
):
    """Convert PDF → DOCX and send result to user.

    Args:
        deduct_balance: True for balance payments (deduct som from account),
                        False for Stars payments (Stars were already charged by Telegram).
    """
    pdf_file_path = data.get("pdf_file_path", "")
    pdf_filename = data.get("pdf_filename", "document.pdf")
    docx_path = None

    processing_msg = await message.answer(get_text(user_lang, "pdf_convert_processing"))

    try:
        docx_path = await convert_pdf_to_docx(pdf_file_path)

        if deduct_balance:
            await db.update_user_balance(user.telegram_id, -price)

        output_filename = os.path.splitext(pdf_filename)[0] + ".docx"
        docx_file = FSInputFile(docx_path, filename=output_filename)

        await processing_msg.delete()
        await message.answer(get_text(user_lang, "pdf_convert_done"))
        await message.answer_document(
            document=docx_file,
            reply_markup=get_main_keyboard(user_lang),
        )

    except Exception as e:
        logger.error(f"PDF conversion error: {e}")
        try:
            await processing_msg.delete()
        except Exception:
            pass
        await message.answer(
            get_text(user_lang, "pdf_convert_too_large"),
            reply_markup=get_main_keyboard(user_lang),
        )
    finally:
        await state.clear()
        for tmp in (pdf_file_path, docx_path):
            if tmp and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass
