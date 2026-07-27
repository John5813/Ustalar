from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from typing import List, Optional
from translations import get_text
from config import EXTRAS_PRICES

def _back_text(lang: str) -> str:
    if lang == "ru": return "🔙 Назад"
    if lang == "en": return "🔙 Back"
    return "🔙 Orqaga"

def get_back_inline_keyboard(lang: str, callback_data: str) -> InlineKeyboardMarkup:
    """Single back button inline keyboard for text-input prompts"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text=_back_text(lang), callback_data=callback_data))
    return keyboard.as_markup()

def get_language_keyboard() -> InlineKeyboardMarkup:
    """Language selection keyboard"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang_uz"))
    keyboard.add(InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"))
    keyboard.add(InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_source_selection_keyboard(lang: str = "uz") -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardBuilder()
    labels = {
        "uz": ("📝 Mavzu asosida", "🌐 Kitob yoki sayt asosida"),
        "ru": ("📝 По теме", "🌐 На основе книги или сайта"),
        "en": ("📝 By topic", "🌐 Based on book or website"),
    }
    topic_label, book_label = labels.get(lang, labels["uz"])
    keyboard.add(InlineKeyboardButton(text=topic_label, callback_data="doc_source_topic"))
    keyboard.add(InlineKeyboardButton(text=book_label, callback_data="doc_source_book"))
    keyboard.add(InlineKeyboardButton(text=_back_text(lang), callback_data="back_to_main"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_doc_language_keyboard(lang: str = "uz", back_callback: str = "back_to_main") -> InlineKeyboardMarkup:
    """Document language selection keyboard"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="doc_lang_uz"))
    keyboard.add(InlineKeyboardButton(text="🇷🇺 Русский", callback_data="doc_lang_ru"))
    keyboard.add(InlineKeyboardButton(text="🇬🇧 English", callback_data="doc_lang_en"))
    keyboard.add(InlineKeyboardButton(text=_back_text(lang), callback_data=back_callback))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_plan_slide_keyboard(language: str) -> InlineKeyboardMarkup:
    """Plan slide choice keyboard"""
    keyboard = InlineKeyboardBuilder()
    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="✅ Ha", callback_data="plan_slide_yes"))
        keyboard.add(InlineKeyboardButton(text="❌ Yo'q", callback_data="plan_slide_no"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="✅ Да", callback_data="plan_slide_yes"))
        keyboard.add(InlineKeyboardButton(text="❌ Нет", callback_data="plan_slide_no"))
    else:
        keyboard.add(InlineKeyboardButton(text="✅ Yes", callback_data="plan_slide_yes"))
        keyboard.add(InlineKeyboardButton(text="❌ No", callback_data="plan_slide_no"))
    keyboard.adjust(2)
    return keyboard.as_markup()

def get_icon_choice_keyboard(language: str) -> InlineKeyboardMarkup:
    """Icon choice keyboard"""
    keyboard = InlineKeyboardBuilder()
    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="✅ Ha, ikonka qo'shish", callback_data="icon_yes"))
        keyboard.add(InlineKeyboardButton(text="❌ Yo'q, ikonkasiz", callback_data="icon_no"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="✅ Да, добавить иконки", callback_data="icon_yes"))
        keyboard.add(InlineKeyboardButton(text="❌ Нет, без иконок", callback_data="icon_no"))
    else:
        keyboard.add(InlineKeyboardButton(text="✅ Yes, add icons", callback_data="icon_yes"))
        keyboard.add(InlineKeyboardButton(text="❌ No, without icons", callback_data="icon_no"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_settings_keyboard(language: str) -> InlineKeyboardMarkup:
    """Settings menu keyboard"""
    keyboard = InlineKeyboardBuilder()

    # Language change
    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="🌍 Tilni o'zgartirish", callback_data="change_language"))
        keyboard.add(InlineKeyboardButton(text="🎟 Promokod kiritish", callback_data="enter_promocode"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="🌍 Изменить язык", callback_data="change_language"))
        keyboard.add(InlineKeyboardButton(text="🎟 Ввести промокод", callback_data="enter_promocode"))
    else:  # en
        keyboard.add(InlineKeyboardButton(text="🌍 Change language", callback_data="change_language"))
        keyboard.add(InlineKeyboardButton(text="🎟 Enter promocode", callback_data="enter_promocode"))

    keyboard.adjust(1)
    return keyboard.as_markup()

def get_article_page_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    """Article page count selection keyboard"""
    keyboard = InlineKeyboardBuilder()
    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="4-5 varoq - 5000 so'm", callback_data="art_pages_4_5"))
        keyboard.add(InlineKeyboardButton(text="5-7 varoq - 7000 so'm", callback_data="art_pages_5_7"))
        keyboard.add(InlineKeyboardButton(text="7-10 varoq - 10000 so'm", callback_data="art_pages_7_10"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="4-5 страниц - 5000 сум", callback_data="art_pages_4_5"))
        keyboard.add(InlineKeyboardButton(text="5-7 страниц - 7000 сум", callback_data="art_pages_5_7"))
        keyboard.add(InlineKeyboardButton(text="7-10 страниц - 10000 сум", callback_data="art_pages_7_10"))
    else:
        keyboard.add(InlineKeyboardButton(text="4-5 pages - 5000 som", callback_data="art_pages_4_5"))
        keyboard.add(InlineKeyboardButton(text="5-7 pages - 7000 som", callback_data="art_pages_5_7"))
        keyboard.add(InlineKeyboardButton(text="7-10 pages - 10000 som", callback_data="art_pages_7_10"))
    keyboard.add(InlineKeyboardButton(text=_back_text(language), callback_data="back_to_author_name"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_main_keyboard(language: str, presentation_enabled: bool = True, independent_work_enabled: bool = True, referat_enabled: bool = True, course_work_enabled: bool = True, tezis_enabled: bool = True, media_enabled: bool = True, diploma_work_enabled: bool = True, maqola_enabled: bool = True, pdf_convert_enabled: bool = True, book_translate_enabled: bool = True, mahsus_ishlanma_enabled: bool = True) -> ReplyKeyboardMarkup:
    """Main reply keyboard with feature toggles"""
    keyboard = ReplyKeyboardBuilder()

    keyboard.add(KeyboardButton(text=get_text(language, "main_menu.other_services")))

    # Premium taqdimot — yangi tizim (Ustalar loyihasidan)
    keyboard.add(KeyboardButton(text=get_text(language, "main_menu.premium_presentation")))

    if presentation_enabled:
        keyboard.add(KeyboardButton(text=get_text(language, "main_menu.presentation")))
    if independent_work_enabled:
        keyboard.add(KeyboardButton(text=get_text(language, "main_menu.independent_work")))
    if referat_enabled:
        keyboard.add(KeyboardButton(text=get_text(language, "main_menu.referat")))
    if course_work_enabled:
        keyboard.add(KeyboardButton(text=get_text(language, "main_menu.course_work")))
    # mahsus_ishlanma button temporarily hidden
    # if mahsus_ishlanma_enabled:
    #     keyboard.add(KeyboardButton(text=get_text(language, "main_menu.mahsus_ishlanma")))

    keyboard.add(KeyboardButton(text=get_text(language, "main_menu.my_account")))
    keyboard.add(KeyboardButton(text=get_text(language, "main_menu.payment")))
    keyboard.add(KeyboardButton(text=get_text(language, "main_menu.samples")))
    keyboard.add(KeyboardButton(text=get_text(language, "main_menu.help")))
    keyboard.add(KeyboardButton(text=get_text(language, "main_menu.settings")))

    keyboard.adjust(1, 2)

    return keyboard.as_markup(resize_keyboard=True)


def get_other_services_keyboard(language: str, media_enabled: bool = True, pdf_convert_enabled: bool = True, book_translate_enabled: bool = True, diploma_work_enabled: bool = True, tezis_enabled: bool = True, maqola_enabled: bool = True, bitiruv_ishi_enabled: bool = True, dissertatsiya_enabled: bool = True) -> InlineKeyboardMarkup:
    """Other services submenu inline keyboard"""
    keyboard = InlineKeyboardBuilder()

    if dissertatsiya_enabled:
        keyboard.add(InlineKeyboardButton(text=get_text(language, "main_menu.dissertatsiya"), callback_data="os:dissertatsiya"))
    if bitiruv_ishi_enabled:
        keyboard.add(InlineKeyboardButton(text=get_text(language, "main_menu.bitiruv_ishi"), callback_data="os:bitiruv_ishi"))
    if diploma_work_enabled:
        keyboard.add(InlineKeyboardButton(text=get_text(language, "main_menu.diploma_work"), callback_data="os:diploma_work"))
    if tezis_enabled:
        keyboard.add(InlineKeyboardButton(text=get_text(language, "main_menu.tezis"), callback_data="os:tezis"))
    if maqola_enabled:
        keyboard.add(InlineKeyboardButton(text=get_text(language, "main_menu.maqola"), callback_data="os:maqola"))
    keyboard.add(InlineKeyboardButton(text=get_text(language, "main_menu.emoji_art"), callback_data="os:emoji_art"))
    if pdf_convert_enabled:
        keyboard.add(InlineKeyboardButton(text=get_text(language, "main_menu.pdf_convert"), callback_data="os:pdf_convert"))
    keyboard.add(InlineKeyboardButton(text=get_text(language, "main_menu.pptx_to_pdf"), callback_data="os:pptx_to_pdf"))
    keyboard.add(InlineKeyboardButton(text=get_text(language, "main_menu.edit_file"), callback_data="os:edit_file"))
    keyboard.add(InlineKeyboardButton(text=get_text(language, "main_menu.test"), callback_data="os:test"))

    keyboard.add(InlineKeyboardButton(text=_back_text(language), callback_data="os:back"))

    keyboard.adjust(2)

    return keyboard.as_markup()


def get_test_question_count_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    """Keyboard for selecting test question count"""
    keyboard = InlineKeyboardBuilder()
    counts = [5, 10, 15, 20, 25, 30]
    for c in counts:
        keyboard.add(InlineKeyboardButton(text=str(c), callback_data=f"test_count_{c}"))
    keyboard.adjust(3)
    back_text = {"uz": "⬅️ Orqaga", "ru": "⬅️ Назад", "en": "⬅️ Back"}.get(language, "⬅️ Orqaga")
    keyboard.row(InlineKeyboardButton(text=back_text, callback_data="os:test_back"))
    return keyboard.as_markup()


def get_test_format_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    """Keyboard for selecting test output format"""
    keyboard = InlineKeyboardBuilder()
    if language == "ru":
        keyboard.add(InlineKeyboardButton(text="📄 Файл (DOCX)", callback_data="test_format_file"))
        keyboard.add(InlineKeyboardButton(text="📊 Опрос (Poll)", callback_data="test_format_poll"))
        keyboard.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="test_format_back"))
    elif language == "en":
        keyboard.add(InlineKeyboardButton(text="📄 File (DOCX)", callback_data="test_format_file"))
        keyboard.add(InlineKeyboardButton(text="📊 Poll", callback_data="test_format_poll"))
        keyboard.row(InlineKeyboardButton(text="⬅️ Back", callback_data="test_format_back"))
    else:
        keyboard.add(InlineKeyboardButton(text="📄 Fayl (DOCX)", callback_data="test_format_file"))
        keyboard.add(InlineKeyboardButton(text="📊 So'rovnoma", callback_data="test_format_poll"))
        keyboard.row(InlineKeyboardButton(text="⬅️ Orqaga", callback_data="test_format_back"))
    keyboard.adjust(2)
    return keyboard.as_markup()


def get_test_confirm_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    """Confirm/cancel keyboard for test payment"""
    keyboard = InlineKeyboardBuilder()
    if language == "ru":
        keyboard.add(InlineKeyboardButton(text="✅ Подтвердить", callback_data="test_confirm"))
        keyboard.add(InlineKeyboardButton(text="❌ Отмена", callback_data="test_cancel"))
    elif language == "en":
        keyboard.add(InlineKeyboardButton(text="✅ Confirm", callback_data="test_confirm"))
        keyboard.add(InlineKeyboardButton(text="❌ Cancel", callback_data="test_cancel"))
    else:
        keyboard.add(InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="test_confirm"))
        keyboard.add(InlineKeyboardButton(text="❌ Bekor qilish", callback_data="test_cancel"))
    keyboard.adjust(2)
    return keyboard.as_markup()


def get_dissertation_page_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    """Master's dissertation page count selection keyboard (multilingual)"""
    keyboard = InlineKeyboardBuilder()

    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="60-70 varoq (3 bob) - 90 000 so'm", callback_data="ds_pages_60_70_3"))
        keyboard.add(InlineKeyboardButton(text="70-80 varoq (3 bob) - 110 000 so'm", callback_data="ds_pages_70_80_3"))
        keyboard.add(InlineKeyboardButton(text="80-90 varoq (4 bob) - 140 000 so'm", callback_data="ds_pages_80_90_4"))
        keyboard.add(InlineKeyboardButton(text="90-100 varoq (4 bob) - 170 000 so'm", callback_data="ds_pages_90_100_4"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="60-70 стр (3 главы) - 90 000 сум", callback_data="ds_pages_60_70_3"))
        keyboard.add(InlineKeyboardButton(text="70-80 стр (3 главы) - 110 000 сум", callback_data="ds_pages_70_80_3"))
        keyboard.add(InlineKeyboardButton(text="80-90 стр (4 главы) - 140 000 сум", callback_data="ds_pages_80_90_4"))
        keyboard.add(InlineKeyboardButton(text="90-100 стр (4 главы) - 170 000 сум", callback_data="ds_pages_90_100_4"))
    else:
        keyboard.add(InlineKeyboardButton(text="60-70 pages (3 chapters) - 90 000 som", callback_data="ds_pages_60_70_3"))
        keyboard.add(InlineKeyboardButton(text="70-80 pages (3 chapters) - 110 000 som", callback_data="ds_pages_70_80_3"))
        keyboard.add(InlineKeyboardButton(text="80-90 pages (4 chapters) - 140 000 som", callback_data="ds_pages_80_90_4"))
        keyboard.add(InlineKeyboardButton(text="90-100 pages (4 chapters) - 170 000 som", callback_data="ds_pages_90_100_4"))

    keyboard.add(InlineKeyboardButton(text=_back_text(language), callback_data="back_to_author_name"))
    keyboard.adjust(1)
    return keyboard.as_markup()


def get_gw_outline_choice_keyboard(lang: str = "uz") -> InlineKeyboardMarkup:
    """Auto vs manual outline choice keyboard for BMI (bitiruv malakaviy ishi)"""
    keyboard = InlineKeyboardBuilder()
    labels = {
        "uz": ("🤖 Avtomatik (AI tuzsin)", "✏️ Qo'lda kirish"),
        "ru": ("🤖 Автоматически (AI составит)", "✏️ Ввести вручную"),
        "en": ("🤖 Automatic (AI will create)", "✏️ Enter manually"),
    }
    auto_lbl, manual_lbl = labels.get(lang, labels["uz"])
    keyboard.add(InlineKeyboardButton(text=auto_lbl, callback_data="gw_outline_auto"))
    keyboard.add(InlineKeyboardButton(text=manual_lbl, callback_data="gw_outline_manual"))
    keyboard.adjust(1)
    return keyboard.as_markup()


def get_graduation_work_page_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    """Graduation qualifying work page count selection keyboard (multilingual)"""
    keyboard = InlineKeyboardBuilder()

    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="30-40 varoq (3 bob) - 35 000 so'm", callback_data="gw_pages_30_40_3"))
        keyboard.add(InlineKeyboardButton(text="40-50 varoq (3 bob) - 50 000 so'm", callback_data="gw_pages_40_50_3"))
        keyboard.add(InlineKeyboardButton(text="50-60 varoq (3 bob) - 65 000 so'm", callback_data="gw_pages_50_60_3"))
        keyboard.add(InlineKeyboardButton(text="60-70 varoq (3 bob) - 80 000 so'm", callback_data="gw_pages_60_70_3"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="30-40 стр (3 главы) - 35 000 сум", callback_data="gw_pages_30_40_3"))
        keyboard.add(InlineKeyboardButton(text="40-50 стр (3 главы) - 50 000 сум", callback_data="gw_pages_40_50_3"))
        keyboard.add(InlineKeyboardButton(text="50-60 стр (3 главы) - 65 000 сум", callback_data="gw_pages_50_60_3"))
        keyboard.add(InlineKeyboardButton(text="60-70 стр (3 главы) - 80 000 сум", callback_data="gw_pages_60_70_3"))
    else:
        keyboard.add(InlineKeyboardButton(text="30-40 pages (3 chapters) - 35 000 som", callback_data="gw_pages_30_40_3"))
        keyboard.add(InlineKeyboardButton(text="40-50 pages (3 chapters) - 50 000 som", callback_data="gw_pages_40_50_3"))
        keyboard.add(InlineKeyboardButton(text="50-60 pages (3 chapters) - 65 000 som", callback_data="gw_pages_50_60_3"))
        keyboard.add(InlineKeyboardButton(text="60-70 pages (3 chapters) - 80 000 som", callback_data="gw_pages_60_70_3"))

    keyboard.add(InlineKeyboardButton(text=_back_text(language), callback_data="back_to_author_name"))
    keyboard.adjust(1)
    return keyboard.as_markup()



