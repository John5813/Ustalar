import logging
from typing import List
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from database.models import Channel

logger = logging.getLogger(__name__)

class ChannelService:
    def __init__(self, bot: Bot):
        self.bot = bot
    
    async def check_user_subscription(self, user_id: int, channels: List[Channel]) -> bool:
        """Check if user is subscribed to all required channels"""
        try:
            accessible_channels = []
            
            # First, check which channels are accessible
            for channel in channels:
                if await self._validate_channel_access(channel.channel_id):
                    accessible_channels.append(channel)
                else:
                    logger.warning(f"Channel {channel.channel_id} is not accessible to bot - skipping subscription check")
            
            # If no channels are accessible, allow access (don't block user due to admin error)
            if not accessible_channels:
                logger.warning("No accessible channels found - allowing access")
                return True
            
            # Check subscription to accessible channels only
            for channel in accessible_channels:
                if not await self._is_user_subscribed(user_id, channel.channel_id):
                    return False
            return True
            
        except Exception as e:
            logger.error(f"Error checking user subscription: {e}")
            # In case of error, allow access (don't block user due to technical issues)
            return True
    
    async def _is_user_subscribed(self, user_id: int, channel_id: str) -> bool:
        """Check if user is subscribed to a specific channel"""
        try:
            member = await self.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            
            # User is subscribed if they are member, administrator, or creator
            return member.status in ['member', 'administrator', 'creator']
            
        except TelegramAPIError as e:
            # User is not a member or channel doesn't exist
            logger.warning(f"User {user_id} not found in channel {channel_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error checking subscription for user {user_id} in channel {channel_id}: {e}")
            return False
            
    async def _validate_channel_access(self, channel_id: str) -> bool:
        """Check if bot has access to the channel"""
        try:
            chat = await self.bot.get_chat(chat_id=channel_id)
            return True
        except TelegramAPIError as e:
            logger.warning(f"Bot cannot access channel {channel_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error validating channel access {channel_id}: {e}")
            return False
    
    async def validate_channel(self, channel_id: str) -> bool:
        """Validate if channel exists and bot has access"""
        try:
            chat = await self.bot.get_chat(chat_id=channel_id)
            
            # Check if it's a channel or supergroup
            return chat.type in ['channel', 'supergroup']
            
        except TelegramAPIError as e:
            logger.error(f"Error validating channel {channel_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error validating channel {channel_id}: {e}")
            return False
    
    async def get_channel_info(self, channel_id: str) -> dict:
        """Get channel information"""
        try:
            chat = await self.bot.get_chat(chat_id=channel_id)
            
            return {
                'id': chat.id,
                'title': chat.title,
                'username': chat.username,
                'type': chat.type,
                'member_count': await self._get_member_count(channel_id)
            }
            
        except Exception as e:
            logger.error(f"Error getting channel info for {channel_id}: {e}")
            return None
    
    async def _get_member_count(self, channel_id: str) -> int:
        """Get channel member count"""
        try:
            count = await self.bot.get_chat_member_count(chat_id=channel_id)
            return count
        except Exception as e:
            logger.warning(f"Could not get member count for {channel_id}: {e}")
            return 0
