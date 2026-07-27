from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.database import Database
from bot.keyboards import get_help_keyboard, get_sample_management_keyboard, get_samples_list_keyboard
from translations import get_text
from config import ADMIN_IDS
import logging

logger = logging.getLogger(__name__)

router = Router()

class SampleStates(StatesGroup):
    waiting_for_file = State()
    waiting_for_title = State()
    waiting_for_description = State()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

SAMPLES_TEXTS = ["📁 Namunalar", "📁 Образцы", "📁 Samples"]

@router.message(F.text.in_(SAMPLES_TEXTS))
async def handle_samples_from_main_menu(message: Message, db: Database, user_lang: str):
    """Handle samples button click from main menu"""
    from bot.keyboards import get_main_keyboard
    
    samples = await db.get_all_sample_files()
    
    if not samples:
        await message.answer(
            get_text(user_lang, "samples_title") + "\n\n" + get_text(user_lang, "no_samples"),
            reply_markup=get_main_keyboard(user_lang)
        )
        return
    
    # Send title message
    await message.answer(get_text(user_lang, "samples_title"))
    
    # Send each sample file
    for sample in samples:
        caption = f"📁 {sample['title']}"
        if sample.get('description'):
            caption += f"\n\n{sample['description']}"
        
        try:
            if sample['file_type'] == 'document':
                await message.answer_document(document=sample['file_id'], caption=caption)
            elif sample['file_type'] == 'photo':
                await message.answer_photo(photo=sample['file_id'], caption=caption)
            elif sample['file_type'] == 'video':
                await message.answer_video(video=sample['file_id'], caption=caption)
        except Exception as e:
            logger.error(f"Error sending sample file: {e}")

@router.callback_query(F.data == "view_samples")
async def handle_view_samples(callback: CallbackQuery, db: Database):
    """Handle view samples button click from help section"""
    await callback.answer()
    
    user = await db.get_user(callback.from_user.id)
    language = user.language if user else "uz"
    
    samples = await db.get_all_sample_files()
    
    if not samples:
        await callback.message.edit_text(
            get_text(language, "samples_title") + "\n\n" + get_text(language, "no_samples"),
            reply_markup=get_help_keyboard(language)
        )
        return
    
    # Send title message
    await callback.message.answer(
        get_text(language, "samples_title")
    )
    
    # Send each sample file
    for sample in samples:
        caption = f"📁 {sample['title']}"
        if sample.get('description'):
            caption += f"\n\n{sample['description']}"
        
        try:
            if sample['file_type'] == 'document':
                await callback.message.answer_document(
                    document=sample['file_id'],
                    caption=caption
                )
            elif sample['file_type'] == 'photo':
                await callback.message.answer_photo(
                    photo=sample['file_id'],
                    caption=caption
                )
            elif sample['file_type'] == 'video':
                await callback.message.answer_video(
                    video=sample['file_id'],
                    caption=caption
                )
        except Exception as e:
            logger.error(f"Error sending sample file: {e}")
    
    # Answer the callback to remove loading state
    await callback.answer()

@router.message(F.text == "📁 Namunalar boshqaruvi")
async def handle_samples_management(message: Message):
    """Handle samples management button for admin"""
    if not is_admin(message.from_user.id):
        return
    
    await message.answer(
        "📁 Namunalar boshqaruvi\n\nTanlang:",
        reply_markup=get_sample_management_keyboard()
    )