def get_post_translation_keyboard(language: str) -> InlineKeyboardMarkup:
    """Post-translation upsell keyboard for related book services"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(
        text=get_text(language, "book_translate_post_presentation"),
        callback_data="bt_post_presentation"
    ))
    keyboard.add(InlineKeyboardButton(
        text=get_text(language, "book_translate_post_referat"),
        callback_data="bt_post_referat"
    ))
    keyboard.add(InlineKeyboardButton(
        text=get_text(language, "book_translate_post_course_work"),
        callback_data="bt_post_course_work"
    ))
    keyboard.add(InlineKeyboardButton(
        text=get_text(language, "book_translate_post_article"),
        callback_data="bt_post_article"
    ))
    keyboard.add(InlineKeyboardButton(
        text=get_text(language, "book_translate_post_no_thanks"),
        callback_data="bt_post_no_thanks"
    ))
    keyboard.adjust(2, 2, 1)
    return keyboard.as_markup()


def get_book_translate_payment_keyboard(language: str, price_som: int, user_balance: int, back_callback: str = "bt_back_from_payment") -> InlineKeyboardMarkup:
    """Payment keyboard for book translation — balance or top-up, no invoice Stars path."""
    keyboard = InlineKeyboardBuilder()
    has_enough = user_balance >= price_som
    if language == "ru":
        if has_enough:
            balance_text = f"💰 С баланса · {user_balance:,} сум ✅"
        else:
            balance_text = f"💰 Баланс: {user_balance:,} сум ❌ недостаточно"
        topup_text = "💳 Пополнить баланс"
    elif language == "en":
        if has_enough:
            balance_text = f"💰 From balance · {user_balance:,} som ✅"
        else:
            balance_text = f"💰 Balance: {user_balance:,} som ❌ insufficient"
        topup_text = "💳 Top Up Balance"
    else:
        if has_enough:
            balance_text = f"💰 Balansingizdan · {user_balance:,} so'm ✅"
        else:
            balance_text = f"💰 Balansingiz: {user_balance:,} so'm ❌ yetarli emas"
        topup_text = "💳 Hisobni to'ldirish"
    keyboard.add(InlineKeyboardButton(text=balance_text, callback_data="pay_balance_book_translate"))
    if not has_enough:
        keyboard.add(InlineKeyboardButton(text=topup_text, callback_data="pay_card_start"))
    keyboard.add(InlineKeyboardButton(text=_back_text(language), callback_data=back_callback))
    keyboard.adjust(1)
    return keyboard.as_markup()


def get_book_translate_lang_keyboard(language: str) -> InlineKeyboardMarkup:
    """Target language selection keyboard for book translation"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(
        text=get_text(language, "book_translate_lang_uz"),
        callback_data="bt_lang_uz"
    ))
    keyboard.add(InlineKeyboardButton(
        text=get_text(language, "book_translate_lang_ru"),
        callback_data="bt_lang_ru"
    ))
    keyboard.add(InlineKeyboardButton(
        text=get_text(language, "book_translate_lang_en"),
        callback_data="bt_lang_en"
    ))
    keyboard.add(InlineKeyboardButton(text=_back_text(language), callback_data="bt_back_to_menu"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_slide_count_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    """Slide count selection keyboard with prices (multilingual)"""
    keyboard = InlineKeyboardBuilder()

    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="10 slayd - 5000 so'm", callback_data="slides_10"))
        keyboard.add(InlineKeyboardButton(text="15 slayd - 7000 so'm", callback_data="slides_15"))
        keyboard.add(InlineKeyboardButton(text="20 slayd - 10000 so'm", callback_data="slides_20"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="10 слайдов - 5000 сум", callback_data="slides_10"))
        keyboard.add(InlineKeyboardButton(text="15 слайдов - 7000 сум", callback_data="slides_15"))
        keyboard.add(InlineKeyboardButton(text="20 слайдов - 10000 сум", callback_data="slides_20"))
    else:
        keyboard.add(InlineKeyboardButton(text="10 slides - 5000 som", callback_data="slides_10"))
        keyboard.add(InlineKeyboardButton(text="15 slides - 7000 som", callback_data="slides_15"))
        keyboard.add(InlineKeyboardButton(text="20 slides - 10000 som", callback_data="slides_20"))

    keyboard.add(InlineKeyboardButton(text=_back_text(language), callback_data="back_to_author_name"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_all_templates_keyboard(lang: str = "uz") -> InlineKeyboardMarkup:
    """Create compact keyboard with all 20 template numbers (4 columns, 5 rows) + back button"""
    keyboard = InlineKeyboardBuilder()

    for i in range(1, 21):
        keyboard.add(InlineKeyboardButton(text=str(i), callback_data=f"template_{i}"))
    keyboard.adjust(4)

    keyboard.row(InlineKeyboardButton(text=_back_text(lang), callback_data="back_from_template"))
    return keyboard.as_markup()

def get_template_keyboard(group: int, total_groups: int, lang: str = "uz") -> InlineKeyboardMarkup:
    """Legacy template keyboard - now uses single overview approach"""
    return get_all_templates_keyboard(lang)

def get_page_count_keyboard(document_type: str, language: str = "uz") -> InlineKeyboardMarkup:
    """Page count selection keyboard with prices (multilingual)"""
    keyboard = InlineKeyboardBuilder()

    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="10-15 varoq - 5000 so'm", callback_data="pages_10_15"))
        keyboard.add(InlineKeyboardButton(text="15-20 varoq - 7000 so'm", callback_data="pages_15_20"))
        keyboard.add(InlineKeyboardButton(text="20-25 varoq - 10000 so'm", callback_data="pages_20_25"))
        keyboard.add(InlineKeyboardButton(text="25-30 varoq - 12000 so'm", callback_data="pages_25_30"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="10-15 страниц - 5000 сум", callback_data="pages_10_15"))
        keyboard.add(InlineKeyboardButton(text="15-20 страниц - 7000 сум", callback_data="pages_15_20"))
        keyboard.add(InlineKeyboardButton(text="20-25 страниц - 10000 сум", callback_data="pages_20_25"))
        keyboard.add(InlineKeyboardButton(text="25-30 страниц - 12000 сум", callback_data="pages_25_30"))
    else:
        keyboard.add(InlineKeyboardButton(text="10-15 pages - 5000 som", callback_data="pages_10_15"))
        keyboard.add(InlineKeyboardButton(text="15-20 pages - 7000 som", callback_data="pages_15_20"))
        keyboard.add(InlineKeyboardButton(text="20-25 pages - 10000 som", callback_data="pages_20_25"))
        keyboard.add(InlineKeyboardButton(text="25-30 pages - 12000 som", callback_data="pages_25_30"))

    keyboard.add(InlineKeyboardButton(text=_back_text(language), callback_data="back_to_author_name"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_course_work_page_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    """Course work page count selection keyboard with chapters (multilingual)"""
    keyboard = InlineKeyboardBuilder()

    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="15-20 varoq (3 bo'lim) - 10000 so'm", callback_data="cw_pages_15_20_3"))
        keyboard.add(InlineKeyboardButton(text="20-25 varoq (3 bo'lim) - 15000 so'm", callback_data="cw_pages_20_25_3"))
        keyboard.add(InlineKeyboardButton(text="25-30 varoq (3 bo'lim) - 20000 so'm", callback_data="cw_pages_25_30_3"))
        keyboard.add(InlineKeyboardButton(text="30-35 varoq (3 bo'lim) - 25000 so'm", callback_data="cw_pages_30_35_3"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="15-20 стр (3 главы) - 10000 сум", callback_data="cw_pages_15_20_3"))
        keyboard.add(InlineKeyboardButton(text="20-25 стр (3 главы) - 15000 сум", callback_data="cw_pages_20_25_3"))
        keyboard.add(InlineKeyboardButton(text="25-30 стр (3 главы) - 20000 сум", callback_data="cw_pages_25_30_3"))
        keyboard.add(InlineKeyboardButton(text="30-35 стр (3 главы) - 25000 сум", callback_data="cw_pages_30_35_3"))
    else:
        keyboard.add(InlineKeyboardButton(text="15-20 pages (3 chapters) - 10000 som", callback_data="cw_pages_15_20_3"))
        keyboard.add(InlineKeyboardButton(text="20-25 pages (3 chapters) - 15000 som", callback_data="cw_pages_20_25_3"))
        keyboard.add(InlineKeyboardButton(text="25-30 pages (3 chapters) - 20000 som", callback_data="cw_pages_25_30_3"))
        keyboard.add(InlineKeyboardButton(text="30-35 pages (3 chapters) - 25000 som", callback_data="cw_pages_30_35_3"))

    keyboard.add(InlineKeyboardButton(text=_back_text(language), callback_data="back_to_author_name"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_diploma_work_page_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    """Diploma work page count selection keyboard with chapters (multilingual)"""
    keyboard = InlineKeyboardBuilder()

    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="15-20 varoq (2 bo'lim) - 10000 so'm", callback_data="dw_pages_15_20_2"))
        keyboard.add(InlineKeyboardButton(text="20-25 varoq (2 bo'lim) - 15000 so'm", callback_data="dw_pages_20_25_2"))
        keyboard.add(InlineKeyboardButton(text="25-30 varoq (3 bo'lim) - 20000 so'm", callback_data="dw_pages_25_30_3"))
        keyboard.add(InlineKeyboardButton(text="30-35 varoq (3 bo'lim) - 25000 so'm", callback_data="dw_pages_30_35_3"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="15-20 стр (2 главы) - 10000 сум", callback_data="dw_pages_15_20_2"))
        keyboard.add(InlineKeyboardButton(text="20-25 стр (2 главы) - 15000 сум", callback_data="dw_pages_20_25_2"))
        keyboard.add(InlineKeyboardButton(text="25-30 стр (3 главы) - 20000 сум", callback_data="dw_pages_25_30_3"))
        keyboard.add(InlineKeyboardButton(text="30-35 стр (3 главы) - 25000 сум", callback_data="dw_pages_30_35_3"))
    else:
        keyboard.add(InlineKeyboardButton(text="15-20 pages (2 chapters) - 10000 som", callback_data="dw_pages_15_20_2"))
        keyboard.add(InlineKeyboardButton(text="20-25 pages (2 chapters) - 15000 som", callback_data="dw_pages_20_25_2"))
        keyboard.add(InlineKeyboardButton(text="25-30 pages (3 chapters) - 20000 som", callback_data="dw_pages_25_30_3"))
        keyboard.add(InlineKeyboardButton(text="30-35 pages (3 chapters) - 25000 som", callback_data="dw_pages_30_35_3"))

    keyboard.add(InlineKeyboardButton(text=_back_text(language), callback_data="back_to_author_name"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_payment_amount_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    """Payment amount selection keyboard with explanations (multilingual)"""
    keyboard = InlineKeyboardBuilder()

    if language == "uz":
        payment_options = [
            (10000, "10,000 so'm"),
            (15000, "15,000 so'm"),
            (20000, "20,000 so'm"),
            (25000, "25,000 so'm"),
            (30000, "30,000 so'm"),
            (50000, "50,000 so'm"),
        ]
    elif language == "ru":
        payment_options = [
            (10000, "10,000 сум"),
            (15000, "15,000 сум"),
            (20000, "20,000 сум"),
            (25000, "25,000 сум"),
            (30000, "30,000 сум"),
            (50000, "50,000 сум"),
        ]
    else:  # en
        payment_options = [
            (10000, "10,000 som"),
            (15000, "15,000 som"),
            (20000, "20,000 som"),
            (25000, "25,000 som"),
            (30000, "30,000 som"),
            (50000, "50,000 som"),
        ]

    for amount, description in payment_options:
        keyboard.add(InlineKeyboardButton(
            text=description, 
            callback_data=f"pay_{amount}"
        ))

    # Custom amount button
    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="✏️ Boshqa summa", callback_data="pay_custom"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="✏️ Другая сумма", callback_data="pay_custom"))
    else:
        keyboard.add(InlineKeyboardButton(text="✏️ Other amount", callback_data="pay_custom"))

    # Add referral button
    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="💰 Pul ishlab topish", callback_data="show_referral"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="👥 Реферальная программа", callback_data="show_referral"))
    else:  # en
        keyboard.add(InlineKeyboardButton(text="👥 Referral Program", callback_data="show_referral"))

    keyboard.adjust(1)
    return keyboard.as_markup()

