import logging
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from bot.states import AdminStates
from bot.keyboards import (
    get_admin_keyboard,
    get_payment_review_keyboard,
    get_channel_management_keyboard,
    get_channels_list_keyboard,
    get_promocode_keyboard,
    get_broadcast_target_keyboard,
    get_main_keyboard,
    get_feature_management_keyboard,
    get_client_action_keyboard,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from database.database import Database
from services.channel_service import ChannelService
from translations import get_text
from config import ADMIN_IDS
import string
import random

router = Router()
logger = logging.getLogger(__name__)

def is_admin(user_id: int) -> bool:
    """Check if user is admin"""
    return user_id in ADMIN_IDS

async def notify_admins_about_payment(bot, user, amount, message_id, payment_id, source=""):
    """Notify admins about new payment"""
    from bot.keyboards import get_payment_review_keyboard

    user_link = f"@{user.username}" if user.username else f"tg://user?id={user.telegram_id}"

    # Add source indicator if payment is from help section
    source_label = "📞 Yordam bo'limi orqali" if source == "help" else ""

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
                f"📅 To'lov ID: {payment_id}\n"
            )

            if source_label:
                text += f"📍 Manba: {source_label}\n"

            text += "\n⬆️ Yuqoridagi chekni tekshiring va to'lovni tasdiqlang:"

            await bot.send_message(
                admin_id,
                text,
                reply_markup=get_payment_review_keyboard(payment_id)
            )

        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")

async def notify_other_admins_about_payment_action(bot, payment_id, action, admin_name, amount):
    """Notify other admins about payment action to prevent double processing"""
    notification_text = (
        f"⚠️ To'lov harakati:\n"
        f"🆔 To'lov #{payment_id} {action}\n"
        f"💵 Summa: {amount:,} so'm\n"
        f"👤 Admin: {admin_name}\n"
        f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, notification_text)
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id} about payment action: {e}")

@router.message(F.text == "📁 Namunalar boshqaruvi")
async def handle_samples_management_admin(message: Message):
    """Handle samples management button for admin"""
    if not is_admin(message.from_user.id):
        return
    
    from bot.keyboards import get_sample_management_keyboard
    await message.answer(
        "📁 Namunalar boshqaruvi\n\nTanlang:",
        reply_markup=get_sample_management_keyboard()
    )

@router.callback_query(F.data == "add_sample")
async def add_sample_start(callback: CallbackQuery, state: FSMContext):
    """Start adding sample process"""
    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        "📎 Namuna faylini yuboring (hujjat, rasm yoki video):",
        parse_mode=None
    )
    await state.set_state(AdminStates.waiting_for_sample_file)

@router.message(AdminStates.waiting_for_sample_file, F.document | F.photo | F.video)
async def handle_sample_file(message: Message, state: FSMContext):
    """Handle sample file upload"""
    try:
        if message.document:
            file_id = message.document.file_id
            file_type = 'document'
        elif message.photo:
            file_id = message.photo[-1].file_id
            file_type = 'photo'
        elif message.video:
            file_id = message.video.file_id
            file_type = 'video'
        else:
            await message.answer("❌ Noto'g'ri fayl turi.")
            return

        await state.update_data(file_id=file_id, file_type=file_type)
        await message.answer("📝 Namuna nomini kiriting:")
        await state.set_state(AdminStates.waiting_for_sample_title)

    except Exception as e:
        logger.error(f"Error handling sample file: {e}")
        await message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")
        await state.clear()

@router.message(F.text == "💳 To'lovlar")
async def handle_orders_request(message: Message, db: Database):
    """Handle orders/payments request"""
    if not is_admin(message.from_user.id):
        return

    pending_payments = await db.get_pending_payments()

    if not pending_payments:
        await message.answer("📋 Kutilayotgan to'lovlar yo'q.")
        return

    await message.answer(f"📋 {len(pending_payments)} ta kutilayotgan to'lov mavjud.")

    for payment in pending_payments[:5]:  # Show first 5 payments
        user = await db.get_user_by_id(payment.user_id)
        user_link = f"@{user.username}" if user.username else f"tg://user?id={user.telegram_id}"

        # Handle both datetime and string formats
        if isinstance(payment.created_at, str):
            date_str = payment.created_at[:16].replace('T', ' ') if 'T' in payment.created_at else payment.created_at[:16]
        else:
            date_str = payment.created_at.strftime('%d.%m.%Y %H:%M')

        text = (
            f"🧾 To'lov #{payment.id}\n"
            f"👤 Foydalanuvchi: {user_link}\n"
            f"💵 Summasi: {payment.amount:,} so'm\n"
            f"📅 Sana: {date_str}"
        )

        # Send screenshot first if available
        if payment.screenshot_file_id:
            try:
                await message.answer_photo(
                    photo=payment.screenshot_file_id,
                    caption=text,
                    reply_markup=get_payment_review_keyboard(payment.id)
                )
            except Exception as e:
                logger.error(f"Error sending payment screenshot: {e}")
                await message.answer(
                    text,
                    reply_markup=get_payment_review_keyboard(payment.id)
                )
        else:
            await message.answer(
                text,
                reply_markup=get_payment_review_keyboard(payment.id)
            )

@router.callback_query(F.data.startswith("adjust_amount_"))
async def adjust_payment_amount(callback: CallbackQuery, state: FSMContext, db: Database):
    """Ask admin to type the new amount manually"""
    if not is_admin(callback.from_user.id):
        return

    payment_id = int(callback.data.split("_")[2])

    try:
        payment = await db.get_payment_by_id(payment_id)
        if not payment:
            await callback.answer("❌ To'lov topilmadi.")
            return

        if payment.status != "pending":
            await callback.answer(f"❌ Bu to'lov allaqachon {payment.status} holatida.")
            return

        # Remove buttons from original payment message
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cancel_amount_input_{payment_id}")
        ]])
        sent = await callback.message.answer(
            f"💵 Yangi summani kiriting (so'mda):\n\n"
            f"Hozirgi summa: {payment.amount:,} so'm\n\n"
            f"Faqat raqam yuboring. Masalan: 25000",
            reply_markup=cancel_kb,
        )
        await state.update_data(
            adj_payment_id=payment_id,
            adj_message_id=sent.message_id,
            adj_chat_id=sent.chat.id,
            adj_orig_msg_id=callback.message.message_id,
            adj_orig_chat_id=callback.message.chat.id,
        )
        await state.set_state(AdminStates.waiting_for_payment_amount)
        await callback.answer()

    except Exception as e:
        logger.error(f"Error starting amount adjustment: {e}")
        await callback.answer("❌ Xatolik yuz berdi.")


def _fmt_date(created_at) -> str:
    """Format created_at regardless of whether it's datetime or str."""
    if hasattr(created_at, "strftime"):
        return created_at.strftime("%d.%m.%Y %H:%M")
    return str(created_at)[:16]


@router.message(AdminStates.waiting_for_payment_amount)
async def payment_amount_entered(message: Message, state: FSMContext, db: Database):
    """Handle manually typed payment amount → immediately approve & add to balance"""
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    payment_id = data.get("adj_payment_id")
    prompt_msg_id = data.get("adj_message_id")
    prompt_chat_id = data.get("adj_chat_id")
    orig_msg_id = data.get("adj_orig_msg_id")
    orig_chat_id = data.get("adj_orig_chat_id")

    raw = (message.text or "").strip().replace(" ", "").replace(",", "").replace(".", "")
    try:
        new_amount = int(raw)
        if new_amount < 1000:
            await message.answer("❌ Summa kamida 1,000 so'm bo'lishi kerak.")
            return
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting. Masalan: 25000")
        return

    await state.clear()

    # Delete admin's typed message and the prompt message
    try:
        await message.delete()
    except Exception:
        pass
    try:
        await message.bot.delete_message(chat_id=prompt_chat_id, message_id=prompt_msg_id)
    except Exception:
        pass

    try:
        payment = await db.get_payment_by_id(payment_id)
        if not payment:
            await message.answer("❌ To'lov topilmadi.")
            return
        if payment.status != "pending":
            await message.answer(f"❌ Bu to'lov allaqachon {payment.status} holatida.")
            return

        # 1. Update amount then approve
        await db.update_payment_amount(payment_id, new_amount)
        await db.update_payment_status(payment_id, "approved")

        # 2. Add balance
        user = await db.get_user_by_id(payment.user_id)
        await db.update_user_balance(user.telegram_id, new_amount)

        # 3. Referral bonus (same logic as approve_payment)
        PAYMENT_BONUS = 1000
        if user.referred_by:
            try:
                referral = await db.get_referral(user.referred_by, user.telegram_id)
                if referral and not referral.payment_bonus_given:
                    from database.database import DATABASE_FILE
                    import aiosqlite
                    async with aiosqlite.connect(DATABASE_FILE) as db_conn:
                        async with db_conn.execute(
                            "SELECT COUNT(*) FROM payments WHERE user_id = ? AND status = 'approved'",
                            (user.id,)
                        ) as cursor:
                            approved_count = (await cursor.fetchone())[0]
                    if approved_count == 1:
                        await db.update_user_balance(user.referred_by, PAYMENT_BONUS)
                        await db.update_referral_earnings(user.referred_by, user.telegram_id, PAYMENT_BONUS)
                        await db.update_payment_bonus(user.referred_by, user.telegram_id, True)
                        referrer = await db.get_user(user.referred_by)
                        if referrer:
                            bonus_text = {
                                'uz': f"💰 Sizning tavsiyangiz bo'yicha foydalanuvchi birinchi to'lovni amalga oshirdi!\n💵 +{PAYMENT_BONUS:,} so'm hisobingizga qo'shildi.",
                                'ru': f"💰 Пользователь по вашей рекомендации совершил первый платеж!\n💵 +{PAYMENT_BONUS:,} сум добавлено на ваш счет.",
                                'en': f"💰 Your referral made their first payment!\n💵 +{PAYMENT_BONUS:,} som added to your balance.",
                            }
                            try:
                                await message.bot.send_message(
                                    user.referred_by,
                                    bonus_text.get(referrer.language, bonus_text['uz'])
                                )
                            except Exception:
                                pass
            except Exception as e:
                logger.error(f"Error processing referral bonus in amount adjustment: {e}")

        # 4. Notify user
        try:
            await message.bot.send_message(
                user.telegram_id,
                f"✅ To'lovingiz tasdiqlandi! {new_amount:,} so'm hisobingizga qo'shildi."
            )
        except Exception:
            pass

        # 5. Remove all buttons from original payment message (process done)
        try:
            await message.bot.edit_message_reply_markup(
                chat_id=orig_chat_id,
                message_id=orig_msg_id,
                reply_markup=None,
            )
        except Exception:
            pass

        # 6. Confirm to admin
        user_link = f"@{user.username}" if user.username else f"ID: {user.telegram_id}"
        await message.answer(
            f"✅ To'lov #{payment_id} tasdiqlandi.\n"
            f"👤 {user_link}\n"
            f"💵 {new_amount:,} so'm hisobga qo'shildi."
        )

        # 7. Notify other admins
        admin_name = message.from_user.username or message.from_user.full_name
        await notify_other_admins_about_payment_action(
            message.bot, payment_id, "tasdiqlandi", admin_name, new_amount
        )

    except Exception as e:
        logger.error(f"Error in payment_amount_entered approval: {e}")
        await message.answer("❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.")