@router.callback_query(F.data == "add_sample")
async def handle_add_sample(callback: CallbackQuery, state: FSMContext):
    """Start adding a new sample"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q", show_alert=True)
        return
    
    await callback.answer()
    await callback.message.edit_text("📎 Namuna faylini yuboring (hujjat, rasm yoki video):")
    await state.set_state(SampleStates.waiting_for_file)

@router.message(SampleStates.waiting_for_file, F.document | F.photo | F.video)
async def handle_sample_file(message: Message, state: FSMContext):
    """Receive sample file from admin"""
    if not is_admin(message.from_user.id):
        return
    
    file_id = None
    file_type = None
    
    if message.document:
        file_id = message.document.file_id
        file_type = 'document'
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_type = 'photo'
    elif message.video:
        file_id = message.video.file_id
        file_type = 'video'
    
    await state.update_data(file_id=file_id, file_type=file_type)
    await message.answer("📝 Namuna nomini kiriting:")
    await state.set_state(SampleStates.waiting_for_title)

@router.message(SampleStates.waiting_for_title)
async def handle_sample_title(message: Message, state: FSMContext):
    """Receive sample title from admin"""
    if not is_admin(message.from_user.id):
        return
    
    await state.update_data(title=message.text)
    await message.answer("📄 Namuna tavsifini kiriting (yoki /skip bosing):")
    await state.set_state(SampleStates.waiting_for_description)

@router.message(SampleStates.waiting_for_description)
async def handle_sample_description(message: Message, state: FSMContext, db: Database):
    """Receive sample description and save to database"""
    if not is_admin(message.from_user.id):
        return
    
    data = await state.get_data()
    description = "" if message.text == "/skip" else message.text
    
    success = await db.add_sample_file(
        title=data['title'],
        description=description,
        file_id=data['file_id'],
        file_type=data['file_type']
    )
    
    if success:
        await message.answer("✅ Namuna muvaffaqiyatli qo'shildi!")
    else:
        await message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")
    
    await state.clear()

@router.callback_query(F.data == "delete_sample")
async def handle_delete_sample(callback: CallbackQuery, db: Database):
    """Show samples list for deletion"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q", show_alert=True)
        return
    
    await callback.answer()
    
    samples = await db.get_all_sample_files()
    
    if not samples:
        await callback.message.edit_text(
            "Hozircha namunalar mavjud emas.",
            reply_markup=get_sample_management_keyboard()
        )
        return
    
    await callback.message.edit_text(
        "🗑 O'chirish uchun namunani tanlang:",
        reply_markup=get_samples_list_keyboard(samples)
    )

@router.callback_query(F.data.startswith("delete_sample_"))
async def handle_confirm_delete_sample(callback: CallbackQuery, db: Database):
    """Delete selected sample"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q", show_alert=True)
        return
    
    sample_id = int(callback.data.split("_")[2])
    
    success = await db.delete_sample_file(sample_id)
    
    if success:
        await callback.answer("✅ Namuna o'chirildi!", show_alert=True)
        
        samples = await db.get_all_sample_files()
        if samples:
            await callback.message.edit_text(
                "🗑 O'chirish uchun namunani tanlang:",
                reply_markup=get_samples_list_keyboard(samples)
            )
        else:
            await callback.message.edit_text(
                "Barcha namunalar o'chirildi.",
                reply_markup=get_sample_management_keyboard()
            )
    else:
        await callback.answer("❌ Xatolik yuz berdi", show_alert=True)

@router.callback_query(F.data == "list_samples")
async def handle_list_samples(callback: CallbackQuery, db: Database):
    """Show all samples list"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q", show_alert=True)
        return
    
    await callback.answer()
    
    samples = await db.get_all_sample_files()
    
    if not samples:
        await callback.message.edit_text(
            "Hozircha namunalar mavjud emas.",
            reply_markup=get_sample_management_keyboard()
        )
        return
    
    samples_text = "📋 Namunalar ro'yxati:\n\n"
    for i, sample in enumerate(samples, 1):
        samples_text += f"{i}. 📁 {sample['title']}"
        if sample.get('description'):
            samples_text += f"\n   {sample['description']}"
        
        created_at = sample.get('created_at', 'Noma\'lum')
        if isinstance(created_at, str):
            date_str = created_at[:10]
        else:
            date_str = created_at.strftime('%Y-%m-%d')
            
        samples_text += f"\n   📅 {date_str}\n\n"
    
    await callback.message.edit_text(
        samples_text,
        reply_markup=get_sample_management_keyboard()
    )

@router.callback_query(F.data == "back_to_sample_menu")
async def handle_back_to_sample_menu(callback: CallbackQuery):
    """Go back to sample management menu"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Ruxsat yo'q", show_alert=True)
        return
    
    await callback.answer()
    await callback.message.edit_text(
        "📁 Namunalar boshqaruvi\n\nTanlang:",
        reply_markup=get_sample_management_keyboard()
    )
