import logging
import os
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ContentType, LabeledPrice, PreCheckoutQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from bot.states import PaymentStates
from bot.keyboards import get_payment_amount_keyboard, get_main_keyboard
from database.database import Database
from translations import get_text
from config import PAYMENT_CARD, PAYMENT_CARD_2, PAYMENT_CARD_OWNER, ADMIN_IDS, STARS_RATE, som_to_stars

router = Router()
logger = logging.getLogger(__name__)

# Payment menu items in different languages
PAYMENT_TEXTS = ["💳 To'lov qilish", "💳 Оплата", "💳 Payment"]
ACCOUNT_TEXTS = ["💎 Mening hisobim", "💎 Мой счет", "💎 My Account"]
REFERRAL_TEXTS = ["💰 Pul ishlab topish", "👥 Реферальная программа", "👥 Referral Program"]

@router.message(F.text.in_(PAYMENT_TEXTS))
async def handle_payment_request(message: Message, state: FSMContext, user_lang: str):
    """Handle payment request"""
    await state.clear()  # Clear any active state

    if user_lang == "uz":
        explanation_text = "💳 Sizga kerakli to'lov miqdorini belgilang:"
    elif user_lang == "ru":
        explanation_text = "💳 Укажите необходимую сумму платежа:"
    else:  # en
        explanation_text = "💳 Specify the required payment amount:"

    await message.answer(
        explanation_text,
        reply_markup=get_payment_amount_keyboard(user_lang),
        parse_mode="Markdown"
    )

@router.message(F.text.in_(ACCOUNT_TEXTS))
async def handle_account_info(message: Message, state: FSMContext, db: Database, user_lang: str, user):
    """Show account information"""
    await state.clear()  # Clear any active state
    if not user:
        await message.answer("❌ Сначала выполните команду /start")
        return

    if user_lang == "uz":
        account_text = f"💰 Sizning hisobingiz:\n\n💵 Balans: {user.balance:,} so'm"
    elif user_lang == "ru":
        account_text = f"💰 Ваш счет:\n\n💵 Баланс: {user.balance:,} сум"
    else:  # en
        account_text = f"💰 Your Account:\n\n💵 Balance: {user.balance:,} som"

    await message.answer(
        account_text,
        reply_markup=get_main_keyboard(user_lang)
    )

@router.callback_query(F.data.regexp(r"^pay_\d+$"))
async def handle_payment_amount_selection(callback: CallbackQuery, state: FSMContext, user_lang: str):
    """Handle payment amount selection"""
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

    try:
        await callback.answer()
    except Exception:
        pass

    try:
        amount = int(callback.data.split("_")[1])
        await state.update_data(payment_amount=amount)

        card1_fmt = f"{PAYMENT_CARD[:4]} {PAYMENT_CARD[4:8]} {PAYMENT_CARD[8:12]} {PAYMENT_CARD[12:]}"
        card2_fmt = f"{PAYMENT_CARD_2[:4]} {PAYMENT_CARD_2[4:8]} {PAYMENT_CARD_2[8:12]} {PAYMENT_CARD_2[12:]}"

        if user_lang == "uz":
            instructions = (
                f"💳 <b>To'lov qilish uchun:</b>\n\n"
                f"1️⃣ Quyidagi kartalardan <b>biriga</b> pul o'tkazing:\n\n"
                f"🏦 Karta 1:\n<code>{card1_fmt}</code>\n\n"
                f"🏦 Karta 2:\n<code>{card2_fmt}</code>\n\n"
                f"👤 Karta egasi: <b>{PAYMENT_CARD_OWNER}</b>\n\n"
                f"2️⃣ <b>{amount:,} so'm</b> o'tkazing\n\n"
                f"3️⃣ «📤 To'lov chekini yuborish» tugmasini bosib chekni yuboring\n\n"
                f"⚠️ <b>DIQQAT:</b> Chekni faqat haqiqiy to'lovdan keyin yuboring. "
                f"Soxta chek yuborish taqiqlanadi!"
            )
            upload_button_text = "📤 To'lov chekini yuborish"
            back_button_text = "🔙 Orqaga qaytish"
        elif user_lang == "ru":
            instructions = (
                f"💳 <b>Для оплаты:</b>\n\n"
                f"1️⃣ Переведите деньги на <b>любую</b> из карт:\n\n"
                f"🏦 Карта 1:\n<code>{card1_fmt}</code>\n\n"
                f"🏦 Карта 2:\n<code>{card2_fmt}</code>\n\n"
                f"👤 Владелец карты: <b>{PAYMENT_CARD_OWNER}</b>\n\n"
                f"2️⃣ Переведите <b>{amount:,} сум</b>\n\n"
                f"3️⃣ Нажмите «📤 Отправить чек» и отправьте чек\n\n"
                f"⚠️ <b>ВНИМАНИЕ:</b> Отправляйте чек только после реального платежа. "
                f"Поддельные чеки запрещены!"
            )
            upload_button_text = "📤 Отправить чек"
            back_button_text = "🔙 Назад"
        else:
            instructions = (
                f"💳 <b>To pay:</b>\n\n"
                f"1️⃣ Transfer money to <b>any</b> of the cards:\n\n"
                f"🏦 Card 1:\n<code>{card1_fmt}</code>\n\n"
                f"🏦 Card 2:\n<code>{card2_fmt}</code>\n\n"
                f"👤 Card owner: <b>{PAYMENT_CARD_OWNER}</b>\n\n"
                f"2️⃣ Transfer <b>{amount:,} som</b>\n\n"
                f"3️⃣ Click «📤 Upload receipt» and send the receipt\n\n"
                f"⚠️ <b>WARNING:</b> Send receipt only after real payment. "
                f"Fake receipts are prohibited!"
            )
            upload_button_text = "📤 Upload receipt"
            back_button_text = "🔙 Back"

        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=upload_button_text)],
                [KeyboardButton(text=back_button_text)]
            ],
            resize_keyboard=True
        )

        try:
            await callback.message.edit_text(instructions, parse_mode="HTML")
        except Exception:
            await callback.message.answer(instructions, parse_mode="HTML")

        await callback.message.answer(
            "👇 Quyidagi tugmalardan birini tanlang:",
            reply_markup=keyboard
        )

        await state.update_data(payment_amount=amount)
        await state.set_state(PaymentStates.waiting_for_screenshot)

    except Exception as e:
        logger.error(f"handle_payment_amount_selection error: {e}", exc_info=True)