def get_subscription_check_keyboard(language: str, channels=None) -> InlineKeyboardMarkup:
    """Subscription check keyboard with channel links"""
    keyboard = InlineKeyboardBuilder()

    # Add buttons for each channel
    if channels:
        for channel in channels:
            # Create channel button text
            if language == "uz":
                button_text = f"📢 {channel.title}"
            elif language == "ru":
                button_text = f"📢 {channel.title}"
            else:  # en
                button_text = f"📢 {channel.title}"

            # Create channel link
            if channel.channel_username:
                channel_url = f"https://t.me/{channel.channel_username}"
            else:
                # If no username, try to create a link from channel_id (won't work for private channels)
                channel_url = f"https://t.me/c/{str(channel.channel_id)[4:]}"

            keyboard.add(InlineKeyboardButton(
                text=button_text,
                url=channel_url
            ))

    # Add check subscription button
    keyboard.add(InlineKeyboardButton(
        text=get_text(language, "check_subscription"), 
        callback_data="check_subscription"
    ))

    keyboard.adjust(1)  # One button per row
    return keyboard.as_markup()

def get_admin_keyboard() -> ReplyKeyboardMarkup:
    """Admin panel keyboard - with channel management"""
    keyboard = ReplyKeyboardBuilder()

    # Statistika va reklama
    keyboard.add(KeyboardButton(text="📊 Statistika"))
    keyboard.add(KeyboardButton(text="📤 Reklama yuborish"))

    # Kunlik statistika va to'lovlar
    keyboard.add(KeyboardButton(text="📈 Kunlik statistika"))
    keyboard.add(KeyboardButton(text="💳 To'lovlar"))

    # Kanallar va promokod boshqaruvi
    keyboard.add(KeyboardButton(text="📢 Kanallar"))
    keyboard.add(KeyboardButton(text="🎟 Promokod boshqaruvi"))

    # Feature management and sample management
    keyboard.add(KeyboardButton(text="🎛 Funksiyalar boshqaruvi"))
    keyboard.add(KeyboardButton(text="📁 Namunalar boshqaruvi"))

    # Block user management
    keyboard.add(KeyboardButton(text="🚫 Foydalanuvchilarni bloklash"))
    
    # AI model selection
    keyboard.add(KeyboardButton(text="🤖 AI modelni almashtirish"))

    # Client management
    keyboard.add(KeyboardButton(text="👥 Mijoz bilan ishlash"))
    keyboard.add(KeyboardButton(text="➕ Yangi mijoz qo'shish"))

    # Orqaga qaytish
    keyboard.add(KeyboardButton(text="👤 Foydalanuvchi rejimi"))

    keyboard.adjust(2)
    return keyboard.as_markup(resize_keyboard=True)