@router.callback_query(F.data.startswith("cancel_amount_input_"))
async def cancel_amount_input(callback: CallbackQuery, state: FSMContext, db: Database):
    """Cancel manual amount input — delete prompt, restore original message buttons"""
    if not is_admin(callback.from_user.id):
        return

    payment_id = int(callback.data.split("_")[3])
    data = await state.get_data()
    orig_msg_id = data.get("adj_orig_msg_id")
    orig_chat_id = data.get("adj_orig_chat_id")
    await state.clear()

    # Delete the prompt message
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Restore buttons on original payment message
    if orig_msg_id and orig_chat_id:
        try:
            await callback.bot.edit_message_reply_markup(
                chat_id=orig_chat_id,
                message_id=orig_msg_id,
                reply_markup=get_payment_review_keyboard(payment_id),
            )
        except Exception:
            pass

    await callback.answer("Bekor qilindi.")

@router.callback_query(F.data.startswith("cancel_adjustment_"))
async def cancel_adjustment(callback: CallbackQuery, db: Database):
    """Cancel amount adjustment"""
    if not is_admin(callback.from_user.id):
        return

    payment_id = int(callback.data.split("_")[2])

    try:
        payment = await db.get_payment_by_id(payment_id)
        if not payment:
            await callback.answer("❌ To'lov topilmadi.")
            return

        user = await db.get_user_by_id(payment.user_id)
        user_link = f"@{user.username}" if user.username else f"tg://user?id={user.telegram_id}"

        text = (
            f"🧾 To'lov #{payment.id}\n"
            f"👤 Foydalanuvchi: {user_link}\n"
            f"💵 Summasi: {payment.amount:,} so'm\n"
            f"📅 Sana: {_fmt_date(payment.created_at)}"
        )

        await callback.message.edit_text(
            text,
            reply_markup=get_payment_review_keyboard(payment_id),
            parse_mode=None
        )

    except Exception as e:
        logger.error(f"Error canceling adjustment: {e}")
        await callback.answer("❌ Xatolik yuz berdi.")

@router.callback_query(F.data.startswith("confirm_adjusted_"))
async def confirm_adjusted_payment(callback: CallbackQuery, db: Database):
    """Confirm payment with adjusted amount"""
    if not is_admin(callback.from_user.id):
        return

    payment_id = int(callback.data.split("_")[2])

    try:
        payment = await db.get_payment_by_id(payment_id)
        if not payment:
            await callback.answer("❌ To'lov topilmadi.")
            return

        if payment.status != "pending":
            await callback.answer(f"❌ Bu to'lov allaqachon {payment.status} holatida.")
            return

        # Update payment status
        await db.update_payment_status(payment_id, "approved")

        # Add balance to user with the adjusted amount
        user = await db.get_user_by_id(payment.user_id)
        await db.update_user_balance(user.telegram_id, payment.amount)

        # Check referral bonus (same as original approve logic)
        PAYMENT_BONUS = 1000
        if user.referred_by:
            try:
                referral = await db.get_referral(user.referred_by, user.telegram_id)
                if referral and not referral.payment_bonus_given:
                    from database.database import DATABASE_FILE
                    import aiosqlite
                    async with aiosqlite.connect(DATABASE_FILE) as db_conn:
                        async with db_conn.execute(
                            "SELECT COUNT(*) FROM payments WHERE user_id = ? AND status = 'approved'",
                            (user.id,)
                        ) as cursor:
                            approved_count = (await cursor.fetchone())[0]

                    if approved_count == 1:
                        await db.update_user_balance(user.referred_by, PAYMENT_BONUS)
                        await db.update_referral_earnings(user.referred_by, user.telegram_id, PAYMENT_BONUS)
                        await db.update_payment_bonus(user.referred_by, user.telegram_id, True)

                        referrer = await db.get_user(user.referred_by)
                        if referrer:
                            bonus_text = {
                                'uz': f"💰 Sizning tavsiyangiz bo'yicha foydalanuvchi birinchi to'lovni amalga oshirdi!\n💵 +{PAYMENT_BONUS:,} so'm hisobingizga qo'shildi.",
                                'ru': f"💰 Пользователь по вашей рекомендации совершил первый платеж!\n💵 +{PAYMENT_BONUS:,} сум добавлено на ваш счет.",
                                'en': f"💰 Your referral made their first payment!\n💵 +{PAYMENT_BONUS:,} som added to your balance."
                            }
                            try:
                                await callback.bot.send_message(
                                    user.referred_by,
                                    bonus_text.get(referrer.language, bonus_text['uz'])
                                )
                            except Exception as e:
                                logger.error(f"Failed to notify referrer {user.referred_by}: {e}")
                        
                        logger.info(f"✅ Payment bonus given (adjusted): referrer={user.referred_by}, referred={user.telegram_id}, amount={PAYMENT_BONUS}")
            except Exception as e:
                logger.error(f"Error processing payment referral bonus: {e}")

        # Notify user
        try:
            await callback.bot.send_message(
                user.telegram_id,
                f"✅ To'lovingiz tasdiqlandi! {payment.amount:,} so'm hisobingizga qo'shildi."
            )
        except Exception as notify_error:
            logger.error(f"Failed to notify user {user.telegram_id} about payment approval: {notify_error}")

        # Keep the message with payment info
        user_link = f"@{user.username}" if user.username else f"tg://user?id={user.telegram_id}"
        await callback.message.edit_text(
            f"✅ To'lov #{payment_id} tasdiqlandi.\n"
            f"👤 Foydalanuvchi: {user_link}\n"
            f"💵 {payment.amount:,} so'm foydalanuvchi hisobiga qo'shildi.\n"
            f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            parse_mode=None
        )

        # Notify other admins
        admin_name = callback.from_user.username or callback.from_user.full_name
        await notify_other_admins_about_payment_action(callback.bot, payment_id, "tasdiqlandi", admin_name, payment.amount)

    except Exception as e:
        logger.error(f"Error confirming adjusted payment: {e}")
        await callback.answer("❌ Xatolik yuz berdi.")

@router.callback_query(F.data.startswith("approve_payment_"))
async def approve_payment(callback: CallbackQuery, db: Database):
    """Approve payment"""
    if not is_admin(callback.from_user.id):
        return

    payment_id = int(callback.data.split("_")[2])

    try:
        # Get payment details
        payment = await db.get_payment_by_id(payment_id)
        if not payment:
            await callback.answer("❌ To'lov topilmadi.")
            return

        # Check if payment is already processed
        if payment.status != "pending":
            await callback.answer(f"❌ Bu to'lov allaqachon {payment.status} holatida.")
            return

        # Update payment status
        await db.update_payment_status(payment_id, "approved")

        # Add balance to user
        user = await db.get_user_by_id(payment.user_id)
        await db.update_user_balance(user.telegram_id, payment.amount)

        # Check if this is user's first payment and if they were referred
        # If yes, give payment bonus to referrer
        PAYMENT_BONUS = 1000
        if user.referred_by:
            try:
                # Check if referral exists and payment bonus not given yet
                referral = await db.get_referral(user.referred_by, user.telegram_id)
                if referral and not referral.payment_bonus_given:
                    # Count approved payments for this user AFTER this approval
                    from database.database import DATABASE_FILE
                    import aiosqlite
                    async with aiosqlite.connect(DATABASE_FILE) as db_conn:
                        async with db_conn.execute(
                            "SELECT COUNT(*) FROM payments WHERE user_id = ? AND status = 'approved'",
                            (user.id,)
                        ) as cursor:
                            approved_count = (await cursor.fetchone())[0]

                    # If this is the first approved payment (count = 1 after approval)
                    if approved_count == 1:
                        # Give payment bonus to referrer
                        await db.update_user_balance(user.referred_by, PAYMENT_BONUS)
                        await db.update_referral_earnings(user.referred_by, user.telegram_id, PAYMENT_BONUS)
                        await db.update_payment_bonus(user.referred_by, user.telegram_id, True)

                        # Notify referrer
                        referrer = await db.get_user(user.referred_by)
                        if referrer:
                            bonus_text = {
                                'uz': f"💰 Sizning tavsiyangiz bo'yicha foydalanuvchi birinchi to'lovni amalga oshirdi!\n💵 +{PAYMENT_BONUS:,} so'm hisobingizga qo'shildi.",
                                'ru': f"💰 Пользователь по вашей рекомендации совершил первый платеж!\n💵 +{PAYMENT_BONUS:,} сум добавлено на ваш счет.",
                                'en': f"💰 Your referral made their first payment!\n💵 +{PAYMENT_BONUS:,} som added to your balance."
                            }
                            try:
                                await callback.bot.send_message(
                                    user.referred_by,
                                    bonus_text.get(referrer.language, bonus_text['uz'])
                                )
                            except Exception as e:
                                logger.error(f"Failed to notify referrer {user.referred_by}: {e}")
                        
                        logger.info(f"✅ Payment bonus given: referrer={user.referred_by}, referred={user.telegram_id}, amount={PAYMENT_BONUS}")
            except Exception as e:
                logger.error(f"Error processing payment referral bonus: {e}")

        # Notify user
        try:
            await callback.bot.send_message(
                user.telegram_id,
                f"✅ To'lovingiz tasdiqlandi! {payment.amount:,} so'm hisobingizga qo'shildi."
            )
        except Exception as notify_error:
            logger.error(f"Failed to notify user {user.telegram_id} about payment approval: {notify_error}")

        # Keep the message with payment info
        user_link = f"@{user.username}" if user.username else f"tg://user?id={user.telegram_id}"
        await callback.message.edit_text(
            f"✅ To'lov #{payment_id} tasdiqlandi.\n"
            f"👤 Foydalanuvchi: {user_link}\n"
            f"💵 {payment.amount:,} so'm foydalanuvchi hisobiga qo'shildi.\n"
            f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            parse_mode=None
        )

        # Notify other admins
        admin_name = callback.from_user.username or callback.from_user.full_name
        await notify_other_admins_about_payment_action(callback.bot, payment_id, "tasdiqlandi", admin_name, payment.amount)

    except Exception as e:
        logger.error(f"Error approving payment: {e}")
        await callback.answer("❌ Xatolik yuz berdi.")

