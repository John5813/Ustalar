"""
Premium taqdimot handleri — Ustalar loyihasidan olingan yangi taqdimot tizimi.
Mavjud hujjat xizmatlariga halaqit qilmaydi, to'liq mustaqil modul.
"""
import asyncio
import logging
import os

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.states import PremiumPresentationStates
from database.database import Database
from translations import get_text

router = Router()
logger = logging.getLogger(__name__)

MIN_SLIDES = 5
MAX_SLIDES = 30

# Narx (so'm) — slide soni bo'yicha
def _get_price(slide_count: int) -> int:
    if slide_count <= 10:
        return 15000
    elif slide_count <= 20:
        return 25000
    else:
        return 35000


def _back_text(lang: str) -> str:
    if lang == "ru": return "🔙 Назад"
    if lang == "en": return "🔙 Back"
    return "🔙 Orqaga"


def _slide_count_keyboard(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for n in [5, 8, 10, 12, 15, 20]:
        price = _get_price(n)
        builder.button(text=f"{n} ta | {price:,} so'm", callback_data=f"prem_ppt_count:{n}")
    builder.button(text=_back_text(lang), callback_data="prem_ppt_back")
    builder.adjust(2)
    return builder.as_markup()


def _confirm_keyboard(lang: str, slide_count: int, price: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if lang == "ru":
        builder.button(text=f"✅ Оплатить {price:,} сум", callback_data="prem_ppt_confirm")
        builder.button(text="🔙 Назад", callback_data="prem_ppt_recount")
    elif lang == "en":
        builder.button(text=f"✅ Pay {price:,} soʻm", callback_data="prem_ppt_confirm")
        builder.button(text="🔙 Back", callback_data="prem_ppt_recount")
    else:
        builder.button(text=f"✅ To'lash {price:,} so'm", callback_data="prem_ppt_confirm")
        builder.button(text="🔙 Orqaga", callback_data="prem_ppt_recount")
    builder.adjust(1)
    return builder.as_markup()


# ──────────────────────────────────────────────────────────────── ENTRY POINT

@router.message(F.text.in_(["⭐ Premium taqdimot", "⭐ Премиум презентация", "⭐ Premium presentation"]))
async def premium_presentation_start(message: Message, state: FSMContext, db: Database):
    """Premium taqdimot tugmasi bosilganda"""
    await state.clear()
    user = await db.get_user(message.from_user.id)
    lang = user.language if user else "uz"

    msgs = {
        "uz": (
            "⭐ <b>Premium Taqdimot</b>\n\n"
            "Bu yangi avlod taqdimot tizimi — AI yordamida professional slaydlar yaratadi:\n\n"
            "✅ Har slayd uchun alohida dizayn\n"
            "✅ Avtomatik rasm generatsiyasi\n"
            "✅ Vizual sifat nazorati (AI ko'rib chiqadi)\n"
            "✅ 15 ta professional layout turi\n\n"
            "📝 <b>Taqdimot mavzusini kiriting:</b>"
        ),
        "ru": (
            "⭐ <b>Премиум Презентация</b>\n\n"
            "Новая система создания презентаций с помощью AI:\n\n"
            "✅ Уникальный дизайн для каждого слайда\n"
            "✅ Автоматическая генерация изображений\n"
            "✅ Визуальный контроль качества (AI проверяет)\n"
            "✅ 15 профессиональных типов макетов\n\n"
            "📝 <b>Введите тему презентации:</b>"
        ),
        "en": (
            "⭐ <b>Premium Presentation</b>\n\n"
            "A new generation AI-powered presentation system:\n\n"
            "✅ Unique design for each slide\n"
            "✅ Automatic image generation\n"
            "✅ Visual quality control (AI reviews)\n"
            "✅ 15 professional layout types\n\n"
            "📝 <b>Enter the presentation topic:</b>"
        ),
    }

    await state.set_state(PremiumPresentationStates.waiting_for_topic)
    back_kb = InlineKeyboardBuilder()
    back_kb.button(text=_back_text(lang), callback_data="prem_ppt_back")
    await message.answer(msgs.get(lang, msgs["uz"]), parse_mode="HTML", reply_markup=back_kb.as_markup())


# ──────────────────────────────────────────────────────────────── TOPIC

@router.message(PremiumPresentationStates.waiting_for_topic)
async def premium_ppt_got_topic(message: Message, state: FSMContext, db: Database):
    user = await db.get_user(message.from_user.id)
    lang = user.language if user else "uz"
    topic = (message.text or "").strip()

    if len(topic) < 3:
        await message.answer("❌ Mavzu juda qisqa. Kamida 3 ta belgi kiriting.")
        return

    await state.update_data(topic=topic)
    await state.set_state(PremiumPresentationStates.waiting_for_slide_count)

    msgs = {
        "uz": f"📋 Mavzu: <b>{topic}</b>\n\n📊 Necha slayd kerak?",
        "ru": f"📋 Тема: <b>{topic}</b>\n\n📊 Сколько слайдов нужно?",
        "en": f"📋 Topic: <b>{topic}</b>\n\n📊 How many slides do you need?",
    }
    await message.answer(msgs.get(lang, msgs["uz"]), parse_mode="HTML",
                         reply_markup=_slide_count_keyboard(lang))


# ──────────────────────────────────────────────────────────────── SLIDE COUNT

@router.callback_query(F.data.startswith("prem_ppt_count:"), PremiumPresentationStates.waiting_for_slide_count)
async def premium_ppt_got_count(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    user = await db.get_user(callback.from_user.id)
    lang = user.language if user else "uz"

    slide_count = int(callback.data.split(":")[1])
    price = _get_price(slide_count)
    data = await state.get_data()
    topic = data.get("topic", "")

    await state.update_data(slide_count=slide_count, price=price)

    msgs = {
        "uz": (
            f"⭐ <b>Premium Taqdimot</b>\n\n"
            f"📋 Mavzu: <b>{topic}</b>\n"
            f"📊 Slaydlar: <b>{slide_count} ta</b>\n"
            f"💰 Narx: <b>{price:,} so'm</b>\n\n"
            f"Hisobingizdan yechiladi. Tasdiqlaysizmi?"
        ),
        "ru": (
            f"⭐ <b>Премиум Презентация</b>\n\n"
            f"📋 Тема: <b>{topic}</b>\n"
            f"📊 Слайдов: <b>{slide_count}</b>\n"
            f"💰 Цена: <b>{price:,} сум</b>\n\n"
            f"Будет списано с вашего баланса. Подтверждаете?"
        ),
        "en": (
            f"⭐ <b>Premium Presentation</b>\n\n"
            f"📋 Topic: <b>{topic}</b>\n"
            f"📊 Slides: <b>{slide_count}</b>\n"
            f"💰 Price: <b>{price:,} soʻm</b>\n\n"
            f"Will be deducted from your balance. Confirm?"
        ),
    }
    await callback.message.edit_text(
        msgs.get(lang, msgs["uz"]),
        parse_mode="HTML",
        reply_markup=_confirm_keyboard(lang, slide_count, price)
    )


@router.callback_query(F.data == "prem_ppt_recount", PremiumPresentationStates.waiting_for_slide_count)
async def premium_ppt_recount(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    user = await db.get_user(callback.from_user.id)
    lang = user.language if user else "uz"
    data = await state.get_data()
    topic = data.get("topic", "")

    msgs = {
        "uz": f"📋 Mavzu: <b>{topic}</b>\n\n📊 Necha slayd kerak?",
        "ru": f"📋 Тема: <b>{topic}</b>\n\n📊 Сколько слайдов нужно?",
        "en": f"📋 Topic: <b>{topic}</b>\n\n📊 How many slides do you need?",
    }
    await callback.message.edit_text(msgs.get(lang, msgs["uz"]), parse_mode="HTML",
                                     reply_markup=_slide_count_keyboard(lang))


# ──────────────────────────────────────────────────────────────── CONFIRM & GENERATE

@router.callback_query(F.data == "prem_ppt_confirm", PremiumPresentationStates.waiting_for_slide_count)
async def premium_ppt_confirm(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    user = await db.get_user(callback.from_user.id)
    lang = user.language if user else "uz"
    data = await state.get_data()

    topic = data.get("topic", "")
    slide_count = data.get("slide_count", 10)
    price = data.get("price", 15000)

    # Balans tekshirish
    if user.balance < price:
        shortage = price - user.balance
        msgs = {
            "uz": (
                f"❌ <b>Hisobingizda mablag' yetarli emas</b>\n\n"
                f"💰 Kerakli: {price:,} so'm\n"
                f"💳 Mavjud: {user.balance:,} so'm\n"
                f"📉 Yetishmaydi: {shortage:,} so'm\n\n"
                f"To'lov bo'limiga o'ting va hisobni to'ldiring."
            ),
            "ru": (
                f"❌ <b>Недостаточно средств</b>\n\n"
                f"💰 Нужно: {price:,} сум\n"
                f"💳 Доступно: {user.balance:,} сум\n"
                f"📉 Не хватает: {shortage:,} сум\n\n"
                f"Пополните баланс в разделе оплаты."
            ),
            "en": (
                f"❌ <b>Insufficient balance</b>\n\n"
                f"💰 Required: {price:,} soʻm\n"
                f"💳 Available: {user.balance:,} soʻm\n"
                f"📉 Shortfall: {shortage:,} soʻm\n\n"
                f"Please top up your balance in the payment section."
            ),
        }
        await callback.message.edit_text(msgs.get(lang, msgs["uz"]), parse_mode="HTML")
        await state.clear()
        return

    # Balansdan yechish
    await db.update_user_balance(callback.from_user.id, -price)
    await state.set_state(PremiumPresentationStates.generating)

    total_chunks = max(1, (slide_count + 4) // 5)
    status_msgs = {
        "uz": (
            f"⚙️ <b>{topic}</b>\n"
            f"📄 {slide_count} ta slayd tayyorlanmoqda...\n\n"
            f"⏳ Kontent 1/{total_chunks} bo'lak..."
        ),
        "ru": (
            f"⚙️ <b>{topic}</b>\n"
            f"📄 Готовим {slide_count} слайдов...\n\n"
            f"⏳ Контент 1/{total_chunks} часть..."
        ),
        "en": (
            f"⚙️ <b>{topic}</b>\n"
            f"📄 Preparing {slide_count} slides...\n\n"
            f"⏳ Content 1/{total_chunks} chunk..."
        ),
    }

    status = await callback.message.edit_text(
        status_msgs.get(lang, status_msgs["uz"]), parse_mode="HTML"
    )

    loop = asyncio.get_event_loop()

    def progress_cb(done_chunk: int, total: int):
        async def _edit():
            try:
                msgs2 = {
                    "uz": (
                        f"⚙️ <b>{topic}</b>\n"
                        f"📄 {slide_count} ta slayd\n\n"
                        f"⏳ Kontent: {done_chunk}/{total} bo'lak tayyor..."
                    ),
                    "ru": (
                        f"⚙️ <b>{topic}</b>\n"
                        f"📄 {slide_count} слайдов\n\n"
                        f"⏳ Контент: {done_chunk}/{total} частей готово..."
                    ),
                    "en": (
                        f"⚙️ <b>{topic}</b>\n"
                        f"📄 {slide_count} slides\n\n"
                        f"⏳ Content: {done_chunk}/{total} chunks done..."
                    ),
                }
                await status.edit_text(msgs2.get(lang, msgs2["uz"]), parse_mode="HTML")
            except Exception:
                pass
        asyncio.run_coroutine_threadsafe(_edit(), loop)

    try:
        from services.premium_presentation.pipeline import (
            generate_brief_chunked,
            canvas_validation_and_fix,
            run_visual_qa_and_fix,
        )
        from services.premium_presentation.renderer import build_presentation

        # 1 — Brief yaratish
        brief = await loop.run_in_executor(
            None, generate_brief_chunked, topic, slide_count, progress_cb
        )

        step2 = {
            "uz": (
                f"⚙️ <b>{topic}</b>\n"
                f"✅ Kontent tayyor: {len(brief.slides)} slayd\n"
                f"⏳ Strukturaviy tekshiruv..."
            ),
            "ru": (
                f"⚙️ <b>{topic}</b>\n"
                f"✅ Контент готов: {len(brief.slides)} слайдов\n"
                f"⏳ Структурная проверка..."
            ),
            "en": (
                f"⚙️ <b>{topic}</b>\n"
                f"✅ Content ready: {len(brief.slides)} slides\n"
                f"⏳ Structural check..."
            ),
        }
        await status.edit_text(step2.get(lang, step2["uz"]), parse_mode="HTML")

        # 2 — Kanvas validatsiyasi
        brief = await loop.run_in_executor(None, canvas_validation_and_fix, brief, topic)

        step3 = {
            "uz": (
                f"⚙️ <b>{topic}</b>\n"
                f"✅ Kontent: {len(brief.slides)} slayd\n"
                f"✅ Strukturaviy tekshiruv o'tdi\n"
                f"⏳ Slaydlar chizilmoqda..."
            ),
            "ru": (
                f"⚙️ <b>{topic}</b>\n"
                f"✅ Контент: {len(brief.slides)} слайдов\n"
                f"✅ Структурная проверка пройдена\n"
                f"⏳ Рисуем слайды..."
            ),
            "en": (
                f"⚙️ <b>{topic}</b>\n"
                f"✅ Content: {len(brief.slides)} slides\n"
                f"✅ Structural check passed\n"
                f"⏳ Drawing slides..."
            ),
        }
        await status.edit_text(step3.get(lang, step3["uz"]), parse_mode="HTML")

        # 3 — Render
        pptx_path = await loop.run_in_executor(None, build_presentation, brief)

        step4 = {
            "uz": (
                f"⚙️ <b>{topic}</b>\n"
                f"✅ Kontent: {len(brief.slides)} slayd\n"
                f"✅ Strukturaviy tekshiruv o'tdi\n"
                f"✅ Slaydlar chizildi\n"
                f"⏳ Vizual sifat nazorati..."
            ),
            "ru": (
                f"⚙️ <b>{topic}</b>\n"
                f"✅ Контент: {len(brief.slides)} слайдов\n"
                f"✅ Структурная проверка пройдена\n"
                f"✅ Слайды нарисованы\n"
                f"⏳ Визуальный контроль качества..."
            ),
            "en": (
                f"⚙️ <b>{topic}</b>\n"
                f"✅ Content: {len(brief.slides)} slides\n"
                f"✅ Structural check passed\n"
                f"✅ Slides drawn\n"
                f"⏳ Visual quality check..."
            ),
        }
        await status.edit_text(step4.get(lang, step4["uz"]), parse_mode="HTML")

        # 4 — Vizual QA
        final_path = await loop.run_in_executor(
            None, run_visual_qa_and_fix, pptx_path, brief, topic
        )

    except Exception as e:
        logger.exception("Premium taqdimot generatsiyasida xato: %s", e)
        # Balansni qaytarish
        await db.update_user_balance(callback.from_user.id, price)
        err_msgs = {
            "uz": (
                f"❌ Xatolik yuz berdi:\n{str(e)[:300]}\n\n"
                f"💰 {price:,} so'm hisobingizga qaytarildi.\n"
                f"Qayta urinib ko'ring."
            ),
            "ru": (
                f"❌ Произошла ошибка:\n{str(e)[:300]}\n\n"
                f"💰 {price:,} сум возвращены на баланс.\n"
                f"Попробуйте снова."
            ),
            "en": (
                f"❌ An error occurred:\n{str(e)[:300]}\n\n"
                f"💰 {price:,} soʻm refunded to your balance.\n"
                f"Please try again."
            ),
        }
        try:
            await status.edit_text(err_msgs.get(lang, err_msgs["uz"]), parse_mode="HTML")
        except Exception:
            pass
        await state.clear()
        return

    # Tayyor — yuborish
    done_msgs = {
        "uz": f"✅ <b>{topic}</b> — tayyor!\n📊 {len(brief.slides)} slayd | Yuborilmoqda...",
        "ru": f"✅ <b>{topic}</b> — готово!\n📊 {len(brief.slides)} слайдов | Отправляю...",
        "en": f"✅ <b>{topic}</b> — done!\n📊 {len(brief.slides)} slides | Sending...",
    }
    try:
        await status.edit_text(done_msgs.get(lang, done_msgs["uz"]), parse_mode="HTML")
    except Exception:
        pass

    filename = f"Premium_{topic[:30].replace(' ', '_')}.pptx"
    with open(final_path, "rb") as f:
        await callback.message.answer_document(document=f, filename=filename)

    # Temp faylni o'chirish
    try:
        os.remove(final_path)
    except Exception:
        pass

    await state.clear()


# ──────────────────────────────────────────────────────────────── BACK

@router.callback_query(F.data == "prem_ppt_back")
async def premium_ppt_back(callback: CallbackQuery, state: FSMContext, db: Database):
    await callback.answer()
    await state.clear()
    user = await db.get_user(callback.from_user.id)
    lang = user.language if user else "uz"
    from bot.keyboards import get_main_keyboard
    from database.database import Database as DB
    media_enabled = await db.get_feature_status("media")
    book_translate_enabled = await db.get_feature_status("book_translate")
    mahsus_ishlanma_enabled = await db.get_feature_status("mahsus_ishlanma")
    await callback.message.delete()
    await callback.message.answer(
        "🏠 Bosh menyu",
        reply_markup=get_main_keyboard(
            lang,
            media_enabled=media_enabled,
            book_translate_enabled=book_translate_enabled,
            mahsus_ishlanma_enabled=mahsus_ishlanma_enabled,
        )
    )