def get_client_action_keyboard(telegram_id: int, show_dismiss: bool = False) -> InlineKeyboardMarkup:
    """Admin client management action keyboard"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="📨 Xabar yuborish", callback_data=f"client_msg_{telegram_id}"))
    keyboard.add(InlineKeyboardButton(text="➕ Balans qo'shish", callback_data=f"client_add_{telegram_id}"))
    keyboard.add(InlineKeyboardButton(text="➖ Balansdan yechish", callback_data=f"client_deduct_{telegram_id}"))
    keyboard.add(InlineKeyboardButton(text="🔍 Boshqa mijoz", callback_data="client_search_again"))
    if show_dismiss:
        keyboard.add(InlineKeyboardButton(text="✅ Kerak emas, yopish", callback_data="client_dismiss"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_payment_review_keyboard(payment_id: int) -> InlineKeyboardMarkup:
    """Payment review keyboard for admin"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(
        text="✅ Tasdiqlash", 
        callback_data=f"approve_payment_{payment_id}"
    ))
    keyboard.add(InlineKeyboardButton(
        text="❌ Rad etish", 
        callback_data=f"reject_payment_{payment_id}"
    ))
    keyboard.add(InlineKeyboardButton(
        text="💰 Summani o'zgartirish",
        callback_data=f"adjust_amount_{payment_id}"
    ))
    keyboard.adjust(2, 1)
    return keyboard.as_markup()