@router.callback_query(F.data.startswith("reject_payment_"))
async def reject_payment(callback: CallbackQuery, db: Database):
    """Reject payment"""
    if not is_admin(callback.from_user.id):
        return

    payment_id = int(callback.data.split("_")[2])

    try:
        # Get payment details
        payment = await db.get_payment_by_id(payment_id)
        if not payment:
            await callback.answer("❌ To'lov topilmadi.")
            return

        # Check if payment is already processed
        if payment.status != "pending":
            await callback.answer(f"❌ Bu to'lov allaqachon {payment.status} holatida.")
            return

        # Update payment status
        await db.update_payment_status(payment_id, "rejected")

        # Get user details
        user = await db.get_user_by_id(payment.user_id)

        # Notify user with simple message (no retry button)
        await callback.bot.send_message(
            user.telegram_id,
            get_text(user.language, "payment_rejected"),
            parse_mode="Markdown"
        )

        # Keep the message with payment info
        user_link = f"@{user.username}" if user.username else f"tg://user?id={user.telegram_id}"
        await callback.message.edit_text(
            f"❌ To'lov #{payment_id} rad etildi.\n"
            f"👤 Foydalanuvchi: {user_link}\n"
            f"💵 Summa: {payment.amount:,} so'm\n"
            f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
            f"Foydalanuvchiga xabar yuborildi.",
            parse_mode=None
        )

        # Notify other admins
        admin_name = callback.from_user.username or callback.from_user.full_name
        await notify_other_admins_about_payment_action(callback.bot, payment_id, "rad etildi", admin_name, payment.amount)

    except Exception as e:
        logger.error(f"Error rejecting payment: {e}")
        await callback.answer("❌ Xatolik yuz berdi.")

@router.message(F.text == "📢 Kanallar")
async def handle_channel_settings(message: Message):
    """Handle channel settings"""
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "📢 Kanal sozlamalari",
        reply_markup=get_channel_management_keyboard()
    )

@router.callback_query(F.data == "add_channel")
async def add_channel_start(callback: CallbackQuery, state: FSMContext):
    """Start adding channel"""
    if not is_admin(callback.from_user.id):
        return

    from bot.keyboards import get_back_to_channels_keyboard
    await callback.message.edit_text(
        "📢 Yangi kanal qo'shish\n\n"
        "Kanal ID sini kiriting (masalan: -1001234567890):",
        reply_markup=get_back_to_channels_keyboard(),
        parse_mode=None
    )
    await state.set_state(AdminStates.waiting_for_channel_id)

@router.message(AdminStates.waiting_for_channel_id)
async def add_channel_id(message: Message, state: FSMContext):
    """Handle channel ID input"""
    try:
        channel_id = message.text.strip()

        # Basic validation
        if not channel_id.startswith("-100"):
            from bot.keyboards import get_channel_error_keyboard
            await message.answer(
                "❌ Kanal ID noto'g'ri formatda. -100 bilan boshlanishi kerak.",
                reply_markup=get_channel_error_keyboard()
            )
            return

        # Validate if bot has access to this channel
        channel_service = ChannelService(message.bot)
        if not await channel_service.validate_channel(channel_id):
            from bot.keyboards import get_channel_error_keyboard
            # Get current bot username dynamically
            bot_info = await message.bot.get_me()
            bot_username = bot_info.username
            await message.answer(
                f"❌ Bot ushbu kanalga kirish huquqi yo'q!\n\n"
                f"📝 Quyidagi qadamlarni bajaring:\n"
                f"1. Kanalga @{bot_username} ni admin sifatida qo'shing\n"
                f"2. Bot uchun 'A'zolarni ko'rish' huquqini bering\n"
                f"3. Qayta urinib ko'ring",
                reply_markup=get_channel_error_keyboard()
            )
            return

        await state.update_data(channel_id=channel_id)
        await message.answer("🔗 Kanal linkini kiriting (https://t.me/channelname shaklida):")
        await state.set_state(AdminStates.waiting_for_channel_username)

    except Exception as e:
        logger.error(f"Error adding channel ID: {e}")
        await message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")

@router.message(AdminStates.waiting_for_channel_username)
async def add_channel_username(message: Message, state: FSMContext):
    """Handle channel link input"""
    link = message.text.strip()

    # Extract username from link
    if link.startswith("https://t.me/"):
        username = link.replace("https://t.me/", "")
    elif link.startswith("t.me/"):
        username = link.replace("t.me/", "")
    elif link.startswith("@"):
        username = link.replace("@", "")
    else:
        # If it's just the username without link format
        username = link

    # Store both link and username
    await state.update_data(
        channel_username=username,
        channel_link=link if link.startswith(("https://", "t.me/")) else f"https://t.me/{username}"
    )

    await message.answer("📝 Kanal nomini kiriting:")
    await state.set_state(AdminStates.waiting_for_channel_title)

@router.message(AdminStates.waiting_for_channel_title)
async def add_channel_title(message: Message, state: FSMContext, db: Database):
    """Handle channel title input and complete channel addition"""
    title = message.text.strip()
    data = await state.get_data()

    try:
        await db.add_channel(
            channel_id=data['channel_id'],
            channel_username=data['channel_username'],
            title=title
        )

        await message.answer(
            f"✅ Kanal qo'shildi:\n"
            f"📢 {title}\n"
            f"🆔 {data['channel_id']}\n"
            f"👤 @{data['channel_username']}",
            reply_markup=get_admin_keyboard()
        )

    except Exception as e:
        logger.error(f"Error adding channel: {e}")
        await message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")

    finally:
        await state.clear()

@router.callback_query(F.data == "remove_channel")
async def remove_channel_start(callback: CallbackQuery, db: Database):
    """Start removing channel"""
    if not is_admin(callback.from_user.id):
        return

    channels = await db.get_active_channels()

    if not channels:
        await callback.message.edit_text("📢 Faol kanallar yo'q.", parse_mode=None)
        return

    await callback.message.edit_text(
        "🗑 O'chirish uchun kanalni tanlang:",
        reply_markup=get_channels_list_keyboard(channels),
        parse_mode=None
    )

@router.callback_query(F.data.startswith("delete_channel_"))
async def remove_channel_confirm(callback: CallbackQuery, db: Database):
    """Remove channel"""
    if not is_admin(callback.from_user.id):
        return

    channel_id = callback.data.split("_")[2]

    try:
        await db.remove_channel(channel_id)
        await callback.message.edit_text(
            f"✅ Kanal o'chirildi: {channel_id}",
            parse_mode=None
        )
    except Exception as e:
        logger.error(f"Error removing channel: {e}")
        await callback.answer("❌ Xatolik yuz berdi.")

@router.callback_query(F.data == "list_channels")
async def list_channels(callback: CallbackQuery, db: Database):
    """List all channels"""
    if not is_admin(callback.from_user.id):
        return

    channels = await db.get_active_channels()

    if not channels:
        await callback.message.edit_text("📢 Faol kanallar yo'q.", parse_mode=None)
        return

    text = "📢 Faol kanallar:\n\n"
    for channel in channels:
        text += f"• {channel.title}\n"
        text += f"  🆔 {channel.channel_id}\n"
        if channel.channel_username:
            text += f"  👤 @{channel.channel_username}\n"
        text += "\n"

    await callback.message.edit_text(text, parse_mode=None)

@router.message(F.text == "🎟 Promokod boshqaruvi")
async def handle_promocode_management(message: Message):
    """Handle promocode management"""
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "💬 Promokod boshqaruvi",
        reply_markup=get_promocode_keyboard()
    )

@router.callback_query(F.data == "create_promocode")
async def create_promocode_start(callback: CallbackQuery, state: FSMContext):
    """Start creating promocode"""
    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        "💬 Yangi promokod yaratish\n\n"
        "Promokod nomini kiriting (yoki 'auto' deb yozing avtomatik yaratish uchun):",
        parse_mode=None
    )
    await state.set_state(AdminStates.waiting_for_promocode)

@router.message(AdminStates.waiting_for_promocode)
async def create_promocode_finish(message: Message, state: FSMContext, db: Database):
    """Complete promocode creation"""
    try:
        code_input = message.text.strip().upper()

        if code_input == "AUTO":
            # Generate random code
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        else:
            code = code_input

        # Set expiry to 24 hours from now
        expires_at = datetime.now() + timedelta(hours=24)

        promocode_id = await db.create_promocode(code, expires_at)

        await message.answer(
            f"✅ Promokod yaratildi:\n"
            f"💬 Kod: {code}\n"
            f"⏰ Amal qilish muddati: 24 soat\n"
            f"📅 Tugaydi: {expires_at.strftime('%d.%m.%Y %H:%M')}",
            reply_markup=get_admin_keyboard()
        )

    except Exception as e:
        logger.error(f"Error creating promocode: {e}")
        await message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")

    finally:
        await state.clear()

@router.callback_query(F.data == "list_promocodes")
async def list_promocodes(callback: CallbackQuery, db: Database):
    """List all promocodes"""
    if not is_admin(callback.from_user.id):
        return

    promocodes = await db.get_active_promocodes()

    if not promocodes:
        await callback.message.edit_text(
            "📋 Faol promokodlar yo'q",
            reply_markup=get_promocode_keyboard(),
            parse_mode=None
        )
        return

    text = f"📋 Faol promokodlar ({len(promocodes)} ta):\n\n"

    for promo in promocodes:
        # Handle both string and datetime expires_at
        if hasattr(promo.expires_at, 'strftime'):
            expires_str = promo.expires_at.strftime('%d.%m.%Y %H:%M')
        else:
            # If it's a string, try to parse it
            try:
                from datetime import datetime
                expires_dt = datetime.fromisoformat(str(promo.expires_at).replace('Z', '+00:00'))
                expires_str = expires_dt.strftime('%d.%m.%Y %H:%M')
            except:
                expires_str = str(promo.expires_at)

        # Count usage
        used_count = await db.count_promocode_usage(promo.id)

        text += f"🎟 **{promo.code}** ← O'chirish uchun bu nomni kiriting\n"
        text += f"📅 Tugaydi: {expires_str}\n"
        text += f"👥 Ishlatilgan: {used_count} marta\n"
        text += "➖➖➖➖➖➖➖➖\n\n"

    # Add deactivate keyboard
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🔴 Promokodni o'chirish", callback_data="deactivate_promocode"))
    keyboard.add(InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_promocode_menu"))
    keyboard.adjust(1)

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode=None)

@router.callback_query(F.data == "promocode_stats")
async def promocode_stats(callback: CallbackQuery, db: Database):
    """Show promocode statistics"""
    if not is_admin(callback.from_user.id):
        return

    # Get all promocodes with usage stats
    all_promocodes = await db.get_all_promocodes_with_stats()
    active_count = len(await db.get_active_promocodes())

    total_created = len(all_promocodes)
    total_used = sum(promo.get('usage_count', 0) for promo in all_promocodes)

    text = f"📊 Promokod statistikasi:\n\n"
    text += f"🎟 Jami yaratilgan: {total_created}\n"
    text += f"✅ Faol promokodlar: {active_count}\n"
    text += f"❌ Faolsizlashtirilgan: {total_created - active_count}\n"
    text += f"👥 Jami foydalanish: {total_used} marta\n\n"

    # Top used promocodes
    if all_promocodes:
        text += "🔥 Eng ko'p ishlatilanlar:\n"
        sorted_promos = sorted(all_promocodes, key=lambda x: x.get('usage_count', 0), reverse=True)[:5]

        for i, promo in enumerate(sorted_promos, 1):
            usage = promo.get('usage_count', 0)
            text += f"{i}. {promo['code']} - {usage} marta\n"

    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_promocode_menu"))

    await callback.message.edit_text(text, reply_markup=keyboard.as_markup(), parse_mode=None)

