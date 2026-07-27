import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from bot.keyboards import get_settings_keyboard, get_language_keyboard, get_main_keyboard
from bot.states import SettingsStates
from translations import get_text
from database.database import Database
from datetime import datetime

router = Router()
logger = logging.getLogger(__name__)

# Settings menu items in different languages
SETTINGS_TEXTS = ["⚙️ Sozlamalar", "⚙️ Настройки", "⚙️ Settings"]

@router.message(F.text.in_(SETTINGS_TEXTS))
async def handle_settings_request(message: Message, state: FSMContext, user_lang: str):
    """Handle settings request"""
    await state.clear()  # Clear any active state
    await message.answer(
        get_text(user_lang, "settings_menu"),
        reply_markup=get_settings_keyboard(user_lang)
    )

# Handle individual settings options
@router.callback_query(F.data == "change_language")
async def handle_change_language_option(callback: CallbackQuery, user_lang: str):
    """Handle change language option"""
    await callback.message.edit_text(
        get_text(user_lang, "choose_language"),
        reply_markup=get_language_keyboard()
    )

@router.callback_query(F.data == "enter_promocode")
async def handle_enter_promocode_option(callback: CallbackQuery, state: FSMContext, user_lang: str):
    """Handle enter promocode option"""
    await callback.message.edit_text("🎟 Promokodni kiriting:")
    await state.set_state(SettingsStates.waiting_for_promocode)

@router.callback_query(F.data.startswith("lang_"))
async def handle_language_change(callback: CallbackQuery, db: Database):
    """Handle language change from settings"""
    new_language = callback.data.split("_")[1]
    user_id = callback.from_user.id

    # Update user language
    await db.update_user_language(user_id, new_language)

    await callback.message.edit_text(
        get_text(new_language, "language_changed"),
        reply_markup=None
    )

    media_enabled = await db.get_feature_status("media")
    book_translate_enabled = await db.get_feature_status("book_translate")
    await callback.message.answer(
        "🎓 Bot ishga tayyor!",
        reply_markup=get_main_keyboard(new_language, media_enabled=media_enabled, book_translate_enabled=book_translate_enabled)
    )

@router.callback_query(F.data == "retry_promocode")
async def handle_retry_promocode(callback: CallbackQuery, state: FSMContext, user_lang: str):
    """Handle retry promocode input"""
    await callback.message.edit_text("🎟 Promokodni kiriting:")
    await state.set_state(SettingsStates.waiting_for_promocode)

@router.callback_query(F.data == "back_to_main")
async def handle_back_to_main(callback: CallbackQuery, state: FSMContext, user_lang: str):
    """Handle back to main menu from promocode error"""
    await state.clear()
    await callback.message.delete()
    await callback.message.answer(
        "🎓 Bot ishga tayyor!",
        reply_markup=get_main_keyboard(user_lang)
    )

@router.message(SettingsStates.waiting_for_promocode)
async def handle_settings_promocode_input(message: Message, state: FSMContext, db: Database, user_lang: str, user):
    """Handle promocode input from settings"""
    promocode_text = message.text.strip().upper()

    # Get promocode from database
    promocode = await db.get_promocode(promocode_text)

    if not promocode:
        from bot.keyboards import get_promocode_error_keyboard
        await message.answer(
            "❌ Noto'g'ri promokod.",
            reply_markup=get_promocode_error_keyboard(user_lang)
        )
        return

    # Check if promocode is expired
    # Parse expires_at if it's a string
    if isinstance(promocode.expires_at, str):
        from datetime import datetime as dt
        expires_dt = dt.fromisoformat(promocode.expires_at.replace('Z', '+00:00'))
    else:
        expires_dt = promocode.expires_at

    if expires_dt < datetime.now():
        from bot.keyboards import get_promocode_error_keyboard
        await message.answer(
            "❌ Promokodning amal qilish muddati tugagan.",
            reply_markup=get_promocode_error_keyboard(user_lang)
        )
        return

    # Check if user already used this promocode
    is_used = await db.is_promocode_used(user.id, promocode.id)
    if is_used:
        from bot.keyboards import get_promocode_error_keyboard
        await message.answer(
            "❌ Siz bu promokodni allaqachon ishlatgansiz.",
            reply_markup=get_promocode_error_keyboard(user_lang)
        )
        return

    # Apply promocode - add balance to user
    await db.mark_promocode_used(user.id, promocode.id)

    # Add balance to user (10,000 som - enough for 1-2 documents)
    bonus_amount = 10000
    await db.update_user_balance(user.telegram_id, bonus_amount)

    # Clear state
    await state.clear()

    # Send success message
    success_text = {
        'uz': f"✅ Promokod muvaffaqiyatli qo'llandi!\n💰 Hisobingizga {bonus_amount:,} so'm qo'shildi.",
        'ru': f"✅ Промокод успешно применен!\n💰 На ваш счет добавлено {bonus_amount:,} сум.",
        'en': f"✅ Promocode successfully applied!\n💰 {bonus_amount:,} som added to your balance."
    }

    await message.answer(
        success_text.get(user_lang, success_text['uz']),
        reply_markup=get_main_keyboard(user_lang)
    )