@router.callback_query(F.data == "pay_custom")
async def handle_custom_amount_request(callback: CallbackQuery, state: FSMContext, user_lang: str):
    """Ask user to type any custom payment amount"""
    try:
        await callback.answer()
    except Exception:
        pass

    try:
        if user_lang == "uz":
            text = (
                "✏️ Istalgan to'lov summasini yozing:\n\n"
                "Masalan: <code>35000</code>\n\n"
                "⚠️ Faqat raqam kiriting (so'm)."
            )
            cancel_text = "🔙 Bekor qilish"
        elif user_lang == "ru":
            text = (
                "✏️ Введите любую сумму платежа:\n\n"
                "Например: <code>35000</code>\n\n"
                "⚠️ Введите только число (в сумах)."
            )
            cancel_text = "🔙 Отмена"
        else:
            text = (
                "✏️ Enter any payment amount:\n\n"
                "For example: <code>35000</code>\n\n"
                "⚠️ Numbers only (in som)."
            )
            cancel_text = "🔙 Cancel"

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=cancel_text, callback_data="pay_custom_cancel")]
        ])

        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)

        await state.set_state(PaymentStates.waiting_for_custom_amount)

    except Exception as e:
        logger.error(f"handle_custom_amount_request error: {e}", exc_info=True)


@router.callback_query(F.data == "pay_custom_cancel")
async def handle_custom_amount_cancel(callback: CallbackQuery, state: FSMContext, user_lang: str):
    """Cancel custom amount and go back to amount selection"""
    try:
        await callback.answer()
    except Exception:
        pass

    try:
        await state.clear()
        if user_lang == "uz":
            text = "💳 Sizga kerakli to'lov miqdorini belgilang:"
        elif user_lang == "ru":
            text = "💳 Укажите необходимую сумму платежа:"
        else:
            text = "💳 Specify the required payment amount:"
        try:
            await callback.message.edit_text(text, reply_markup=get_payment_amount_keyboard(user_lang))
        except Exception:
            await callback.message.answer(text, reply_markup=get_payment_amount_keyboard(user_lang))
    except Exception as e:
        logger.error(f"handle_custom_amount_cancel error: {e}", exc_info=True)