@router.callback_query(F.data == "deactivate_promocode")
async def start_deactivate_promocode(callback: CallbackQuery, state: FSMContext):
    """Start deactivating promocode"""
    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        "🔴 Promokodni faolsizlashtirish\n\n"
        "Faolsizlashtirmoqchi bo'lgan promokod nomini kiriting:\n"
        "Masalan: ABC12345",
        parse_mode=None
    )
    await state.set_state(AdminStates.waiting_for_deactivate_promocode)

@router.message(AdminStates.waiting_for_deactivate_promocode)
async def finish_deactivate_promocode(message: Message, state: FSMContext, db: Database):
    """Complete promocode deactivation"""
    try:
        promocode_code = message.text.strip().upper()

        # Check if promocode exists and is active
        promocode = await db.get_promocode(promocode_code)
        if not promocode:
            await message.answer("❌ Bunday nomli faol promokod topilmadi. Qayta kiriting:")
            return

        # Deactivate promocode by code
        success = await db.deactivate_promocode_by_code(promocode_code)

        if success:
            await message.answer(
                f"✅ Promokod faolsizlashtirildi!\n\n"
                f"🎟 Kod: {promocode.code}\n"
                f"🆔 ID: {promocode.id}",
                reply_markup=get_admin_keyboard()
            )
        else:
            await message.answer("❌ Promokodni faolsizlashtirishda xatolik. Qayta urinib ko'ring.")

    except Exception as e:
        logger.error(f"Error deactivating promocode: {e}")
        await message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")

    finally:
        await state.clear()

@router.callback_query(F.data == "back_to_promocode_menu")
async def back_to_promocode_menu(callback: CallbackQuery):
    """Return to promocode management menu"""
    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        "💬 Promokod boshqaruvi",
        reply_markup=get_promocode_keyboard(),
        parse_mode=None
    )

@router.callback_query(F.data == "back_to_channels")
async def back_to_channels(callback: CallbackQuery, state: FSMContext):
    """Return to channel management menu"""
    if not is_admin(callback.from_user.id):
        return

    await state.clear()
    await callback.message.edit_text(
        "📢 Kanal sozlamalari",
        reply_markup=get_channel_management_keyboard(),
        parse_mode=None
    )

@router.callback_query(F.data == "retry_channel_id")
async def retry_channel_id(callback: CallbackQuery, state: FSMContext):
    """Retry channel ID input"""
    if not is_admin(callback.from_user.id):
        return

    from bot.keyboards import get_back_to_channels_keyboard
    await callback.message.edit_text(
        "📢 Yangi kanal qo'shish\n\n"
        "Kanal ID sini kiriting (masalan: -1001234567890):",
        reply_markup=get_back_to_channels_keyboard(),
        parse_mode=None
    )
    await state.set_state(AdminStates.waiting_for_channel_id)

# Removed duplicate handler - using the first one defined above

@router.message(F.text == "👥 Foydalanuvchilar")
async def handle_users_list(message: Message, db: Database):
    """Handle users list request"""
    if not is_admin(message.from_user.id):
        return

    users = await db.get_all_users()

    text = f"👥 Jami foydalanuvchilar: {len(users)}\n\n"
    text += "So'nggi 10 ta foydalanuvchi:\n"

    for user in users[-10:]:
        username = f"@{user.username}" if user.username else "Username yo'q"
        first_name = user.first_name or "Ism yo'q"
        text += f"• {first_name} ({username})\n"
        text += f"  💰 Balans: {user.balance} so'm\n"
        text += f"  🗓 Qo'shilgan: {_fmt_date(user.created_at)[:10]}\n\n"

    await message.answer(text)

@router.message(F.text == "📊 Statistika")
async def handle_statistics(message: Message, db: Database):
    """Handle statistics request with detailed breakdown"""
    if not is_admin(message.from_user.id):
        return

    try:
        from database.database import DATABASE_FILE
        import aiosqlite

        async with aiosqlite.connect(DATABASE_FILE) as db_conn:
            # Total users
            async with db_conn.execute("SELECT COUNT(*) FROM users") as cursor:
                total_users = (await cursor.fetchone())[0]

            # Users who joined today
            async with db_conn.execute(
                "SELECT COUNT(*) FROM users WHERE date(created_at) = date('now')"
            ) as cursor:
                joined_today = (await cursor.fetchone())[0]

            # Total users who made at least one payment
            async with db_conn.execute(
                "SELECT COUNT(DISTINCT user_id) FROM payments WHERE status = 'approved'"
            ) as cursor:
                total_paid_users = (await cursor.fetchone())[0]

            # Today's revenue
            async with db_conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'approved' AND date(created_at) = date('now')"
            ) as cursor:
                revenue_today = (await cursor.fetchone())[0]

            async with db_conn.execute(
                "SELECT COUNT(*) FROM document_stats"
            ) as cursor:
                total_documents = (await cursor.fetchone())[0]

            doc_types = {
                "presentation":    ("📊 Taqdimotlar", 0),
                "independent_work":("📝 Mustaqil ishlar", 0),
                "referat":         ("📄 Referatlar", 0),
                "tezis":           ("🗒 Tezislar", 0),
                "maqola":          ("📰 Maqolalar", 0),
                "course_work":     ("📚 Kurs ishlari", 0),
                "diploma_work":    ("🎓 Diplom ishlari", 0),
                "bitiruv_ishi":    ("🏆 Bitiruv ishlari", 0),
                "dissertatsiya":   ("🎓 Dissertatsiyalar", 0),
            }
            for dtype in doc_types:
                async with db_conn.execute(
                    "SELECT COUNT(*) FROM document_stats WHERE document_type = ?",
                    (dtype,)
                ) as cursor:
                    count = (await cursor.fetchone())[0]
                    label = doc_types[dtype][0]
                    doc_types[dtype] = (label, count)

            async with db_conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'approved'"
            ) as cursor:
                total_revenue = (await cursor.fetchone())[0]

        doc_lines = "\n".join(f"  • {label}: {count} ta" for label, count in doc_types.values())
        text = (
            f"📈 Bot statistikasi:\n\n"
            f"👥 Jami foydalanuvchilar: {total_users} ta\n"
            f"🆕 Bugun qo'shilganlar: {joined_today} ta\n"
            f"💳 To'lov qilganlar: {total_paid_users} ta\n"
            f"💰 Bugungi daromad: {revenue_today:,} so'm\n"
            f"💵 Jami daromad: {total_revenue:,} so'm\n\n"
            f"📄 Yaratilgan hujjatlar: {total_documents} ta\n"
            f"{doc_lines}\n"
        )

        await message.answer(text)

    except Exception as e:
        logger.error(f"Error in statistics: {e}")
        await message.answer("❌ Statistikani olishda xatolik yuz berdi.")

@router.message(F.text == "📈 Kunlik statistika")
async def handle_daily_statistics(message: Message, db: Database):
    """Handle daily statistics request with detailed breakdown"""
    if not is_admin(message.from_user.id):
        return

    try:
        from database.database import DATABASE_FILE
        import aiosqlite

        today = datetime.now()

        # Get today's detailed statistics
        async with aiosqlite.connect(DATABASE_FILE) as db_conn:
            # Total users in database
            async with db_conn.execute("SELECT COUNT(*) FROM users") as cursor:
                total_users = (await cursor.fetchone())[0]

            # Users who started bot today (/start command)
            async with db_conn.execute(
                "SELECT COUNT(*) FROM users WHERE date(created_at) = date('now')"
            ) as cursor:
                users_started_today = (await cursor.fetchone())[0]

            # Users who made payment today
            async with db_conn.execute(
                "SELECT COUNT(DISTINCT user_id) FROM payments WHERE status = 'approved' AND date(created_at) = date('now')"
            ) as cursor:
                users_paid_today = (await cursor.fetchone())[0]

            # Number of payments today
            async with db_conn.execute(
                "SELECT COUNT(*) FROM payments WHERE status = 'approved' AND date(created_at) = date('now')"
            ) as cursor:
                payments_count_today = (await cursor.fetchone())[0]

            # Revenue today
            async with db_conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'approved' AND date(created_at) = date('now')"
            ) as cursor:
                revenue_today = (await cursor.fetchone())[0]

            async with db_conn.execute(
                "SELECT COUNT(*) FROM document_stats WHERE date(completed_at) = date('now')"
            ) as cursor:
                documents_today = (await cursor.fetchone())[0]

            doc_types_today = {
                "presentation":    ("📊 Taqdimotlar", 0),
                "independent_work":("📝 Mustaqil ishlar", 0),
                "referat":         ("📄 Referatlar", 0),
                "tezis":           ("🗒 Tezislar", 0),
                "maqola":          ("📰 Maqolalar", 0),
                "course_work":     ("📚 Kurs ishlari", 0),
                "diploma_work":    ("🎓 Diplom ishlari", 0),
                "bitiruv_ishi":    ("🏆 Bitiruv ishlari", 0),
                "dissertatsiya":   ("🎓 Dissertatsiyalar", 0),
            }
            for dtype in doc_types_today:
                async with db_conn.execute(
                    "SELECT COUNT(*) FROM document_stats WHERE date(completed_at) = date('now') AND document_type = ?",
                    (dtype,)
                ) as cursor:
                    count = (await cursor.fetchone())[0]
                    label = doc_types_today[dtype][0]
                    doc_types_today[dtype] = (label, count)

        doc_lines = "\n".join(f"  • {label}: {count} ta" for label, count in doc_types_today.values())
        text = (
            f"📈 Kunlik statistika ({today.strftime('%d.%m.%Y')})\n\n"
            f"👥 Jami foydalanuvchilar: {total_users} ta\n\n"
            f"🆕 Bugun /start bosganlar: {users_started_today} ta\n"
            f"💳 Bugun to'lov qilganlar: {users_paid_today} ta\n"
            f"📊 Bugun to'lovlar soni: {payments_count_today} ta\n"
            f"💰 Bugungi daromad: {revenue_today:,} so'm\n\n"
            f"📄 Bugun yaratilgan hujjatlar: {documents_today} ta\n"
            f"{doc_lines}\n\n"
            f"⏰ Yangilandi: {today.strftime('%d.%m.%Y %H:%M')}"
        )

        await message.answer(text)

    except Exception as e:
        logger.error(f"Error in daily statistics: {e}")
        await message.answer("❌ Kunlik statistikani olishda xatolik yuz berdi.")