def get_amount_adjustment_keyboard(payment_id: int, current_amount: int) -> InlineKeyboardMarkup:
    """Amount adjustment keyboard for admin"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(
        text="➖ -1000", 
        callback_data=f"decrease_amount_{payment_id}"
    ))
    keyboard.add(InlineKeyboardButton(
        text=f"💵 {current_amount:,} so'm", 
        callback_data=f"amount_display_{payment_id}"
    ))
    keyboard.add(InlineKeyboardButton(
        text="➕ +1000", 
        callback_data=f"increase_amount_{payment_id}"
    ))
    keyboard.add(InlineKeyboardButton(
        text="✅ Tasdiqlash (yangi summa bilan)", 
        callback_data=f"confirm_adjusted_{payment_id}"
    ))
    keyboard.add(InlineKeyboardButton(
        text="🔙 Bekor qilish", 
        callback_data=f"cancel_adjustment_{payment_id}"
    ))
    keyboard.adjust(3, 1, 1)
    return keyboard.as_markup()

def get_channel_management_keyboard() -> InlineKeyboardMarkup:
    """Channel management keyboard"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_channel"))
    keyboard.add(InlineKeyboardButton(text="🗑 Kanal o'chirish", callback_data="remove_channel"))
    keyboard.add(InlineKeyboardButton(text="📋 Kanallar ro'yxati", callback_data="list_channels"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_channels_list_keyboard(channels: List) -> InlineKeyboardMarkup:
    """Channels list keyboard for removal"""
    keyboard = InlineKeyboardBuilder()

    for channel in channels:
        keyboard.add(InlineKeyboardButton(
            text=f"🗑 {channel.title}",
            callback_data=f"delete_channel_{channel.channel_id}"
        ))

    keyboard.adjust(1)
    return keyboard.as_markup()

def get_promocode_keyboard() -> InlineKeyboardMarkup:
    """Promocode management keyboard"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="📤 Promokod yaratish", callback_data="create_promocode"))
    keyboard.add(InlineKeyboardButton(text="📋 Barcha promokodlar", callback_data="list_promocodes"))
    keyboard.add(InlineKeyboardButton(text="📊 Statistika", callback_data="promocode_stats"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_broadcast_target_keyboard() -> InlineKeyboardMarkup:
    """Broadcast target selection keyboard"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="👥 Hamma", callback_data="broadcast_all"))
    keyboard.add(InlineKeyboardButton(text="🟢 Faqat faollar", callback_data="broadcast_active"))
    keyboard.adjust(2)
    return keyboard.as_markup()

def get_promocode_option_keyboard(language: str) -> InlineKeyboardMarkup:
    """Promocode option keyboard"""
    keyboard = InlineKeyboardBuilder()

    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="🎟 Ha, promokod kiritaman", callback_data="use_promocode"))
        keyboard.add(InlineKeyboardButton(text="❌ Yo'q, davom etaman", callback_data="skip_promocode"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="🎟 Да, введу промокод", callback_data="use_promocode"))
        keyboard.add(InlineKeyboardButton(text="❌ Нет, продолжить", callback_data="skip_promocode"))
    else:  # en
        keyboard.add(InlineKeyboardButton(text="🎟 Yes, enter promocode", callback_data="use_promocode"))
        keyboard.add(InlineKeyboardButton(text="❌ No, continue", callback_data="skip_promocode"))

    keyboard.adjust(1)
    return keyboard.as_markup()

