import time
import logging
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile, InputSticker
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.enums import StickerFormat
from aiogram.exceptions import TelegramBadRequest

from database.database import Database
from translations import get_text
from services import sticker_service

router = Router()
logger = logging.getLogger(__name__)

_bot_username: str = ""
STICKER_EMOJI = ["🌟"]


def set_bot_username(username: str) -> None:
    global _bot_username
    _bot_username = username.lower().lstrip("@")


# ── Name helpers ─────────────────────────────────────────────────────────────

def _make_static_set_name(user_id: int) -> str:
    return f"user_{user_id}_by_{_bot_username}"


def _make_video_set_name(user_id: int) -> str:
    return f"uvid_{user_id}_by_{_bot_username}"


def _make_fresh_name(user_id: int, prefix: str) -> str:
    suffix = int(time.time()) % 100000
    return f"{prefix}_{user_id}_{suffix}_by_{_bot_username}"


def _make_set_title(first_name: str, suffix: str = "") -> str:
    name = (first_name or "User").strip()[:18]
    return f"{name} Stickers{suffix}"


# ── Lang helper ───────────────────────────────────────────────────────────────

async def _get_lang(state: FSMContext, db: Database, user_id: int) -> str:
    data = await state.get_data()
    lang = data.get("language")
    if not lang:
        user = await db.get_user(user_id)
        lang = user.language if user else "uz"
    return lang


# ── Error helpers ─────────────────────────────────────────────────────────────

def _is_set_invalid(e: Exception) -> bool:
    return "stickerset_invalid" in str(e).lower().replace("_", "")


def _is_set_full(e: Exception) -> bool:
    txt = str(e).lower()
    return "too many stickers" in txt or "sticker_set_full" in txt


# ── Low-level Telegram calls ──────────────────────────────────────────────────

async def _create_set(bot, user_id: int, set_name: str, title: str,
                      sticker_file: BufferedInputFile,
                      fmt: StickerFormat) -> None:
    input_sticker = InputSticker(
        sticker=sticker_file,
        emoji_list=STICKER_EMOJI,
        format=fmt,
    )
    await bot.create_new_sticker_set(
        user_id=user_id,
        name=set_name,
        title=title,
        stickers=[input_sticker],
    )


async def _add_to_set(bot, user_id: int, set_name: str,
                      sticker_file: BufferedInputFile,
                      fmt: StickerFormat) -> None:
    input_sticker = InputSticker(
        sticker=sticker_file,
        emoji_list=STICKER_EMOJI,
        format=fmt,
    )
    await bot.add_sticker_to_set(
        user_id=user_id,
        name=set_name,
        sticker=input_sticker,
    )


# ── Core sticker-set manager (works for both static and video) ────────────────

async def _ensure_sticker_in_set(
    bot, user_id: int, first_name: str,
    file_bytes: bytes, filename: str,
    fmt: StickerFormat,
    base_set_name: str,
    name_prefix: str,
    title_suffix: str,
    existing_set: str | None,
    db: Database,
    save_fn,
) -> str:
    """
    Add `file_bytes` to the user's sticker set of the given format.
    Creates the set if it doesn't exist yet.
    Returns the final set_name used.
    """
    title = _make_set_title(first_name, title_suffix)

    def _buf():
        return BufferedInputFile(file_bytes, filename=filename)

    if existing_set is None:
        set_name = base_set_name
        try:
            await _create_set(bot, user_id, set_name, title, _buf(), fmt)
            await save_fn(user_id, set_name)
            logger.info(f"Created set {set_name} ({fmt}) for user {user_id}")
        except TelegramBadRequest as e:
            if _is_set_invalid(e):
                # Set already exists on Telegram but not in DB
                logger.warning(f"Set {set_name} exists on Telegram; saving & adding.")
                await save_fn(user_id, set_name)
                try:
                    await _add_to_set(bot, user_id, set_name, _buf(), fmt)
                except TelegramBadRequest as e2:
                    if _is_set_invalid(e2):
                        # Still invalid — use a fresh name
                        fresh = _make_fresh_name(user_id, name_prefix)
                        await _create_set(bot, user_id, fresh, title, _buf(), fmt)
                        await save_fn(user_id, fresh)
                        set_name = fresh
                    else:
                        raise e2
            else:
                raise
    else:
        set_name = existing_set
        try:
            await _add_to_set(bot, user_id, set_name, _buf(), fmt)
        except TelegramBadRequest as e:
            if _is_set_invalid(e):
                # Set was deleted — recreate with a fresh name
                logger.warning(
                    f"Set {set_name} deleted for user {user_id}. Recreating."
                )
                fresh = _make_fresh_name(user_id, name_prefix)
                try:
                    await _create_set(bot, user_id, fresh, title, _buf(), fmt)
                except TelegramBadRequest as e2:
                    if _is_set_invalid(e2):
                        fresh = _make_fresh_name(user_id, name_prefix)
                        await _create_set(bot, user_id, fresh, title, _buf(), fmt)
                    else:
                        raise e2
                await save_fn(user_id, fresh)
                set_name = fresh
                logger.info(f"Recreated set as {fresh} for user {user_id}")
            else:
                raise

    return set_name