@router.message(F.text == "💰 Narxlar sozlamalari")
async def handle_price_settings(message: Message):
    """Handle price settings request"""
    if not is_admin(message.from_user.id):
        return

    from config import PRESENTATION_PRICE, INDEPENDENT_WORK_PRICE, REFERAT_PRICE

    text = (
        f"💰 Joriy narxlar:\n\n"
        f"📊 Taqdimot: {PRESENTATION_PRICE:,} so'm\n"
        f"📄 Mustaqil ish: {INDEPENDENT_WORK_PRICE:,} so'm\n"
        f"📚 Referat: {REFERAT_PRICE:,} so'm\n\n"
        f"Narxlarni o'zgartirish uchun config.py faylini tahrirlang."
    )

    await message.answer(text, reply_markup=get_admin_keyboard())

@router.message(F.text == "🔧 Bot sozlamalari")
async def handle_bot_settings(message: Message):
    """Handle bot settings request"""
    if not is_admin(message.from_user.id):
        return

    from config import ADMIN_IDS, PAYMENT_CARD

    text = (
        f"🔧 Bot sozlamalari:\n\n"
        f"👨‍💼 Admin IDs: {', '.join(map(str, ADMIN_IDS))}\n"
        f"💳 To'lov kartasi: {PAYMENT_CARD}\n"
        f"🤖 Bot ishlayapti va barcha funksiyalar faol\n\n"
        f"Sozlamalarni o'zgartirish uchun config.py faylini tahrirlang."
    )

    await message.answer(text, reply_markup=get_admin_keyboard())

@router.message(F.text == "🗄 Database boshqaruvi")
async def handle_database_management(message: Message, db: Database):
    """Handle database management request"""
    if not is_admin(message.from_user.id):
        return

    try:
        from database.database import DATABASE_FILE
        import aiosqlite
        import os

        async with aiosqlite.connect(DATABASE_FILE) as db_conn:
            async with db_conn.execute("SELECT COUNT(*) FROM users") as cursor:
                total_users = (await cursor.fetchone())[0]

            async with db_conn.execute(
                "SELECT COUNT(*) FROM users WHERE date(created_at) = date('now')"
            ) as cursor:
                users_today = (await cursor.fetchone())[0]

            async with db_conn.execute(
                "SELECT COUNT(*) FROM users WHERE created_at >= datetime('now', '-7 days')"
            ) as cursor:
                users_week = (await cursor.fetchone())[0]

            async with db_conn.execute("SELECT COUNT(*) FROM document_orders") as cursor:
                total_orders = (await cursor.fetchone())[0]

            async with db_conn.execute(
                "SELECT COUNT(*) FROM document_orders WHERE status = 'completed'"
            ) as cursor:
                completed_orders = (await cursor.fetchone())[0]

            async with db_conn.execute(
                "SELECT COUNT(*) FROM document_orders WHERE status = 'failed'"
            ) as cursor:
                failed_orders = (await cursor.fetchone())[0]

            async with db_conn.execute("SELECT COUNT(*) FROM payments") as cursor:
                total_payments = (await cursor.fetchone())[0]

            async with db_conn.execute(
                "SELECT COUNT(*) FROM payments WHERE status = 'approved'"
            ) as cursor:
                approved_payments = (await cursor.fetchone())[0]

            async with db_conn.execute(
                "SELECT COUNT(*) FROM payments WHERE status = 'pending'"
            ) as cursor:
                pending_payments = (await cursor.fetchone())[0]

            async with db_conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'approved'"
            ) as cursor:
                total_revenue = (await cursor.fetchone())[0]

            async with db_conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'approved' AND date(created_at) = date('now')"
            ) as cursor:
                revenue_today = (await cursor.fetchone())[0]

            async with db_conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'approved' AND created_at >= datetime('now', '-30 days')"
            ) as cursor:
                revenue_month = (await cursor.fetchone())[0]

            async with db_conn.execute("SELECT COUNT(*) FROM document_stats") as cursor:
                total_doc_stats = (await cursor.fetchone())[0]

            async with db_conn.execute("SELECT COUNT(*) FROM referrals") as cursor:
                total_referrals = (await cursor.fetchone())[0]

        db_size_mb = round(os.path.getsize(DATABASE_FILE) / 1024 / 1024, 2) if os.path.exists(DATABASE_FILE) else 0

        text = (
            f"🗄 Database holati\n\n"
            f"👥 Foydalanuvchilar:\n"
            f"  • Jami: {total_users:,} ta\n"
            f"  • Bugun: {users_today:,} ta\n"
            f"  • Bu hafta: {users_week:,} ta\n\n"
            f"📋 Buyurtmalar:\n"
            f"  • Jami: {total_orders:,} ta\n"
            f"  • Bajarilgan: {completed_orders:,} ta\n"
            f"  • Xatolik: {failed_orders:,} ta\n\n"
            f"💳 To'lovlar:\n"
            f"  • Jami: {total_payments:,} ta\n"
            f"  • Tasdiqlangan: {approved_payments:,} ta\n"
            f"  • Kutilmoqda: {pending_payments:,} ta\n\n"
            f"💰 Daromad:\n"
            f"  • Jami (all-time): {total_revenue:,} so'm\n"
            f"  • Bu oy: {revenue_month:,} so'm\n"
            f"  • Bugun: {revenue_today:,} so'm\n\n"
            f"📄 Hujjat statistikasi: {total_doc_stats:,} ta\n"
            f"🔗 Referal havolalar: {total_referrals:,} ta\n\n"
            f"💾 Database hajmi: {db_size_mb} MB"
        )

    except Exception as e:
        logger.error(f"Error in database management: {e}")
        text = "❌ Database ma'lumotlarini olishda xatolik yuz berdi."

    await message.answer(text, reply_markup=get_admin_keyboard())

@router.message(F.text == "📤 Reklama yuborish")
async def handle_broadcast_start(message: Message, state: FSMContext):
    """Start advertisement broadcast"""
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "📢 Reklama yuborish\n\n"
        "Yubormoqchi bo'lgan reklamangizni kiriting:\n\n"
        "📝 Matn xabar\n"
        "🖼 Rasm (caption bilan)\n"
        "🎥 Video (caption bilan)\n"
        "📄 Fayl/Hujjat\n"
        "🔗 URL havola\n\n"
        "Reklama materialingizni yuboring:"
    )
    await state.set_state(AdminStates.waiting_for_broadcast_message)

@router.message(AdminStates.waiting_for_broadcast_message)
async def handle_broadcast_message(message: Message, state: FSMContext):
    """Handle advertisement content input - supports all media types"""

    # Determine content type and store appropriate data
    if message.text:
        await state.update_data(
            message_text=message.text,
            message_type="text"
        )
    elif message.photo:
        await state.update_data(
            photo_id=message.photo[-1].file_id,
            caption=message.caption or "",
            message_type="photo"
        )
    elif message.video:
        await state.update_data(
            video_id=message.video.file_id,
            caption=message.caption or "",
            message_type="video"
        )
    elif message.document:
        await state.update_data(
            document_id=message.document.file_id,
            caption=message.caption or "",
            message_type="document"
        )
    elif message.animation:
        await state.update_data(
            animation_id=message.animation.file_id,
            caption=message.caption or "",
            message_type="animation"
        )
    elif message.voice:
        await state.update_data(
            voice_id=message.voice.file_id,
            caption=message.caption or "",
            message_type="voice"
        )
    elif message.audio:
        await state.update_data(
            audio_id=message.audio.file_id,
            caption=message.caption or "",
            message_type="audio"
        )
    else:
        await message.answer("❌ Ushbu turdagi kontent qo'llab-quvvatlanmaydi.")
        return

    await message.answer(
        "📢 Kimga reklama yuborilsin?",
        reply_markup=get_broadcast_target_keyboard()
    )
    await state.set_state(AdminStates.waiting_for_broadcast_target)

@router.callback_query(F.data.startswith("broadcast_"), AdminStates.waiting_for_broadcast_target)
async def handle_broadcast_target(callback: CallbackQuery, state: FSMContext, db: Database):
    """Handle broadcast target selection and send messages"""
    if not is_admin(callback.from_user.id):
        return

    target = callback.data.split("_")[1]
    data = await state.get_data()

    # Get target users
    all_users = await db.get_all_users()

    if target == "all":
        target_users = all_users
    else:  # active (users who used the bot in last 30 days)
        cutoff_date = datetime.now() - timedelta(days=30)
        target_users = [user for user in all_users if user.updated_at >= cutoff_date]

    await callback.message.edit_text(
        f"📢 Reklama yuborilmoqda...\n"
        f"Jami: {len(target_users)} ta foydalanuvchi"
    )

    # Send advertisements based on type
    sent_count = 0
    failed_count = 0
    message_type = data.get('message_type', 'text')

    for user in target_users:
        try:
            if message_type == "text":
                await callback.bot.send_message(
                    user.telegram_id,
                    data['message_text']
                )
            elif message_type == "photo":
                await callback.bot.send_photo(
                    user.telegram_id,
                    photo=data['photo_id'],
                    caption=data.get('caption')
                )
            elif message_type == "video":
                await callback.bot.send_video(
                    user.telegram_id,
                    video=data['video_id'],
                    caption=data.get('caption')
                )
            elif message_type == "document":
                await callback.bot.send_document(
                    user.telegram_id,
                    document=data['document_id'],
                    caption=data.get('caption')
                )
            elif message_type == "animation":
                await callback.bot.send_animation(
                    user.telegram_id,
                    animation=data['animation_id'],
                    caption=data.get('caption')
                )
            elif message_type == "voice":
                await callback.bot.send_voice(
                    user.telegram_id,
                    voice=data['voice_id'],
                    caption=data.get('caption')
                )
            elif message_type == "audio":
                await callback.bot.send_audio(
                    user.telegram_id,
                    audio=data['audio_id'],
                    caption=data.get('caption')
                )

            sent_count += 1
        except Exception as e:
            logger.error(f"Failed to send {message_type} to {user.telegram_id}: {e}")
            failed_count += 1

    # Send result
    await callback.message.edit_text(
        f"✅ Reklama yuborish yakunlandi:\n\n"
        f"📊 Tur: {message_type.title()}\n"
        f"✅ {sent_count} ta yuborildi\n"
        f"❌ {failed_count} ta foydalanuvchiga yetmadi"
    )

    await state.clear()

async def _feature_keyboard(db):
    """Helper: build feature management keyboard with current statuses."""
    from bot.keyboards import get_feature_management_keyboard as _kb
    startup = await db.get_feature_status("startup_bonus")
    mahsus = await db.get_feature_status("mahsus_ishlanma")
    return _kb(startup, mahsus)

_FEATURES_TITLE = (
    "🎛 Funksiyalar boshqaruvi\n\n"
    "Quyidagi funksiyalarni yoqish/o'chirish mumkin:"
)

