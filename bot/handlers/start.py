import logging
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.keyboards import get_language_keyboard, get_main_keyboard, get_subscription_check_keyboard
from database.database import Database
from services.channel_service import ChannelService
from translations import get_text
from config import ADMIN_IDS

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("start"))
async def start_command(message: Message, state: FSMContext, db: Database):
    """Handle /start command"""
    # IMPORTANT: Clear any active state when /start is pressed
    await state.clear()
    
    user_id = message.from_user.id
    user = await db.get_user(user_id)

    # Extract referral code from command if present (e.g., /start ref_ABC123)
    referral_code = None
    referred_by_id = None
    if message.text and len(message.text.split()) > 1:
        command_args = message.text.split()[1]
        if command_args.startswith("ref_"):
            referral_code = command_args[4:]  # Remove "ref_" prefix
            
            # Get referrer by referral code
            referrer = await db.get_user_by_referral_code(referral_code)
            if referrer and referrer.telegram_id != user_id:
                referred_by_id = referrer.telegram_id
                await state.update_data(referred_by=referred_by_id)

    if not user:
        # Check if admin pre-added this user by username (temp negative ID record)
        temp_balance = 0
        username_now = message.from_user.username
        if username_now:
            temp_user = await db.get_user_by_username(username_now)
            if temp_user and temp_user.telegram_id < 0:
                temp_balance = temp_user.balance or 0
                # Remove the temporary placeholder record
                try:
                    from database.database import DATABASE_FILE
                    import aiosqlite
                    async with aiosqlite.connect(DATABASE_FILE) as _db:
                        await _db.execute("DELETE FROM users WHERE telegram_id = ?", (temp_user.telegram_id,))
                        await _db.commit()
                    logger.info(f"Merged temp record for @{username_now} (balance={temp_balance}) into real user {user_id}")
                except Exception as merge_err:
                    logger.warning(f"Could not delete temp user record: {merge_err}")

        # CRITICAL: Create user IMMEDIATELY on /start to prevent silent failures
        logger.info(f"Creating new user on /start: telegram_id={user_id}, username={username_now}, referred_by={referred_by_id}")
        try:
            user = await db.create_user(
                telegram_id=user_id,
                username=username_now,
                first_name=message.from_user.first_name,
                language="uz",  # Default language, will be updated when user selects
                referred_by=referred_by_id
            )
            logger.info(f"✅ User created successfully on /start: user_id={user_id}")

            # Transfer pre-added balance from temp record if any
            if temp_balance > 0:
                await db.update_user_balance(user_id, temp_balance)
                logger.info(f"✅ Transferred pre-added balance {temp_balance} to user {user_id}")
                try:
                    await message.bot.send_message(
                        user_id,
                        f"💰 Hisobingizga <b>{temp_balance:,} so'm</b> qo'shib qo'yilgan edi — muvaffaqiyatli o'tkazildi!",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

            # Check if startup bonus is enabled and add 5000 so'm
            startup_bonus_enabled = await db.get_feature_status("startup_bonus")
            if startup_bonus_enabled:
                STARTUP_BONUS = 5000
                await db.update_user_balance(user_id, STARTUP_BONUS)
                logger.info(f"✅ Startup bonus {STARTUP_BONUS} added to user {user_id}")
            
            # Process referral signup bonus if applicable
            if referred_by_id:
                try:
                    # Create referral record
                    await db.create_referral(referred_by_id, user_id)

                    # Give 2500 som signup bonus to referrer
                    SIGNUP_BONUS = 2500
                    await db.update_user_balance(referred_by_id, SIGNUP_BONUS)
                    await db.update_referral_earnings(referred_by_id, user_id, SIGNUP_BONUS)
                    await db.update_signup_bonus(referred_by_id, user_id, True)

                    # Notify referrer
                    referrer_user = await db.get_user(referred_by_id)
                    if referrer_user:
                        bonus_text = {
                            'uz': f"🎉 Yangi foydalanuvchi sizning havolangiz orqali botga qo'shildi!\n💰 +{SIGNUP_BONUS:,} so'm hisobingizga qo'shildi.",
                            'ru': f"🎉 Новый пользователь присоединился к боту по вашей ссылке!\n💰 +{SIGNUP_BONUS:,} сум добавлено на ваш счет.",
                            'en': f"🎉 New user joined the bot via your referral link!\n💰 +{SIGNUP_BONUS:,} som added to your balance."
                        }
                        try:
                            await message.bot.send_message(
                                referred_by_id,
                                bonus_text.get(referrer_user.language, bonus_text['uz'])
                            )
                        except Exception as e:
                            logger.error(f"Failed to notify referrer {referred_by_id}: {e}")
                except Exception as e:
                    logger.error(f"Error processing referral: {e}")
        except Exception as e:
            logger.error(f"❌ CRITICAL: Failed to create user on /start {user_id}: {e}", exc_info=True)
            await message.answer(
                "❌ Xatolik yuz berdi. Iltimos, qaytadan /start bosing.\n\n"
                "❌ Произошла ошибка. Пожалуйста, нажмите /start снова.\n\n"
                "❌ An error occurred. Please press /start again."
            )
            return
        
        # New user - show language selection
        await message.answer(
            "@EDUfail_bot sizga mustaqil ish referat va taqdimotlarni tez va sifatli yaratib beradi.\n"
            "3 tilda\n\n"
            "Tilni tanlang / Выберите язык / Choose language:",
            reply_markup=get_language_keyboard()
        )
    else:
        # Existing user - show brief welcome back, then check channel subscription
        welcome_texts = {
            'uz': "👋 Xush kelibsiz! @Edufayl_bot — akademik hujjatlar yaratish boti.",
            'ru': "👋 Добро пожаловать! @Edufayl_bot — бот для создания академических документов.",
            'en': "👋 Welcome back! @Edufayl_bot — academic document creation bot.",
        }
        lang = user.language if user.language in welcome_texts else 'uz'
        await message.answer(welcome_texts[lang])
        await check_subscription_and_show_menu(message, user, db)

@router.callback_query(F.data.startswith("lang_"))
async def language_selected(callback: CallbackQuery, state: FSMContext, db: Database):
    """Handle language selection - only update language preference"""
    language = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    logger.info(f"Language selection callback: user_id={user_id}, language={language}")

    # Get user (should exist from /start handler)
    user = await db.get_user(user_id)
    
    if not user:
        # This should NOT happen if /start worked correctly
        logger.error(f"❌ CRITICAL: User not found in language_selected callback: user_id={user_id}")
        await callback.answer(
            "❌ Xatolik yuz berdi. Iltimos, /start bosing.\n\n"
            "❌ Произошла ошибка. Пожалуйста, нажмите /start.\n\n"
            "❌ An error occurred. Please press /start.",
            show_alert=True
        )
        return
    
    # Update language preference
    await db.update_user_language(user_id, language)
    user.language = language
    logger.info(f"✅ Language updated: user_id={user_id}, new_language={language}")

    # Delete the language selection message
    await callback.message.delete()

    # Check channel subscription
    await check_subscription_and_show_menu(callback.message, user, db)

async def check_subscription_and_show_menu(message: Message, user, db: Database):
    """Check channel subscription and show main menu"""
    channels = await db.get_active_channels()

    if channels:
        # Check subscription to all required channels
        channel_service = ChannelService(message.bot)
        is_subscribed = await channel_service.check_user_subscription(user.telegram_id, channels)

        if not is_subscribed:
            # Show subscription requirement
            if user.language == "uz":
                text = "📢 Botdan foydalanish uchun quyidagi kanallarga a'zo bo'lishingiz shart:\n\n👇 Kanalga o'tish uchun tugmani bosing:"
            elif user.language == "ru":
                text = "📢 Для использования бота необходимо<bos> подписаться на следующие каналы:\n\n👇 Нажмите кнопку для перехода в канал:"
            else:  # en
                text = "📢 To use the bot, you must subscribe to the following channels:\n\n👇 Click the button to go to the channel:"

            await message.answer(
                text,
                reply_markup=get_subscription_check_keyboard(user.language, channels)
            )
            return

    # Show main menu with language selected message
    presentation_enabled = await db.get_feature_status("presentation")
    independent_work_enabled = await db.get_feature_status("independent_work")
    referat_enabled = await db.get_feature_status("referat")
    media_enabled = await db.get_feature_status("media")
    book_translate_enabled = await db.get_feature_status("book_translate")
    mahsus_ishlanma_enabled = await db.get_feature_status("mahsus_ishlanma")

    await message.answer(
        get_text(user.language, "language_selected"),
        reply_markup=get_main_keyboard(user.language, presentation_enabled, independent_work_enabled, referat_enabled, media_enabled=media_enabled, book_translate_enabled=book_translate_enabled, mahsus_ishlanma_enabled=mahsus_ishlanma_enabled)
    )

@router.callback_query(F.data == "check_subscription")
async def check_subscription(callback: CallbackQuery, db: Database, user_lang: str):
    """Handle subscription check"""
    user_id = callback.from_user.id
    channels = await db.get_active_channels()

    if channels:
        channel_service = ChannelService(callback.message.bot)
        is_subscribed = await channel_service.check_user_subscription(user_id, channels)

        if is_subscribed:
            media_enabled = await db.get_feature_status("media")
            book_translate_enabled = await db.get_feature_status("book_translate")
            mahsus_ishlanma_enabled = await db.get_feature_status("mahsus_ishlanma")
            await callback.message.edit_text(
                get_text(user_lang, "subscription_verified"),
                reply_markup=None
            )
            await callback.message.answer(
                "🎓 Bot ishga tayyor!",
                reply_markup=get_main_keyboard(user_lang, media_enabled=media_enabled, book_translate_enabled=book_translate_enabled, mahsus_ishlanma_enabled=mahsus_ishlanma_enabled)
            )
        else:
            await callback.answer(
                get_text(user_lang, "subscription_not_verified"),
                show_alert=True
            )
    else:
        # No channels required
        media_enabled = await db.get_feature_status("media")
        book_translate_enabled = await db.get_feature_status("book_translate")
        mahsus_ishlanma_enabled = await db.get_feature_status("mahsus_ishlanma")
        await callback.message.edit_text(
            get_text(user_lang, "subscription_verified"),
            reply_markup=None
        )
        await callback.message.answer(
            "🎓 Bot ishga tayyor!",
            reply_markup=get_main_keyboard(user_lang, media_enabled=media_enabled, book_translate_enabled=book_translate_enabled, mahsus_ishlanma_enabled=mahsus_ishlanma_enabled)
        )

@router.message(Command("admin"))
async def admin_command(message: Message):
    """Handle /admin command"""
    user_id = message.from_user.id
    if user_id in ADMIN_IDS:
        from bot.keyboards import get_admin_keyboard
        await message.answer(
            "👨‍💼 Admin panel",
            reply_markup=get_admin_keyboard()
        )
    else:
        await message.answer("❌ Sizda admin huquqi yo'q.")

@router.message(StateFilter(None))
async def handle_unknown_message(message: Message, state: FSMContext, db: Database):
    """Handle any unrecognized message - catch-all handler (only when no active state)"""
    user_id = message.from_user.id
    user = await db.get_user(user_id)

    if not user:
        await message.answer(
            "👋 Salom! Botdan foydalanish uchun /start buyrug'ini bosing.\n\n"
            "👋 Привет! Нажмите /start для использования бота.\n\n"
            "👋 Hello! Press /start to use the bot."
        )
    else:
        if user.language == "uz":
            text = "❓ Iltimos, quyidagi tugmalardan birini tanlang:"
        elif user.language == "ru":
            text = "❓ Пожалуйста, выберите одну из кнопок ниже:"
        else:
            text = "❓ Please select one of the buttons below:"

        media_enabled = await db.get_feature_status("media")
        await message.answer(
            text,
            reply_markup=get_main_keyboard(user.language, media_enabled=media_enabled)
        )