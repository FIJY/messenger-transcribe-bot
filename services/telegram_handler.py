# services/telegram_handler.py
import os
import logging
import tempfile
import httpx
import uuid
import asyncio
from typing import Dict, Any, List, Optional
from telegram import Update, InlineKeyboardMarkup, Bot, Message, BotCommand
from datetime import datetime, timezone
import re
from bson import ObjectId

from .database import Database
from .s3_service import S3Service
from .celery_client import get_celery_app_client
from .payment_service import PaymentService
from .telegram_ui import TelegramUI
from .youtube_service import YouTubeService
from config.transcrib_suggestion_config import SUPPORTED_LANGUAGES_MAP

logger = logging.getLogger(__name__)


class TelegramHandler:
    def __init__(self, token: str, database: Database, s3_service: S3Service,
                 payment_service: PaymentService):
        if not token: raise ValueError("Telegram token is required.")
        self.bot = Bot(token=token)
        self.database = database
        self.s3_service = s3_service
        self.celery_app_client = get_celery_app_client()
        self.payment_service = payment_service
        self.admin_telegram_id = os.getenv('ADMIN_TELEGRAM_ID')
        self.ui = TelegramUI()
        self.youtube_service = YouTubeService()

    async def set_bot_commands(self):
        """Устанавливает список команд, видимых в меню Telegram."""
        commands = [
            BotCommand("start", "Start or restart the bot"),
            BotCommand("status", "Check your plan and minute balance"),
            BotCommand("search", "Search through your notes"),
            BotCommand("summary", "Get a summary of recent notes"),
            BotCommand("help", "Get help and information")
        ]
        try:
            await self.bot.set_my_commands(commands)
            logger.info("Bot commands have been set successfully.")
        except Exception as e:
            logger.error(f"Failed to set bot commands: {e}")

    async def handle_update(self, update_data: dict):
        update = Update.de_json(update_data, bot=self.bot)
        if update.callback_query:
            await self._handle_callback_query(update.callback_query)
            return
        if not update.message or not update.message.from_user:
            return

        user_id = str(update.message.from_user.id)
        chat_id = update.message.chat_id
        username = update.message.from_user.username

        if update.message.text:
            if self.youtube_service.is_youtube_link(update.message.text):
                await self._handle_youtube_link(update.message)
                return

            if update.message.text.startswith('/'):
                command_parts = update.message.text.split()
                command = command_parts[0]

                if command == '/start':
                    await self._handle_start_command(user_id, chat_id, username)
                    return
                if command == '/status':
                    await self._handle_status_command(user_id, chat_id)
                    return
                if command == '/help':
                    # ===> ИЗМЕНЕНИЕ: Формируем и передаем URL для добавления в группу <===
                    bot_user = await self.bot.get_me()
                    add_to_group_url = f"https://t.me/{bot_user.username}?startgroup=true"
                    await self.send_message(chat_id, self.ui.get_help_message(add_to_group_url))
                    return
                if command == '/search' or command == '/summary':
                    await self.send_message(chat_id, "This feature is under development and will be available soon!")
                    return

                if user_id == self.admin_telegram_id:
                    if command == '/confirm':
                        await self._handle_confirm_command(command_parts, chat_id)
                        return
                    if command == '/check':
                        await self._handle_check_command(command_parts, chat_id)
                        return

        user = self.database.get_user(user_id)
        if not user:
            user = await self._handle_start_command(user_id, chat_id, username)

        if update.message.photo:
            if user.get('state') == 'awaiting_payment_proof':
                await self.payment_service.handle_payment_proof(update.message)
                return

        file_to_process = update.message.document or update.message.audio or update.message.video or update.message.voice
        if file_to_process:
            await self._handle_file(file_to_process, user_id, chat_id)
        elif update.message.text:
            await self._handle_text_note(update.message.text, user_id, chat_id)

    async def _handle_youtube_link(self, message: Message):
        url = message.text
        chat_id = message.chat_id
        user_id = str(message.from_user.id)

        await self.send_message(chat_id, "✅ YouTube link received. Starting to download audio...")

        asyncio.create_task(self._process_youtube_download(url, user_id, chat_id))

    async def _process_youtube_download(self, url: str, user_id: str, chat_id: int):
        download_result = self.youtube_service.download_audio(url)

        if "error" in download_result:
            await self.send_message(chat_id, f"❌ Error: {download_result['error']}")
            return

        local_file_path = download_result.get("local_path")
        try:
            self._queue_file_for_processing(local_file_path, user_id, chat_id)
        finally:
            if local_file_path and os.path.exists(local_file_path):
                os.remove(local_file_path)

    async def _handle_text_note(self, text: str, user_id: str, chat_id: int):
        try:
            note_id = self.database.save_note(user_id=user_id, content=text)
            message, reply_markup = self.ui.get_note_created_message(text, note_id)
            await self.send_message(chat_id, message, reply_markup)
        except Exception as e:
            logger.error(f"Error creating text note for user {user_id}: {e}")
            await self.send_message(chat_id, "❌ Sorry, an error occurred while saving your note.")

    async def _handle_file(self, file_obj, user_id: str, chat_id: int):
        TELEGRAM_FILE_SIZE_LIMIT = 20 * 1024 * 1024
        if hasattr(file_obj, 'file_size') and file_obj.file_size and file_obj.file_size > TELEGRAM_FILE_SIZE_LIMIT:
            await self.send_message(chat_id,
                                    f"❌ File is too large ({file_obj.file_size / 1024 / 1024:.1f}MB). The maximum file size for bots is 20MB.")
            return

        await self.send_message(chat_id, "✅ File received. Processing...")
        local_file_path = None
        try:
            tg_file = await file_obj.get_file()
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(tg_file.file_path)[-1]) as temp_f:
                local_file_path = temp_f.name
                await tg_file.download_to_drive(custom_path=local_file_path)

            self._queue_file_for_processing(local_file_path, user_id, chat_id)
        except Exception as e:
            logger.error(f"Error handling Telegram file: {e}", exc_info=True)
            if "File is too big" in str(e):
                await self.send_message(chat_id, "❌ Error: The file is too large to download (over 20MB).")
            else:
                await self.send_message(chat_id, "❌ An error occurred while processing your file.")
        finally:
            if local_file_path and os.path.exists(local_file_path): os.remove(local_file_path)

    def _queue_file_for_processing(self, local_file_path: str, user_id: str, chat_id: int):
        try:
            object_key = f"{uuid.uuid4()}{os.path.splitext(local_file_path)[-1]}"
            if not self.s3_service.upload_file(local_file_path, object_key):
                logger.error("Failed to upload file to S3.")
                asyncio.run(self.send_message(chat_id, "❌ Server error: could not save file."))
                return

            if self.celery_app_client:
                self.celery_app_client.send_task('tasks.process_media', args=[user_id, object_key, {},
                                                                              {'platform': 'telegram',
                                                                               'chat_id': chat_id}])
            else:
                logger.error("Celery client not available.")
        except Exception as e:
            logger.error(f"Error in _queue_file_for_processing: {e}", exc_info=True)

    async def _handle_start_command(self, user_id: str, chat_id: int, username: Optional[str]):
        user = self.database.get_user(user_id)
        if not user:
            user = self.database.create_user(user_id, username=username)
        await self.send_message(chat_id, self.ui.get_welcome_message())
        return user

    async def _handle_status_command(self, user_id: str, chat_id: int):
        user = self.database.get_user(user_id)
        if not user:
            await self.send_message(chat_id, "Please use /start first.")
            return
        message = self.ui.get_status_message(user)
        await self.send_message(chat_id, message)

    async def _handle_confirm_command(self, command_parts: List[str], chat_id: int):

    # ... (метод без изменений)

    async def _handle_check_command(self, command_parts: List[str], chat_id: int):

    # ... (метод без изменений)

    async def _handle_callback_query(self, query: Update.callback_query):
        await query.answer()
        payload = query.data
        chat_id = query.message.chat_id

        if payload.startswith('NOTE_'):
            parts = payload.split('_')
            action = parts[1]
            note_id_str = parts[2]

            if action == 'TODO':
                await self.send_message(chat_id, f"✅ Marked as TODO. (This feature is coming soon!)")
            elif action == 'FIND':
                await self.send_message(chat_id, "🔍 Finding related notes... (This feature is coming soon!)")
            elif action == 'SHARE':
                await self.send_message(chat_id, "Sharing options... (This feature is coming soon!)")
            elif action == 'DELETE':
                await self.send_message(chat_id, "🗑️ Note deleted. (This feature is coming soon!)")
        elif payload == 'SHOW_PAYMENT_QR':
        # ... (метод без изменений)
        else:
            await self.send_message(chat_id, "Sorry, this action is no longer supported.")

    async def send_message(self, chat_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None):
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send message to Telegram chat {chat_id}: {e}")