def get_promocode_error_keyboard(language: str) -> InlineKeyboardMarkup:
    """Promocode error keyboard with retry and back options"""
    keyboard = InlineKeyboardBuilder()

    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="🔄 Qayta kiritish", callback_data="retry_promocode"))
        keyboard.add(InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_main"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="🔄 Повторить", callback_data="retry_promocode"))
        keyboard.add(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    else:  # en
        keyboard.add(InlineKeyboardButton(text="🔄 Try again", callback_data="retry_promocode"))
        keyboard.add(InlineKeyboardButton(text="🔙 Back", callback_data="back_to_main"))

    keyboard.adjust(2)
    return keyboard.as_markup()

def get_back_to_channels_keyboard() -> InlineKeyboardMarkup:
    """Back to channels keyboard"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_channels"))
    return keyboard.as_markup()

def get_outline_choice_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    """Outline choice keyboard - manual or automatic"""
    keyboard = InlineKeyboardBuilder()

    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="✍️ Rejani qo'lda kiritish", callback_data="outline_manual"))
        keyboard.add(InlineKeyboardButton(text="🤖 Reja avtomatik yaratilsin", callback_data="outline_auto"))
        keyboard.add(InlineKeyboardButton(text=_back_text(language), callback_data="back_from_outline"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="✍️ Ввести план вручную", callback_data="outline_manual"))
        keyboard.add(InlineKeyboardButton(text="🤖 Создать план автоматически", callback_data="outline_auto"))
        keyboard.add(InlineKeyboardButton(text=_back_text(language), callback_data="back_from_outline"))
    else:
        keyboard.add(InlineKeyboardButton(text="✍️ Enter outline manually", callback_data="outline_manual"))
        keyboard.add(InlineKeyboardButton(text="🤖 Create outline automatically", callback_data="outline_auto"))
        keyboard.add(InlineKeyboardButton(text=_back_text(language), callback_data="back_from_outline"))

    keyboard.adjust(1)
    return keyboard.as_markup()

def get_manual_input_keyboard(language: str = "uz") -> ReplyKeyboardMarkup:
    """Keyboard with back button for manual outline input"""
    keyboard = ReplyKeyboardBuilder()

    if language == "uz":
        keyboard.add(KeyboardButton(text="🔙 Ortga qaytish"))
    elif language == "ru":
        keyboard.add(KeyboardButton(text="🔙 Назад"))
    else:  # en
        keyboard.add(KeyboardButton(text="🔙 Back"))

    keyboard.adjust(1)
    return keyboard.as_markup(resize_keyboard=True)

def get_outline_review_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    """Keyboard for outline review - confirm or edit"""
    keyboard = InlineKeyboardBuilder()

    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="confirm_outline"))
        keyboard.add(InlineKeyboardButton(text="✏️ Tahrirlash", callback_data="edit_outline"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_outline"))
        keyboard.add(InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_outline"))
    else:  # en
        keyboard.add(InlineKeyboardButton(text="✅ Confirm", callback_data="confirm_outline"))
        keyboard.add(InlineKeyboardButton(text="✏️ Edit", callback_data="edit_outline"))

    keyboard.adjust(1)
    return keyboard.as_markup()

def get_references_choice_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    """Keyboard for choosing whether to add references to presentation"""
    keyboard = InlineKeyboardBuilder()

    if language == "uz":
        keyboard.add(InlineKeyboardButton(text="✅ Ha", callback_data="add_references_yes"))
        keyboard.add(InlineKeyboardButton(text="❌ Yo'q", callback_data="add_references_no"))
    elif language == "ru":
        keyboard.add(InlineKeyboardButton(text="✅ Да", callback_data="add_references_yes"))
        keyboard.add(InlineKeyboardButton(text="❌ Нет", callback_data="add_references_no"))
    else:  # en
        keyboard.add(InlineKeyboardButton(text="✅ Yes", callback_data="add_references_yes"))
        keyboard.add(InlineKeyboardButton(text="❌ No", callback_data="add_references_no"))

    keyboard.adjust(2)
    return keyboard.as_markup()

def get_channel_error_keyboard() -> InlineKeyboardMarkup:
    """Channel error keyboard with retry and back options"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🔄 Qayta kiritish", callback_data="retry_channel_id"))
    keyboard.add(InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_channels"))
    keyboard.adjust(2)
    return keyboard.as_markup()

def get_back_to_features_keyboard() -> InlineKeyboardMarkup:
    """Back to feature management keyboard"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_features"))
    return keyboard.as_markup()

def get_feature_management_keyboard(
    startup_bonus_enabled: bool,
    mahsus_ishlanma_enabled: bool = True,
) -> InlineKeyboardMarkup:
    """Feature management keyboard for admin"""
    keyboard = InlineKeyboardBuilder()

    # Startup bonus toggle (5000 for new users)
    bonus_status = "🟢 Yoqilgan" if startup_bonus_enabled else "🔴 O'chirilgan"
    bonus_action = "off" if startup_bonus_enabled else "on"
    keyboard.add(InlineKeyboardButton(
        text=f"🎁 Start bonus (5000): {bonus_status}",
        callback_data=f"toggle_startup_bonus_{bonus_action}"
    ))

    # Mahsus ishlanma toggle
    mi_status = "🟢 Yoqilgan" if mahsus_ishlanma_enabled else "🔴 O'chirilgan"
    mi_action = "off" if mahsus_ishlanma_enabled else "on"
    keyboard.add(InlineKeyboardButton(
        text=f"🔬 Mahsus ishlanma: {mi_status}",
        callback_data=f"toggle_mahsus_ishlanma_{mi_action}"
    ))

    # Mass gift button
    keyboard.add(InlineKeyboardButton(
        text="🎁 Barchaga sovg'a yuborish",
        callback_data="mass_gift_start"
    ))

    # Mass take back button
    keyboard.add(InlineKeyboardButton(
        text="💸 Barchadan pulni qaytib olish",
        callback_data="mass_take_back_start"
    ))

    keyboard.adjust(1)
    return keyboard.as_markup()

def get_help_keyboard(language: str = "uz") -> InlineKeyboardMarkup:
    """Help section keyboard with view samples button"""
    keyboard = InlineKeyboardBuilder()
    
    # View samples button with proper translation
    samples_text = get_text(language, "view_samples")
    keyboard.add(InlineKeyboardButton(
        text=samples_text,
        callback_data="view_samples"
    ))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_sample_management_keyboard() -> InlineKeyboardMarkup:
    """Sample files management keyboard for admin"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="➕ Namuna qo'shish", callback_data="add_sample"))
    keyboard.add(InlineKeyboardButton(text="🗑 Namuna o'chirish", callback_data="delete_sample"))
    keyboard.add(InlineKeyboardButton(text="📋 Barcha namunalar", callback_data="list_samples"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_samples_list_keyboard(samples: list) -> InlineKeyboardMarkup:
    """Samples list keyboard for deletion"""
    keyboard = InlineKeyboardBuilder()

    for sample in samples:
        keyboard.add(InlineKeyboardButton(
            text=f"🗑 {sample['title']}",
            callback_data=f"delete_sample_{sample['id']}"
        ))

    keyboard.add(InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_sample_menu"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_block_user_keyboard() -> InlineKeyboardMarkup:
    """Block user management keyboard"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🚫 Foydalanuvchini bloklash", callback_data="block_user"))
    keyboard.add(InlineKeyboardButton(text="✅ Blokdan chiqarish", callback_data="unblock_user"))
    keyboard.add(InlineKeyboardButton(text="📋 Bloklangan foydalanuvchilar", callback_data="list_blocked"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_blocked_users_keyboard(blocked_users: list) -> InlineKeyboardMarkup:
    """Keyboard showing blocked users for unblocking"""
    keyboard = InlineKeyboardBuilder()
    
    for user in blocked_users:
        username_display = f"@{user['username']}" if user['username'] else f"ID: {user['telegram_id']}"
        keyboard.add(InlineKeyboardButton(
            text=f"✅ {username_display}",
            callback_data=f"unblock_{user['telegram_id']}"
        ))
    
    keyboard.add(InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_block_menu"))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_payment_choice_keyboard(language: str, price_som: int, price_stars: int, user_balance: int = 0, balance_callback: str = "pay_balance_doc", back_callback: Optional[str] = None) -> InlineKeyboardMarkup:
    """Payment choice: pay from balance or via Telegram Stars"""
    keyboard = InlineKeyboardBuilder()
    has_enough = user_balance >= price_som
    if language == "uz":
        if has_enough:
            balance_text = f"💰 Balansingizdan · {user_balance:,} so'm ✅"
        else:
            balance_text = f"💰 Balansingiz: {user_balance:,} so'm ❌ yetarli emas"
        stars_text = f"⭐ {price_stars} Stars to'lash"
        topup_text = "💳 Hisobni to'ldirish"
    elif language == "ru":
        if has_enough:
            balance_text = f"💰 С баланса · {user_balance:,} сум ✅"
        else:
            balance_text = f"💰 Баланс: {user_balance:,} сум ❌ недостаточно"
        stars_text = f"⭐ Оплатить {price_stars} Stars"
        topup_text = "💳 Пополнить баланс"
    else:
        if has_enough:
            balance_text = f"💰 From balance · {user_balance:,} som ✅"
        else:
            balance_text = f"💰 Balance: {user_balance:,} som ❌ insufficient"
        stars_text = f"⭐ Pay {price_stars} Stars"
        topup_text = "💳 Top Up Balance"
    keyboard.add(InlineKeyboardButton(text=balance_text, callback_data=balance_callback))
    keyboard.add(InlineKeyboardButton(text=stars_text, callback_data=f"pay_stars_{price_stars}_{price_som}"))
    if not has_enough:
        keyboard.add(InlineKeyboardButton(text=topup_text, callback_data="pay_card_start"))
    if back_callback:
        keyboard.add(InlineKeyboardButton(text=_back_text(language), callback_data=back_callback))
    keyboard.adjust(1)
    return keyboard.as_markup()

def get_insufficient_balance_keyboard(language: str) -> InlineKeyboardMarkup:
    """Single top-up button shown when balance is insufficient"""
    keyboard = InlineKeyboardBuilder()
    if language == "uz":
        text = "💳 Hisobni to'ldirish"
    elif language == "ru":
        text = "💳 Пополнить баланс"
    else:
        text = "💳 Top Up Balance"
    keyboard.add(InlineKeyboardButton(text=text, callback_data="pay_card_start"))
    keyboard.adjust(1)
    return keyboard.as_markup()


def get_image_model_keyboard(language: str) -> InlineKeyboardMarkup:
    """Image generation model selection (3 choices)"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🍌 Nano Banana", callback_data="imgmodel_nano"))
    keyboard.add(InlineKeyboardButton(text="🎨 DALL-E 3", callback_data="imgmodel_dalle"))
    keyboard.add(InlineKeyboardButton(text="⚡ Grok Aurora", callback_data="imgmodel_grok"))
    keyboard.adjust(1)
    keyboard.row(InlineKeyboardButton(text=_back_text(language), callback_data="back_imgmodel"))
    return keyboard.as_markup()

def get_edit_model_keyboard(language: str) -> InlineKeyboardMarkup:
    """Image editing model selection (3 choices)"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="🍌 Nano Banana Pro", callback_data="editmodel_nano"))
    keyboard.add(InlineKeyboardButton(text="🎨 DALL-E 2", callback_data="editmodel_dalle"))
    keyboard.add(InlineKeyboardButton(text="⚡ FLUX Dev", callback_data="editmodel_grok"))
    keyboard.adjust(1)
    keyboard.row(InlineKeyboardButton(text=_back_text(language), callback_data="back_editmodel"))
    return keyboard.as_markup()

def get_video_model_keyboard(language: str) -> InlineKeyboardMarkup:
    """Video model selection with flat prices (max duration)."""
    from config import VIDEO_MODEL_PRICES
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(
        text=f"🌊 Veo 3.1 (ovozli, ~5-8s) — {VIDEO_MODEL_PRICES['veo']:,} so'm",
        callback_data="vidmodel_veo"
    ))
    keyboard.add(InlineKeyboardButton(
        text=f"🎬 Kling v3 Pro (ovozli, 10s) — {VIDEO_MODEL_PRICES['kling']:,} so'm",
        callback_data="vidmodel_kling"
    ))
    keyboard.adjust(1)
    keyboard.row(InlineKeyboardButton(text=_back_text(language), callback_data="back_vidmodel"))
    return keyboard.as_markup()

def get_img2video_model_keyboard(language: str) -> InlineKeyboardMarkup:
    """Image-to-video model selection with prices shown."""
    from config import IMG2VIDEO_PRICE
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(
        text=f"🌊 Veo 3.1 (ovozli) — {IMG2VIDEO_PRICE:,} so'm",
        callback_data="i2vmodel_veo"
    ))
    keyboard.add(InlineKeyboardButton(
        text=f"🎬 Kling v3 Pro (ovozli) — {IMG2VIDEO_PRICE:,} so'm",
        callback_data="i2vmodel_kling"
    ))
    keyboard.adjust(1)
    keyboard.row(InlineKeyboardButton(text=_back_text(language), callback_data="back_i2vmodel"))
    return keyboard.as_markup()

def get_image_size_keyboard(language: str) -> InlineKeyboardMarkup:
    """Legacy image size keyboard (kept for compat)"""
    return get_image_aspect_keyboard(language)

def get_image_aspect_keyboard(language: str) -> InlineKeyboardMarkup:
    """Image aspect ratio keyboard (single step)"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="1:1", callback_data="imgaspect_1_1"))
    keyboard.add(InlineKeyboardButton(text="16:9", callback_data="imgaspect_16_9"))
    keyboard.add(InlineKeyboardButton(text="9:16", callback_data="imgaspect_9_16"))
    keyboard.adjust(3)
    keyboard.row(InlineKeyboardButton(text=_back_text(language), callback_data="back_imgaspect"))
    return keyboard.as_markup()

def get_video_duration_keyboard(language: str) -> InlineKeyboardMarkup:
    """Video duration selection keyboard"""
    if language == "uz":
        labels = ["5 sekund", "10 sekund"]
    elif language == "ru":
        labels = ["5 секунд", "10 секунд"]
    else:
        labels = ["5 seconds", "10 seconds"]
    keyboard = InlineKeyboardBuilder()
    for label, val in zip(labels, ["5", "10"]):
        keyboard.add(InlineKeyboardButton(text=label, callback_data=f"viddur_{val}"))
    keyboard.adjust(2)
    keyboard.row(InlineKeyboardButton(text=_back_text(language), callback_data="back_viddur"))
    return keyboard.as_markup()

def get_video_aspect_keyboard(language: str) -> InlineKeyboardMarkup:
    """Video aspect ratio keyboard"""
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="16:9", callback_data="vidaspect_16_9"))
    keyboard.add(InlineKeyboardButton(text="9:16", callback_data="vidaspect_9_16"))
    keyboard.add(InlineKeyboardButton(text="1:1", callback_data="vidaspect_1_1"))
    keyboard.adjust(3)
    keyboard.row(InlineKeyboardButton(text=_back_text(language), callback_data="back_vidaspect"))
    return keyboard.as_markup()