@router.message(F.text == "🎛 Funksiyalar boshqaruvi")
async def handle_feature_management(message: Message, db: Database):
    """Handle feature management request"""
    if not is_admin(message.from_user.id):
        return
    kb = await _feature_keyboard(db)
    await message.answer(_FEATURES_TITLE, reply_markup=kb)

@router.callback_query(F.data.startswith("toggle_startup_bonus_"))
async def toggle_startup_bonus(callback: CallbackQuery, db: Database):
    """Toggle startup bonus feature"""
    if not is_admin(callback.from_user.id):
        return
    action = callback.data.split("_")[3]
    new_status = action == "on"
    await db.set_feature_status("startup_bonus", new_status)
    status_text = "yoqildi" if new_status else "o'chirildi"
    await callback.answer(f"🎁 Start bonus {status_text}!")
    kb = await _feature_keyboard(db)
    await callback.message.edit_text(_FEATURES_TITLE, reply_markup=kb)

@router.callback_query(F.data.startswith("toggle_mahsus_ishlanma_"))
async def toggle_mahsus_ishlanma(callback: CallbackQuery, db: Database):
    """Toggle mahsus ishlanma feature"""
    if not is_admin(callback.from_user.id):
        return
    action = callback.data.split("_")[-1]
    new_status = action == "on"
    await db.set_feature_status("mahsus_ishlanma", new_status)
    status_text = "yoqildi" if new_status else "o'chirildi"
    await callback.answer(f"🔬 Mahsus ishlanma {status_text}!")
    kb = await _feature_keyboard(db)
    await callback.message.edit_text(_FEATURES_TITLE, reply_markup=kb)


# ══════════════════════════════════════════════════════════════════════════════
# MIJOZ BILAN ISHLASH
# ══════════════════════════════════════════════════════════════════════════════

def _client_info_text(user) -> str:
    name = user.first_name or "—"
    username = f"@{user.username}" if user.username else "yo'q"
    return (
        f"👤 Mijoz ma'lumotlari\n\n"
        f"🆔 ID: {user.telegram_id}\n"
        f"📛 Ism: {name}\n"
        f"🔗 Username: {username}\n"
        f"💰 Balans: {user.balance:,} so'm\n"
        f"🌐 Til: {user.language.upper()}"
    )

@router.message(F.text == "👥 Mijoz bilan ishlash")
async def client_management_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AdminStates.waiting_for_client_search)
    await message.answer(
        "🔍 Mijozni qidirish\n\n"
        "Username (@username) yoki Telegram ID raqamini yuboring:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_client_search")
        ]])
    )


@router.message(F.text == "➕ Yangi mijoz qo'shish")
async def new_client_add_start(message: Message, state: FSMContext):
    """Admin manually adds a user to DB (e.g. after DB wipe)."""
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AdminStates.waiting_for_new_client_input)
    await message.answer(
        "➕ <b>Yangi mijoz qo'shish</b>\n\n"
        "Mijozning <b>Telegram ID</b> raqamini yoki <b>@username</b> ini yuboring.\n\n"
        "💡 Agar bazada topilmasa — avtomatik qo'shiladi.\n"
        "Agar allaqachon bor bo'lsa — ma'lumotlari ko'rsatiladi.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_client_search")
        ]])
    )


def _extract_telegram_id(text: str):
    """
    Try to extract a numeric Telegram ID from various input formats:
      - Plain number: 123456789
      - tg://user?id=123456789
      - https://t.me/+123456789  (phone link — rare)
    Returns int if found, else None.
    """
    import re
    text = text.strip()
    # tg://user?id=XXXXXXX
    m = re.search(r'[?&]id=(-?\d+)', text)
    if m:
        return int(m.group(1))
    # plain number or @number
    plain = text.lstrip("@").lstrip("+")
    if re.fullmatch(r'-?\d+', plain):
        return int(plain)
    return None


@router.message(AdminStates.waiting_for_new_client_input)
async def new_client_input_handler(message: Message, state: FSMContext, db: Database):
    """Search user in DB by ID or username; create if missing. No profile-open check needed."""
    if not is_admin(message.from_user.id):
        return
    query = (message.text or "").strip()
    await state.clear()

    # ── Try to extract a numeric Telegram ID from input ────────────────────
    tg_id = _extract_telegram_id(query)

    # ── Step 1: Look up in DB ───────────────────────────────────────────────
    user = None
    if tg_id is not None:
        user = await db.get_user(tg_id)
    else:
        # Username input — search DB first
        user = await db.get_user_by_username(query.lstrip("@"))

    if user:
        await message.answer(
            f"✅ Mijoz bazada mavjud!\n\n{_client_info_text(user)}",
            reply_markup=get_client_action_keyboard(user.telegram_id, show_dismiss=True),
        )
        return

    # ── Step 2: Not in DB ───────────────────────────────────────────────────
    if tg_id is not None:
        # Numeric ID given — create directly, no API check needed
        try:
            new_user = await db.create_user(
                telegram_id=tg_id,
                username=None,
                first_name="(Qo'lda qo'shilgan)",
                language="uz",
            )
            await message.answer(
                f"✅ <b>Yangi mijoz muvaffaqiyatli qo'shildi!</b>\n\n"
                f"{_client_info_text(new_user)}\n\n"
                "⬇️ Balans qo'shish yoki boshqa amal:",
                parse_mode="HTML",
                reply_markup=get_client_action_keyboard(new_user.telegram_id, show_dismiss=True),
            )
        except Exception as e:
            logger.error(f"Error creating user {tg_id}: {e}")
            await message.answer(
                f"❌ Qo'shishda xatolik: {e}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🔄 Qayta urinish", callback_data="new_client_retry"),
                    InlineKeyboardButton(text="❌ Yopish", callback_data="cancel_client_search"),
                ]])
            )
        return

    # ── Step 3: Username not in DB — create directly with a temporary negative ID ─
    import time as _time
    uname_clean = query.lstrip("@")
    temp_id = -int(_time.time() * 1000)  # unique negative ms-timestamp
    try:
        new_user = await db.create_user(
            telegram_id=temp_id,
            username=uname_clean,
            first_name="(Qo'lda qo'shilgan)",
            language="uz",
        )
        await message.answer(
            f"✅ <b>@{uname_clean}</b> bazaga qo'shildi!\n\n"
            f"{_client_info_text(new_user)}\n\n"
            "⚡ Vaqtinchalik yozuv. Foydalanuvchi botga /start bossa — "
            "balansi avtomatik uning akkauntiga o'tadi.\n\n"
            "⬇️ Balans qo'shish yoki boshqa amal:",
            parse_mode="HTML",
            reply_markup=get_client_action_keyboard(new_user.telegram_id, show_dismiss=True),
        )
    except Exception as e:
        logger.error(f"Error creating temp user @{uname_clean}: {e}")
        await message.answer(f"❌ Qo'shishda xatolik: {e}")


@router.callback_query(F.data == "new_client_retry")
async def new_client_retry(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.set_state(AdminStates.waiting_for_new_client_input)
    await callback.message.edit_text(
        "➕ <b>Yangi mijoz qo'shish</b>\n\n"
        "Mijozning <b>Telegram ID</b> raqamini yoki <b>@username</b> ini yuboring:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_client_search")
        ]])
    )


@router.callback_query(F.data == "client_dismiss")
async def client_dismiss(callback: CallbackQuery, state: FSMContext):
    """Close the client action card (admin chose 'Not needed')."""
    if not is_admin(callback.from_user.id):
        return
    await callback.answer("Yopildi.")
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        await callback.message.edit_reply_markup(reply_markup=None)

@router.callback_query(F.data == "cancel_client_search")
async def cancel_client_search(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.clear()
    await callback.message.edit_text("Bekor qilindi.")
    await callback.answer()

@router.callback_query(F.data == "client_search_again")
async def client_search_again(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_for_client_search)
    await callback.message.edit_text(
        "🔍 Mijozni qidirish\n\n"
        "Username (@username) yoki Telegram ID raqamini yuboring:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_client_search")
        ]])
    )
    await callback.answer()

@router.message(AdminStates.waiting_for_client_search)
async def client_search_handler(message: Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        return
    query = (message.text or "").strip()
    user = None
    if query.lstrip("@").isdigit() or (query.startswith("-") and query[1:].isdigit()):
        user = await db.get_user(int(query.lstrip("@")))
    else:
        user = await db.get_user_by_username(query)

    if not user:
        await message.answer(
            "❌ Mijoz topilmadi.\n\nUsername yoki ID to'g'ri ekanini tekshiring.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔍 Qayta qidirish", callback_data="client_search_again"),
                InlineKeyboardButton(text="❌ Yopish", callback_data="cancel_client_search"),
            ]])
        )
        return

    await state.update_data(client_tg_id=user.telegram_id)
    await state.set_state(None)
    await message.answer(_client_info_text(user), reply_markup=get_client_action_keyboard(user.telegram_id))


# ── Xabar yuborish ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("client_msg_"))
async def client_msg_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    tg_id = int(callback.data.split("_")[2])
    await state.update_data(client_tg_id=tg_id, client_action_msg_id=callback.message.message_id)
    await state.set_state(AdminStates.waiting_for_client_message)
    await callback.message.edit_text(
        "📨 Mijozga yuboriladigan xabarni yozing:\n\n(Bekor qilish uchun tugmani bosing)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"client_action_cancel_{tg_id}")
        ]])
    )
    await callback.answer()

@router.message(AdminStates.waiting_for_client_message)
async def client_msg_send(message: Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    tg_id = data.get("client_tg_id")
    msg_id = data.get("client_action_msg_id")
    await state.clear()
    try:
        await message.bot.send_message(tg_id, f"📩 Admin xabari:\n\n{message.text}")
        result = "✅ Xabar muvaffaqiyatli yuborildi."
    except Exception as e:
        logger.error(f"Error sending message to client {tg_id}: {e}")
        result = f"❌ Xabar yuborib bo'lmadi: {e}"
    try:
        await message.delete()
    except Exception:
        pass
    user = await db.get_user(tg_id)
    await message.bot.edit_message_text(
        chat_id=message.chat.id, message_id=msg_id,
        text=f"{result}\n\n{_client_info_text(user)}",
        reply_markup=get_client_action_keyboard(tg_id),
    )


# ── Balans qo'shish ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("client_add_"))
async def client_add_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    tg_id = int(callback.data.split("_")[2])
    await state.update_data(client_tg_id=tg_id, client_action_msg_id=callback.message.message_id)
    await state.set_state(AdminStates.waiting_for_client_add_amount)
    await callback.message.edit_text(
        "➕ Qo'shilacak summani kiriting (so'mda):\n\nMasalan: 10000",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"client_action_cancel_{tg_id}")
        ]])
    )
    await callback.answer()