@router.message(PaymentStates.waiting_for_custom_amount, F.text)
async def handle_custom_amount_input(callback_message: Message, state: FSMContext, user_lang: str):
    """Validate custom amount and proceed to payment instructions"""
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

    raw = (callback_message.text or "").strip().replace(" ", "").replace(",", "").replace(".", "")
    if not raw.isdigit():
        if user_lang == "uz":
            await callback_message.answer("❌ Iltimos, faqat raqam kiriting. Masalan: <code>35000</code>", parse_mode="HTML")
        elif user_lang == "ru":
            await callback_message.answer("❌ Пожалуйста, введите только число. Например: <code>35000</code>", parse_mode="HTML")
        else:
            await callback_message.answer("❌ Please enter numbers only. Example: <code>35000</code>", parse_mode="HTML")
        return

    amount = int(raw)
    if amount < 1000:
        if user_lang == "uz":
            await callback_message.answer("❌ Minimal to'lov miqdori 1,000 so'm.")
        elif user_lang == "ru":
            await callback_message.answer("❌ Минимальная сумма платежа — 1 000 сум.")
        else:
            await callback_message.answer("❌ Minimum payment amount is 1,000 som.")
        return

    await state.update_data(payment_amount=amount)

    card1_fmt = f"{PAYMENT_CARD[:4]} {PAYMENT_CARD[4:8]} {PAYMENT_CARD[8:12]} {PAYMENT_CARD[12:]}"
    card2_fmt = f"{PAYMENT_CARD_2[:4]} {PAYMENT_CARD_2[4:8]} {PAYMENT_CARD_2[8:12]} {PAYMENT_CARD_2[12:]}"

    if user_lang == "uz":
        instructions = (
            f"💳 <b>To'lov qilish uchun:</b>\n\n"
            f"1️⃣ Quyidagi kartalardan <b>biriga</b> pul o'tkazing:\n\n"
            f"🏦 Karta 1:\n<code>{card1_fmt}</code>\n\n"
            f"🏦 Karta 2:\n<code>{card2_fmt}</code>\n\n"
            f"👤 Karta egasi: <b>{PAYMENT_CARD_OWNER}</b>\n\n"
            f"2️⃣ <b>{amount:,} so'm</b> o'tkazing\n\n"
            f"3️⃣ «📤 To'lov chekini yuborish» tugmasini bosib chekni yuboring\n\n"
            f"⚠️ <b>DIQQAT:</b> Chekni faqat haqiqiy to'lovdan keyin yuboring. "
            f"Soxta chek yuborish taqiqlanadi!"
        )
        upload_button_text = "📤 To'lov chekini yuborish"
        back_button_text = "🔙 Orqaga qaytish"
    elif user_lang == "ru":
        instructions = (
            f"💳 <b>Для оплаты:</b>\n\n"
            f"1️⃣ Переведите деньги на <b>любую</b> из карт:\n\n"
            f"🏦 Карта 1:\n<code>{card1_fmt}</code>\n\n"
            f"🏦 Карта 2:\n<code>{card2_fmt}</code>\n\n"
            f"👤 Владелец карты: <b>{PAYMENT_CARD_OWNER}</b>\n\n"
            f"2️⃣ Переведите <b>{amount:,} сум</b>\n\n"
            f"3️⃣ Нажмите «📤 Отправить чек» и отправьте чек\n\n"
            f"⚠️ <b>ВНИМАНИЕ:</b> Отправляйте чек только после реального платежа. "
            f"Поддельные чеки запрещены!"
        )
        upload_button_text = "📤 Отправить чек"
        back_button_text = "🔙 Назад"
    else:
        instructions = (
            f"💳 <b>To pay:</b>\n\n"
            f"1️⃣ Transfer money to <b>any</b> of the cards:\n\n"
            f"🏦 Card 1:\n<code>{card1_fmt}</code>\n\n"
            f"🏦 Card 2:\n<code>{card2_fmt}</code>\n\n"
            f"👤 Card owner: <b>{PAYMENT_CARD_OWNER}</b>\n\n"
            f"2️⃣ Transfer <b>{amount:,} som</b>\n\n"
            f"3️⃣ Click «📤 Upload receipt» and send the receipt\n\n"
            f"⚠️ <b>WARNING:</b> Send receipt only after real payment. "
            f"Fake receipts are prohibited!"
        )
        upload_button_text = "📤 Upload receipt"
        back_button_text = "🔙 Back"

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=upload_button_text)],
            [KeyboardButton(text=back_button_text)]
        ],
        resize_keyboard=True
    )

    await callback_message.answer(instructions, parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(PaymentStates.waiting_for_screenshot)


@router.message(PaymentStates.waiting_for_screenshot, F.content_type.in_([ContentType.PHOTO, ContentType.DOCUMENT]))
async def handle_payment_screenshot(message: Message, state: FSMContext, db: Database, user_lang: str, user=None):
    """Handle payment screenshot"""
    try:
        # Get user from database if not provided by middleware
        if not user:
            user = await db.get_user(message.from_user.id)
            if not user:
                if user_lang == "uz":
                    error_text = "❌ Xatolik yuz berdi. Iltimos, /start buyrug'ini bajaring."
                elif user_lang == "ru":
                    error_text = "❌ Произошла ошибка. Пожалуйста, выполните команду /start."
                else:
                    error_text = "❌ Error occurred. Please execute /start command."

                await message.answer(error_text, reply_markup=get_main_keyboard(user_lang))
                await state.clear()
                return

        # Get payment amount and source from state
        data = await state.get_data()
        amount = data.get('payment_amount')
        source = data.get('payment_source', "")  # Get source if from help section

        if not amount:
            if user_lang == "uz":
                error_text = "❌ To'lov miqdori topilmadi. Iltimos, qaytadan boshlang."
            elif user_lang == "ru":
                error_text = "❌ Сумма платежа не найдена. Пожалуйста, начните заново."
            else:
                error_text = "❌ Payment amount not found. Please start again."

            await message.answer(error_text, reply_markup=get_main_keyboard(user_lang))
            await state.clear()
            return

        # Get file ID
        if message.photo:
            file_id = message.photo[-1].file_id
        else:
            file_id = message.document.file_id

        # Create payment record with source
        payment_id = await db.create_payment(user.id, amount, file_id, source)

        if not payment_id:
            if user_lang == "uz":
                error_text = "❌ To'lovni saqlashda xatolik. Iltimos, qayta urinib ko'ring."
            elif user_lang == "ru":
                error_text = "❌ Ошибка при сохранении платежа. Пожалуйста, попробуйте снова."
            else:
                error_text = "❌ Error saving payment. Please try again."

            await message.answer(error_text, reply_markup=get_main_keyboard(user_lang))
            await state.clear()
            return

        # Check time and add reminder
        from datetime import datetime
        now = datetime.now()
        current_hour = now.hour
        is_daytime = 7 <= current_hour < 22

        # Notify user
        success_msg = get_text(user_lang, "payment_sent_to_admin")
        if is_daytime:
            success_msg += f"\n\n{get_text(user_lang, 'payment_reminder_daytime')}"
        else:
            success_msg += f"\n\n{get_text(user_lang, 'payment_reminder_nighttime')}"

        await message.answer(
            success_msg,
            reply_markup=get_main_keyboard(user_lang),
            parse_mode="Markdown"
        )

        # Notify admins with source info
        await notify_admins_about_payment(message.bot, user, amount, message.message_id, payment_id, source)

        logger.info(f"Payment {payment_id} created successfully for user {user.telegram_id}, amount {amount}, source: {source}")

    except Exception as e:
        logger.error(f"Error processing payment screenshot for user {message.from_user.id}: {e}", exc_info=True)

        if user_lang == "uz":
            error_text = "❌ Xatolik yuz berdi. Iltimos, /start buyrug'ini bajaring va qayta urinib ko'ring."
        elif user_lang == "ru":
            error_text = "❌ Произошла ошибка. Пожалуйста, выполните /start и попробуйте снова."
        else:
            error_text = "❌ Error occurred. Please execute /start and try again."

        await message.answer(error_text, reply_markup=get_main_keyboard(user_lang))

    finally:
        await state.clear()

async def notify_admins_about_payment(bot, user, amount, message_id, payment_id, source=""):
    """Notify admins about new payment"""
    from bot.keyboards import get_payment_review_keyboard

    user_link = f"@{user.username}" if user.username else f"tg://user?id={user.telegram_id}"

    # Add source info if present
    source_text = ""
    if source == "help":
        source_text = "\n📍 Manba: 📞 Yordam bo'limi orqali"

    for admin_id in ADMIN_IDS:
        try:
            # First, forward the screenshot
            await bot.copy_message(
                chat_id=admin_id,
                from_chat_id=user.telegram_id,
                message_id=message_id
            )

            # Then send payment info with buttons below the image
            text = (
                f"🧾 Yangi to'lov:\n"
                f"👤 Foydalanuvchi: {user_link}\n"
                f"💵 Summasi: {amount:,} so'm\n"
                f"📅 To'lov ID: {payment_id}{source_text}\n\n"
                f"⬆️ Yuqoridagi chekni tekshiring va to'lovni tasdiqlang:"
            )

            await bot.send_message(
                admin_id,
                text,
                reply_markup=get_payment_review_keyboard(payment_id)
            )

        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")

@router.callback_query(F.data == "show_referral")
async def handle_referral_callback(callback: CallbackQuery, db: Database, user_lang: str, user):
    """Show referral information from payment menu"""
    if not user:
        await callback.answer("❌ Avval /start buyrug'ini bajaring", show_alert=True)
        return

    try:
        # Ensure user has referral code
        if not user.referral_code:
            logger.error(f"User {user.telegram_id} has no referral code after get_user")
            await callback.answer("❌ Xatolik yuz berdi. Iltimos, /start buyrug'ini qayta bajaring.", show_alert=True)
            return

        # Get bot username for referral link
        bot_info = await callback.bot.get_me()
        bot_username = bot_info.username

        # Create referral link
        referral_link = f"https://t.me/{bot_username}?start=ref_{user.referral_code}"

        # Edit message with referral info (no statistics)
        await callback.message.edit_text(
            get_text(user_lang, "referral_info", referral_link=referral_link),
            parse_mode="Markdown"
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Error showing referral info: {e}")
        await callback.answer("❌ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.", show_alert=True)

@router.message(StateFilter(None), F.text.in_(REFERRAL_TEXTS))
async def handle_referral_request(message: Message, db: Database, user_lang: str, user):
    """Show referral information from main menu"""
    if not user:
        await message.answer("❌ Avval /start buyrug'ini bajaring")
        return

    try:
        # Ensure user has referral code
        if not user.referral_code:
            logger.error(f"User {user.telegram_id} has no referral code after get_user")
            await message.answer("❌ Xatolik yuz berdi. Iltimos, /start buyrug'ini qayta bajaring.", reply_markup=get_main_keyboard(user_lang))
            return

        # Get bot username for referral link
        bot_info = await message.bot.get_me()
        bot_username = bot_info.username

        # Create referral link
        referral_link = f"https://t.me/{bot_username}?start=ref_{user.referral_code}"

        # Send message with referral info (no statistics)
        await message.answer(
            get_text(user_lang, "referral_info", referral_link=referral_link),
            reply_markup=get_main_keyboard(user_lang),
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Error showing referral info: {e}")
        await message.answer("❌ Xatolik yuz berdi. Iltimos, qayta urinib ko'ring.", reply_markup=get_main_keyboard(user_lang))


# ─── Telegram Stars payment handlers ───────────────────────────────────────────

@router.callback_query(F.data == "pay_card_start")
async def handle_card_payment_start(callback: CallbackQuery, state: FSMContext, user_lang: str):
    """Redirect to card payment flow"""
    try:
        await callback.answer()
    except Exception:
        pass
    try:
        data = await state.get_data()
        temp_path = data.get("local_path")
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
    except Exception:
        pass
    try:
        await state.clear()
        if user_lang == "uz":
            text = "💳 To'lov miqdorini tanlang:"
        elif user_lang == "ru":
            text = "💳 Выберите сумму платежа:"
        else:
            text = "💳 Select payment amount:"
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await callback.message.answer(text, reply_markup=get_payment_amount_keyboard(user_lang))
    except Exception as e:
        logger.error(f"handle_card_payment_start error: {e}", exc_info=True)


@router.callback_query(F.data.startswith("pay_stars_"))
async def handle_stars_invoice(callback: CallbackQuery, user_lang: str):
    """Send a Telegram Stars invoice to the user"""
    try:
        parts = callback.data.split("_")
        price_stars = int(parts[2])
        price_som = int(parts[3])

        title = get_text(user_lang, "stars_invoice_title")
        description = get_text(user_lang, "stars_invoice_description", stars=price_stars, som=price_som)

        await callback.message.answer_invoice(
            title=title,
            description=description,
            payload=f"topup_{price_stars}_{price_som}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=title, amount=price_stars)],
        )
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer()
    except Exception as e:
        logger.error(f"Stars invoice error: {e}")
        await callback.answer("❌ Xatolik yuz berdi", show_alert=True)


@router.pre_checkout_query()
async def pre_checkout_handler(query: PreCheckoutQuery):
    """Answer pre-checkout query — must be answered within 10 seconds"""
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment_handler(message: Message, db: Database, user_lang: str):
    """Handle successful Stars payment — credit balance"""
    try:
        payment = message.successful_payment
        stars = payment.total_amount
        som_amount = stars * STARS_RATE

        await db.update_user_balance(message.from_user.id, som_amount)

        await message.answer(
            get_text(user_lang, "stars_payment_success", stars=stars, amount=som_amount),
            reply_markup=get_main_keyboard(user_lang),
        )
        logger.info(f"Stars payment: user={message.from_user.id}, stars={stars}, som={som_amount}")
    except Exception as e:
        logger.error(f"successful_payment handler error: {e}")