def get_media_back_keyboard(language: str) -> ReplyKeyboardMarkup:
    """Single back button keyboard"""
    keyboard = ReplyKeyboardBuilder()
    keyboard.add(KeyboardButton(text=get_text(language, "media_menu.back")))
    keyboard.adjust(1)
    return keyboard.as_markup(resize_keyboard=True)

def get_veo_image_keyboard(language: str) -> ReplyKeyboardMarkup:
    """Skip + back keyboard for optional Veo image step."""
    skip_labels = {"uz": "⏭ O'tkazib yuborish", "ru": "⏭ Пропустить", "en": "⏭ Skip"}
    keyboard = ReplyKeyboardBuilder()
    keyboard.add(KeyboardButton(text=skip_labels.get(language, skip_labels["uz"])))
    keyboard.add(KeyboardButton(text=get_text(language, "media_menu.back")))
    keyboard.adjust(1)
    return keyboard.as_markup(resize_keyboard=True)

def get_ai_model_selection_keyboard(current_model: str) -> InlineKeyboardMarkup:
    """AI model selection keyboard for admin"""
    from config import AI_MODELS
    
    keyboard = InlineKeyboardBuilder()
    
    for model_key, model_info in AI_MODELS.items():
        is_current = "✅ " if model_key == current_model else ""
        button_text = f"{is_current}{model_info['name']} - {model_info['price']}"
        keyboard.add(InlineKeyboardButton(
            text=button_text,
            callback_data=f"select_ai_model_{model_key}"
        ))
    
    keyboard.adjust(1)
    return keyboard.as_markup()


