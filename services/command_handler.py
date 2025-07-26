# services/command_handler.py
import logging
from typing import Optional
from telegram import Message, Bot, BotCommand
from telegram.constants import ParseMode

from .database import Database
from .telegram_ui import TelegramUI
from .localization_service import LocalizationService

logger = logging.getLogger(__name__)

class CommandHandler:
    def __init__(self, bot: Bot, db: Database, ui: TelegramUI, localizer: LocalizationService, admin_id: str):
        self.bot = bot
        self.db = db
        self.ui = ui
        self.localizer = localizer
        self.admin_id = admin_id

    async def handle(self, message: Message, user_lang: str):
        user_id = str(message.from_user.id)
        chat_id = message.chat_id
        username = message.from_user.username
        text = message.text
        command_parts = text.split()
        command = command_parts[0]

        if command == '/start':
            await self._handle_start(user_id, chat_id, username, user_lang)
        elif command == '/status':
            await self._handle_status(user_id, chat_id)
        elif command == '/help':
            bot_user = await self.bot.get_me()
            add_to_group_url = f"https://t.me/{bot_user.username}?startgroup=true"
            await self.bot.send_message(chat_id, self.ui.get_help_message(user_lang, add_to_group_url), parse_mode=ParseMode.MARKDOWN)
        elif command == '/cancel':
            self.db.update_user(user_id, {'state': None})
            await self.bot.send_message(chat_id, self.localizer.get_string(user_lang, 'chat_mode_exited'))
        elif command == '/grant':
            await self._handle_grant(user_id, chat_id, command_parts)

    async def _handle_start(self, user_id: str, chat_id: int, username: Optional[str], lang_code: str):
        user = self.db.get_user(user_id)
        if not user:
            self.db.create_user(user_id, username=username, language_code=lang_code)
        await self.bot.send_message(chat_id, self.ui.get_welcome_message(lang_code))

    async def _handle_status(self, user_id: str, chat_id: int):
        user = self.db.get_user(user_id)
        if not user:
            await self.bot.send_message(chat_id, "Please use /start first.")
            return
        message = self.ui.get_status_message(user)
        await self.bot.send_message(chat_id, message, parse_mode=ParseMode.MARKDOWN)

    async def _handle_grant(self, user_id: str, chat_id: int, command_parts: list):
        if user_id != self.admin_id:
            await self.bot.send_message(chat_id, "❌ You are not authorized to use this command.")
            return
        try:
            target_user_id, days = command_parts[1], int(command_parts[2])
            if self.db.grant_premium_subscription(target_user_id, days):
                await self.bot.send_message(chat_id, f"✅ Premium granted to user `{target_user_id}` for {days} days.", parse_mode=ParseMode.MARKDOWN)
                try:
                    await self.bot.send_message(int(target_user_id), f"🎉 Your premium has been extended by {days} days!")
                except Exception as e:
                    logger.warning(f"Could not notify user {target_user_id}: {e}")
            else:
                await self.bot.send_message(chat_id, f"❌ Could not find user with ID `{target_user_id}`.", parse_mode=ParseMode.MARKDOWN)
        except (IndexError, ValueError):
            await self.bot.send_message(chat_id, "Usage: `/grant <user_id> <days>`", parse_mode=ParseMode.MARKDOWN)
