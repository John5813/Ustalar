from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from database.database import Database
from config import ADMIN_IDS
import logging

logger = logging.getLogger(__name__)

class DatabaseMiddleware(BaseMiddleware):
    """Middleware to inject database instance"""

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        data["db"] = Database()
        return await handler(event, data)

class LanguageMiddleware(BaseMiddleware):
    """Middleware to inject user language and feature statuses"""

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        db = data.get("db")
        if db:
            user_id = event.from_user.id
            user = await db.get_user(user_id)

            if not user:
                logger.warning(f"⚠️ User not found in database: user_id={user_id}, defaulting to 'uz' language")

            data["user_lang"] = user.language if user else "uz"
            data["user"] = user

            # Add feature statuses
            data["presentation_enabled"] = await db.get_feature_status("presentation")
            data["independent_work_enabled"] = await db.get_feature_status("independent_work")
            data["referat_enabled"] = await db.get_feature_status("referat")
        return await handler(event, data)

class BlockedUserMiddleware(BaseMiddleware):
    """Middleware to check if user is blocked"""
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id

        # Skip check for admins
        if user_id in ADMIN_IDS:
            return await handler(event, data)

        # Check if user is blocked
        db = Database()
        is_blocked = await db.is_user_blocked(user_id)

        if is_blocked:
            # Don't process the message/callback for blocked users
            if isinstance(event, Message):
                await event.answer("🚫 Siz botdan foydalanish huquqiga ega emassiz.")
            elif isinstance(event, CallbackQuery):
                await event.answer("🚫 Siz botdan foydalanish huquqiga ega emassiz.", show_alert=True)
            return

        return await handler(event, data)