@router.message(AdminStates.waiting_for_client_add_amount)
async def client_add_amount(message: Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    tg_id = data.get("client_tg_id")
    msg_id = data.get("client_action_msg_id")
    raw = (message.text or "").strip().replace(" ", "").replace(",", "")
    try:
        amount = int(raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Faqat musbat raqam kiriting.")
        return

    try:
        await message.delete()
    except Exception:
        pass

    await state.update_data(pending_amount=amount)
    await state.set_state(None)

    user = await db.get_user(tg_id)
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"cladok_{tg_id}"),
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"client_action_cancel_{tg_id}"),
    ]])
    await message.bot.edit_message_text(
        chat_id=message.chat.id, message_id=msg_id,
        text=(
            f"➕ Tasdiqlaysizmi?\n\n"
            f"👤 Mijoz: {_client_info_text(user).splitlines()[0]}\n"
            f"💰 Hozirgi balans: {user.balance:,} so'm\n"
            f"➕ Qo'shiladi: {amount:,} so'm\n"
            f"💵 Yangi balans: {user.balance + amount:,} so'm"
        ),
        reply_markup=confirm_kb,
    )

@router.callback_query(F.data.startswith("cladok_"))
async def client_add_confirm(callback: CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback.from_user.id):
        return
    tg_id = int(callback.data.split("_")[1])
    data = await state.get_data()
    amount = data.get("pending_amount", 0)
    await state.clear()

    await db.update_user_balance(tg_id, amount)
    try:
        await callback.bot.send_message(
            tg_id,
            f"✅ Hisobingizga {amount:,} so'm qo'shildi.\n💰 Yangi balans: {(await db.get_user(tg_id)).balance:,} so'm"
        )
    except Exception:
        pass
    user = await db.get_user(tg_id)
    await callback.message.edit_text(
        f"✅ {amount:,} so'm qo'shildi.\n\n{_client_info_text(user)}",
        reply_markup=get_client_action_keyboard(tg_id),
    )
    await callback.answer()


# ── Balansdan yechish ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("client_deduct_"))
async def client_deduct_start(callback: CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback.from_user.id):
        return
    tg_id = int(callback.data.split("_")[2])
    user = await db.get_user(tg_id)
    await state.update_data(client_tg_id=tg_id, client_action_msg_id=callback.message.message_id)
    await state.set_state(AdminStates.waiting_for_client_deduct_amount)
    await callback.message.edit_text(
        f"➖ Yechilacak summani kiriting (so'mda):\n\nHozirgi balans: {user.balance:,} so'm\n\nMasalan: 5000",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"client_action_cancel_{tg_id}")
        ]])
    )
    await callback.answer()

@router.message(AdminStates.waiting_for_client_deduct_amount)
async def client_deduct_amount(message: Message, state: FSMContext, db: Database):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    tg_id = data.get("client_tg_id")
    msg_id = data.get("client_action_msg_id")
    raw = (message.text or "").strip().replace(" ", "").replace(",", "")
    try:
        amount = int(raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Faqat musbat raqam kiriting.")
        return
    user = await db.get_user(tg_id)
    if user.balance < amount:
        await message.answer(f"❌ Balans yetarli emas. Hozirgi balans: {user.balance:,} so'm")
        return
    await state.clear()
    await db.update_user_balance(tg_id, -amount)
    try:
        await message.bot.send_message(tg_id, f"⚠️ Hisobingizdan {amount:,} so'm yechildi. Yangi balans: {(await db.get_user(tg_id)).balance:,} so'm")
    except Exception:
        pass
    try:
        await message.delete()
    except Exception:
        pass
    user = await db.get_user(tg_id)
    await message.bot.edit_message_text(
        chat_id=message.chat.id, message_id=msg_id,
        text=f"✅ {amount:,} so'm yechildi.\n\n{_client_info_text(user)}",
        reply_markup=get_client_action_keyboard(tg_id),
    )


# ── Bekor qilish (amaldan qaytish) ─────────────────────────────────────────

@router.callback_query(F.data.startswith("client_action_cancel_"))
async def client_action_cancel(callback: CallbackQuery, state: FSMContext, db: Database):
    if not is_admin(callback.from_user.id):
        return
    tg_id = int(callback.data.split("_")[3])
    await state.clear()
    user = await db.get_user(tg_id)
    if user:
        await callback.message.edit_text(_client_info_text(user), reply_markup=get_client_action_keyboard(tg_id))
    else:
        await callback.message.edit_text("Bekor qilindi.")
    await callback.answer()


@router.callback_query(F.data == "mass_gift_start")
async def mass_gift_start(callback: CallbackQuery, state: FSMContext):
    """Start mass gift process"""
    if not is_admin(callback.from_user.id):
        return

    from bot.keyboards import get_back_to_features_keyboard
    await callback.message.edit_text(
        "💰 Barchaga sovg'a yuborish\n\n"
        "Qancha summa yubormoqchisiz? (so'mda)\n"
        "Masalan: 5000",
        reply_markup=get_back_to_features_keyboard()
    )
    await state.set_state(AdminStates.waiting_for_gift_amount)

@router.callback_query(F.data == "back_to_features")
async def back_to_features_handler(callback: CallbackQuery, db: Database):
    """Go back to feature management menu"""
    if not is_admin(callback.from_user.id):
        return
    kb = await _feature_keyboard(db)
    await callback.message.edit_text(_FEATURES_TITLE, reply_markup=kb)

@router.callback_query(F.data == "mass_take_back_start")
async def mass_take_back_start(callback: CallbackQuery, state: FSMContext):
    """Start mass take back process"""
    if not is_admin(callback.from_user.id):
        return

    from bot.keyboards import get_back_to_features_keyboard
    await callback.message.edit_text(
        "💸 Barchadan pulni qaytib olish\n\n"
        "Qancha summa yechib olmoqchisiz? (so'mda)\n"
        "Masalan: 5000",
        reply_markup=get_back_to_features_keyboard()
    )
    await state.set_state(AdminStates.waiting_for_take_back_amount)

@router.message(AdminStates.waiting_for_take_back_amount)
async def process_take_back_amount(message: Message, state: FSMContext, db: Database):
    """Process take back amount and deduct from all users"""
    if not is_admin(message.from_user.id):
        return

    try:
        amount = int(message.text.strip())
        if amount <= 0:
            await message.answer("❌ Summa 0 dan katta bo'lishi kerak!")
            return

        # Get all users
        all_users = await db.get_all_users()
        
        if not all_users:
            await message.answer("❌ Foydalanuvchilar topilmadi!")
            await state.clear()
            return

        # Update balances for all users (deduct amount)
        success_count = 0
        for user in all_users:
            try:
                # Deducting balance (passing negative amount)
                await db.update_user_balance(user.telegram_id, -amount)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to deduct money from user {user.telegram_id}: {e}")

        await message.answer(
            f"✅ Barchadan pul qaytib olindi!\n\n"
            f"💸 Summa: {amount:,} so'm\n"
            f"👤 Foydalanuvchilar: {success_count} ta"
        )
        await state.clear()

    except ValueError:
        await message.answer("❌ Iltimos, faqat son kiriting!")
    except Exception as e:
        logger.error(f"Error in process_take_back_amount: {e}")
        await message.answer("❌ Xatolik yuz berdi.")

@router.message(AdminStates.waiting_for_gift_amount)
async def process_gift_amount(message: Message, state: FSMContext, db: Database):
    """Process gift amount and send to all users"""
    if not is_admin(message.from_user.id):
        return

    try:
        amount = int(message.text.strip())
        if amount <= 0:
            await message.answer("❌ Summa 0 dan katta bo'lishi kerak!")
            return

        # Get all users
        all_users = await db.get_all_users()
        
        if not all_users:
            await message.answer("❌ Foydalanuvchilar topilmadi!")
            await state.clear()
            return

        # Update balances for all users
        success_count = 0
        for user in all_users:
            try:
                await db.update_user_balance(user.telegram_id, amount)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to add gift to user {user.telegram_id}: {e}")

        await message.answer(
            f"✅ Sovg'a muvaffaqiyatli yuborildi!\n\n"
            f"💰 Summa: {amount:,} so'm\n"
            f"👥 {success_count} ta foydalanuvchiga qo'shildi"
        )
        await state.clear()

    except ValueError:
        await message.answer("❌ Iltimos, faqat raqam kiriting!")
        return

@router.message(F.text == "👤 Foydalanuvchi rejimi")
async def switch_to_user_mode(message: Message, db: Database):
    """Switch to user mode"""
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "👤 Foydalanuvchi rejimiga o'tdingiz",
        reply_markup=get_main_keyboard("uz", True)
    )

@router.message(F.text == "📁 Namunalar boshqaruvi")
async def handle_sample_management(message: Message):
    """Handle sample management"""
    if not is_admin(message.from_user.id):
        return

    from bot.keyboards import get_sample_management_keyboard
    await message.answer(
        "📁 Namunalar boshqaruvi",
        reply_markup=get_sample_management_keyboard()
    )

@router.callback_query(F.data == "add_sample")
async def add_sample_start(callback: CallbackQuery, state: FSMContext):
    """Start adding sample file"""
    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        "📁 Yangi namuna qo'shish\n\n"
        "Namuna faylini yuboring (hujjat yoki rasm):",
        parse_mode=None
    )
    await state.set_state(AdminStates.waiting_for_sample_file)

@router.message(AdminStates.waiting_for_sample_file)
async def add_sample_file(message: Message, state: FSMContext):
    """Handle sample file upload"""
    try:
        if message.document:
            file_id = message.document.file_id
            file_type = 'document'
        elif message.photo:
            file_id = message.photo[-1].file_id
            file_type = 'photo'
        else:
            await message.answer("❌ Faqat hujjat yoki rasm yuboring.")
            return

        await state.update_data(file_id=file_id, file_type=file_type)
        await message.answer("📝 Namuna nomini kiriting:")
        await state.set_state(AdminStates.waiting_for_sample_title)

    except Exception as e:
        logger.error(f"Error handling sample file: {e}")
        await message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")
        await state.clear()

@router.message(AdminStates.waiting_for_sample_title)
async def add_sample_title(message: Message, state: FSMContext):
    """Handle sample title input"""
    title = message.text.strip()
    await state.update_data(title=title)
    
    await message.answer("📝 Namuna tavsifini kiriting (yoki 'skip' deb yozing):")
    await state.set_state(AdminStates.waiting_for_sample_description)

@router.message(AdminStates.waiting_for_sample_description)
async def add_sample_description(message: Message, state: FSMContext, db: Database):
    """Handle sample description and save"""
    try:
        description = message.text.strip() if message.text.lower() != 'skip' else ''
        data = await state.get_data()

        sample_id = await db.add_sample_file(
            title=data['title'],
            description=description,
            file_id=data['file_id'],
            file_type=data['file_type']
        )

        await message.answer(
            f"✅ Namuna qo'shildi:\n"
            f"📄 {data['title']}\n"
            f"🆔 ID: {sample_id}",
            reply_markup=get_admin_keyboard()
        )

    except Exception as e:
        logger.error(f"Error adding sample: {e}")
        await message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")

    finally:
        await state.clear()