# ── Photo handler ─────────────────────────────────────────────────────────────

@router.message(StateFilter(None), F.photo)
async def handle_photo_sticker(message: Message, state: FSMContext, db: Database):
    user_id = message.from_user.id
    lang = await _get_lang(state, db, user_id)
    first_name = message.from_user.first_name or "User"

    wait_msg = await message.answer(get_text(lang, "sticker.processing"))
    try:
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        buf = await message.bot.download_file(file.file_path)
        image_bytes = buf.read()

        webp_bytes = await sticker_service.image_to_webp_sticker(image_bytes)
        del image_bytes

        existing = await db.get_user_sticker_set(user_id)
        set_name = await _ensure_sticker_in_set(
            bot=message.bot,
            user_id=user_id,
            first_name=first_name,
            file_bytes=webp_bytes,
            filename="sticker.webp",
            fmt=StickerFormat.STATIC,
            base_set_name=_make_static_set_name(user_id),
            name_prefix="user",
            title_suffix="",
            existing_set=existing,
            db=db,
            save_fn=db.save_user_sticker_set,
        )
        del webp_bytes

        sticker_set = await message.bot.get_sticker_set(set_name)
        await message.answer_sticker(sticker=sticker_set.stickers[-1].file_id)
        await message.answer(
            get_text(lang, "sticker.ready", link=f"t.me/addstickers/{set_name}")
        )

    except Exception as e:
        logger.error(f"Photo sticker failed for user {user_id}: {e}")
        try:
            await wait_msg.delete()
        except Exception:
            pass
        await message.answer(
            get_text(lang, "sticker.set_full") if _is_set_full(e)
            else get_text(lang, "sticker.error")
        )
        return

    try:
        await wait_msg.delete()
    except Exception:
        pass


# ── Video handler ─────────────────────────────────────────────────────────────

@router.message(StateFilter(None), F.video)
async def handle_video_sticker(message: Message, state: FSMContext, db: Database):
    user_id = message.from_user.id
    lang = await _get_lang(state, db, user_id)
    first_name = message.from_user.first_name or "User"

    wait_msg = await message.answer(get_text(lang, "sticker.video_processing"))
    try:
        video = message.video
        file = await message.bot.get_file(video.file_id)
        buf = await message.bot.download_file(file.file_path)
        video_bytes = buf.read()

        webm_bytes = await sticker_service.video_to_webm_sticker(video_bytes)
        del video_bytes

        existing = await db.get_user_video_sticker_set(user_id)
        set_name = await _ensure_sticker_in_set(
            bot=message.bot,
            user_id=user_id,
            first_name=first_name,
            file_bytes=webm_bytes,
            filename="sticker.webm",
            fmt=StickerFormat.VIDEO,
            base_set_name=_make_video_set_name(user_id),
            name_prefix="uvid",
            title_suffix=" (Video)",
            existing_set=existing,
            db=db,
            save_fn=db.save_user_video_sticker_set,
        )
        del webm_bytes

        sticker_set = await message.bot.get_sticker_set(set_name)
        await message.answer_sticker(sticker=sticker_set.stickers[-1].file_id)
        await message.answer(
            get_text(lang, "sticker.ready", link=f"t.me/addstickers/{set_name}")
        )

    except Exception as e:
        logger.error(f"Video sticker failed for user {user_id}: {e}")
        try:
            await wait_msg.delete()
        except Exception:
            pass
        await message.answer(
            get_text(lang, "sticker.set_full") if _is_set_full(e)
            else get_text(lang, "sticker.error")
        )
        return

    try:
        await wait_msg.delete()
    except Exception:
        pass