_EXTRAS_META = {
    "formulas":   {"uz": "🔢 Formulalar",          "ru": "🔢 Формулы",              "en": "🔢 Formulas"},
    "images":     {"uz": "🖼 Infografik rasmlar",   "ru": "🖼 Инфографика",           "en": "🖼 Infographics"},
    "tables":     {"uz": "📊 Taqqoslash jadvallari","ru": "📊 Сравн. таблицы",        "en": "📊 Comparison tables"},
    "glossary":   {"uz": "📖 Lug'at",               "ru": "📖 Глоссарий",             "en": "📖 Glossary"},
    "statistics": {"uz": "📈 Statistika va faktlar","ru": "📈 Статистика и факты",    "en": "📈 Statistics & facts"},
}


def get_extras_keyboard(lang: str, selected: list, base_price: int) -> InlineKeyboardMarkup:
    """Multi-select keyboard for document extras (shown after page count selection)."""
    keyboard = InlineKeyboardBuilder()
    for key, labels in _EXTRAS_META.items():
        add_price = EXTRAS_PRICES[key]
        icon = "✅" if key in selected else "⬜"
        label = labels.get(lang, labels["uz"])
        btn_text = f"{icon} {label}  +{add_price:,} so'm"
        keyboard.add(InlineKeyboardButton(
            text=btn_text,
            callback_data=f"extras_toggle_{key}"
        ))
    extras_total = sum(EXTRAS_PRICES[k] for k in selected)
    total = base_price + extras_total
    if lang == "ru":
        confirm_text = f"Итого: {total:,} сум | Продолжить ➡️"
    elif lang == "en":
        confirm_text = f"Total: {total:,} sum | Continue ➡️"
    else:
        confirm_text = f"Jami: {total:,} so'm | Davom etish ➡️"
    keyboard.add(InlineKeyboardButton(text=confirm_text, callback_data="extras_confirm"))
    keyboard.adjust(1)
    return keyboard.as_markup()