@router.callback_query(F.data == "delete_sample")
async def delete_sample_start(callback: CallbackQuery, db: Database):
    """Start deleting sample"""
    if not is_admin(callback.from_user.id):
        return

    samples = await db.get_active_sample_files()

    if not samples:
        await callback.message.edit_text("📁 Namunalar yo'q.", parse_mode=None)
        return

    from bot.keyboards import get_samples_list_keyboard
    await callback.message.edit_text(
        "🗑 O'chirish uchun namunani tanlang:",
        reply_markup=get_samples_list_keyboard(samples),
        parse_mode=None
    )

@router.callback_query(F.data.startswith("delete_sample_"))
async def delete_sample_confirm(callback: CallbackQuery, db: Database):
    """Delete sample file"""
    if not is_admin(callback.from_user.id):
        return

    sample_id = int(callback.data.split("_")[2])

    try:
        sample = await db.get_sample_file(sample_id)
        if sample:
            await db.delete_sample_file(sample_id)
            await callback.message.edit_text(
                f"✅ Namuna o'chirildi: {sample['title']}",
                parse_mode=None
            )
        else:
            await callback.answer("❌ Namuna topilmadi.")
    except Exception as e:
        logger.error(f"Error deleting sample: {e}")
        await callback.answer("❌ Xatolik yuz berdi.")

@router.callback_query(F.data == "list_samples")
async def list_samples_admin(callback: CallbackQuery, db: Database):
    """List all samples for admin"""
    if not is_admin(callback.from_user.id):
        return

    samples = await db.get_active_sample_files()

    if not samples:
        await callback.message.edit_text("📁 Namunalar yo'q.", parse_mode=None)
        return

    text = f"📁 Barcha namunalar ({len(samples)} ta):\n\n"
    for sample in samples:
        text += f"📄 {sample['title']}\n"
        text += f"🆔 ID: {sample['id']}\n"
        if sample['description']:
            text += f"📝 {sample['description']}\n"
        text += f"📅 {sample['created_at']}\n"
        text += "➖➖➖➖➖➖➖➖\n\n"

    await callback.message.edit_text(text, parse_mode=None)

@router.callback_query(F.data == "back_to_sample_menu")
async def back_to_sample_menu(callback: CallbackQuery):
    """Return to sample management menu"""
    if not is_admin(callback.from_user.id):
        return

    from bot.keyboards import get_sample_management_keyboard
    await callback.message.edit_text(
        "📁 Namunalar boshqaruvi",
        reply_markup=get_sample_management_keyboard(),
        parse_mode=None
    )

@router.message(F.text == "🚫 Foydalanuvchilarni bloklash")
async def handle_block_user_menu(message: Message):
    """Handle block user management menu"""
    if not is_admin(message.from_user.id):
        return

    from bot.keyboards import get_block_user_keyboard
    await message.answer(
        "🚫 Foydalanuvchilarni bloklash boshqaruvi",
        reply_markup=get_block_user_keyboard()
    )

@router.callback_query(F.data == "block_user")
async def start_block_user(callback: CallbackQuery, state: FSMContext):
    """Start blocking a user"""
    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        "🚫 Foydalanuvchini bloklash\n\n"
        "Bloklash uchun foydalanuvchi ma'lumotini kiriting:\n"
        "• Telegram ID: 7223515801\n"
        "• Username: @username\n"
        "• Link: tg://user?id=7223515801\n\n"
        "Bir vaqtning o'zida bir nechta foydalanuvchini bloklash uchun ularni probel bilan ajrating:\n"
        "Misol: 7223515801 @username tg://user?id=8232539555",
        parse_mode=None
    )
    await state.set_state(AdminStates.waiting_for_block_user)

@router.message(AdminStates.waiting_for_block_user)
async def process_block_user(message: Message, state: FSMContext, db: Database):
    """Process user blocking"""
    try:
        input_text = message.text.strip()
        
        # Parse input - can be multiple users separated by space
        user_inputs = input_text.split()
        blocked_count = 0
        already_blocked = 0
        not_found = []
        
        for user_input in user_inputs:
            telegram_id = None
            username = None
            
            # Extract telegram_id from different formats
            if user_input.startswith("tg://user?id="):
                telegram_id = int(user_input.split("=")[1])
                # Try to get username from database
                user = await db.get_user(telegram_id)
                username = user.username if user else None
            elif user_input.startswith("@"):
                username = user_input[1:]
                # Find user by username
                all_users = await db.get_all_users()
                for u in all_users:
                    if u.username and u.username.lower() == username.lower():
                        telegram_id = u.telegram_id
                        username = u.username
                        break
            elif user_input.isdigit():
                telegram_id = int(user_input)
                # Try to get username from database
                user = await db.get_user(telegram_id)
                username = user.username if user else None
            
            if telegram_id:
                # Check if already blocked
                is_blocked = await db.is_user_blocked(telegram_id)
                if is_blocked:
                    already_blocked += 1
                else:
                    await db.block_user(
                        telegram_id=telegram_id,
                        username=username or "Unknown",
                        blocked_by=message.from_user.id,
                        reason="Adminlar tomonidan bloklangan"
                    )
                    blocked_count += 1
            else:
                not_found.append(user_input)
        
        # Send result
        result_text = f"✅ Bloklash natijasi:\n\n"
        if blocked_count > 0:
            result_text += f"🚫 Bloklandi: {blocked_count} ta\n"
        if already_blocked > 0:
            result_text += f"⚠️ Allaqachon bloklangan: {already_blocked} ta\n"
        if not_found:
            result_text += f"❌ Topilmadi: {', '.join(not_found)}\n"
        
        await message.answer(result_text, reply_markup=get_admin_keyboard())
        
    except Exception as e:
        logger.error(f"Error blocking users: {e}")
        await message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")
    
    finally:
        await state.clear()

@router.callback_query(F.data == "unblock_user")
async def show_blocked_users_for_unblock(callback: CallbackQuery, db: Database):
    """Show blocked users for unblocking"""
    if not is_admin(callback.from_user.id):
        return

    blocked_users = await db.get_blocked_users()
    
    if not blocked_users:
        await callback.message.edit_text(
            "📋 Bloklangan foydalanuvchilar yo'q.",
            parse_mode=None
        )
        return

    from bot.keyboards import get_blocked_users_keyboard
    await callback.message.edit_text(
        "✅ Blokdan chiqarish uchun foydalanuvchini tanlang:",
        reply_markup=get_blocked_users_keyboard(blocked_users),
        parse_mode=None
    )

@router.callback_query(F.data.startswith("unblock_"))
async def unblock_user_confirm(callback: CallbackQuery, db: Database):
    """Unblock a user"""
    if not is_admin(callback.from_user.id):
        return

    telegram_id = int(callback.data.split("_")[1])
    
    try:
        await db.unblock_user(telegram_id)
        await callback.answer("✅ Foydalanuvchi blokdan chiqarildi!")
        
        # Refresh the list
        blocked_users = await db.get_blocked_users()
        if blocked_users:
            from bot.keyboards import get_blocked_users_keyboard
            await callback.message.edit_text(
                "✅ Blokdan chiqarish uchun foydalanuvchini tanlang:",
                reply_markup=get_blocked_users_keyboard(blocked_users),
                parse_mode=None
            )
        else:
            from bot.keyboards import get_block_user_keyboard
            await callback.message.edit_text(
                "✅ Barcha foydalanuvchilar blokdan chiqarildi.",
                reply_markup=get_block_user_keyboard(),
                parse_mode=None
            )
    except Exception as e:
        logger.error(f"Error unblocking user: {e}")
        await callback.answer("❌ Xatolik yuz berdi.")

@router.callback_query(F.data == "list_blocked")
async def list_blocked_users(callback: CallbackQuery, db: Database):
    """List all blocked users"""
    if not is_admin(callback.from_user.id):
        return

    blocked_users = await db.get_blocked_users()
    
    if not blocked_users:
        await callback.message.edit_text(
            "📋 Bloklangan foydalanuvchilar yo'q.",
            parse_mode=None
        )
        return

    text = f"📋 Bloklangan foydalanuvchilar ({len(blocked_users)} ta):\n\n"
    
    for user in blocked_users:
        username_display = f"@{user['username']}" if user['username'] else "Username yo'q"
        text += f"🚫 {username_display}\n"
        text += f"   ID: {user['telegram_id']}\n"
        if user['reason']:
            text += f"   Sabab: {user['reason']}\n"
        text += f"   Sana: {user['blocked_at']}\n"
        text += "➖➖➖➖➖➖➖➖\n\n"

    from bot.keyboards import get_block_user_keyboard
    await callback.message.edit_text(text, reply_markup=get_block_user_keyboard(), parse_mode=None)

@router.callback_query(F.data == "back_to_block_menu")
async def back_to_block_menu(callback: CallbackQuery):
    """Return to block user management menu"""
    if not is_admin(callback.from_user.id):
        return

    from bot.keyboards import get_block_user_keyboard
    await callback.message.edit_text(
        "🚫 Foydalanuvchilarni bloklash boshqaruvi",
        reply_markup=get_block_user_keyboard(),
        parse_mode=None
    )

@router.message(F.text == "🤖 AI modelni almashtirish")
async def handle_ai_model_settings(message: Message, db: Database):
    """Handle AI model settings"""
    if not is_admin(message.from_user.id):
        return

    from config import AI_MODELS
    from bot.keyboards import get_ai_model_selection_keyboard
    
    current_model_key = await db.get_current_ai_model()
    current_model = AI_MODELS.get(current_model_key, AI_MODELS["gemini_25_flash"])
    
    text = (
        "🤖 AI model sozlamalari\n\n"
        f"📌 Hozirgi model: {current_model['name']}\n"
        f"💰 Narxi: {current_model['price']}\n"
        f"📝 {current_model['description']}\n\n"
        "Quyidagi modellardan birini tanlang:"
    )
    
    await message.answer(
        text,
        reply_markup=get_ai_model_selection_keyboard(current_model_key)
    )

@router.callback_query(F.data.startswith("select_ai_model_"))
async def select_ai_model(callback: CallbackQuery, db: Database):
    """Select AI model"""
    if not is_admin(callback.from_user.id):
        return

    from config import AI_MODELS
    from bot.keyboards import get_ai_model_selection_keyboard
    from services.ai_service import AIService
    
    model_key = callback.data.replace("select_ai_model_", "")
    
    if model_key not in AI_MODELS:
        await callback.answer("❌ Model topilmadi.")
        return
    
    current_model_key = await db.get_current_ai_model()
    
    if model_key == current_model_key:
        await callback.answer("Bu model allaqachon tanlangan!")
        return
    
    success = await db.set_current_ai_model(model_key)
    
    if success:
        AIService.clear_model_cache()
        model_info = AI_MODELS[model_key]
        await callback.answer(f"✅ {model_info['name']} tanlandi!")
        await callback.message.delete()
    else:
        await callback.answer("❌ Xatolik yuz berdi.")