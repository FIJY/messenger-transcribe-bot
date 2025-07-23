# services/telegram_handler.py
import os
import logging
import tempfile
import uuid
import asyncio
import re
import json
from typing import Dict, Any, List, Optional
from telegram import Update, InlineKeyboardMarkup, Bot, Message, BotCommand
from telegram.constants import ParseMode
from bson import ObjectId, errors as bson_errors
from telegram.error import BadRequest

from .database import Database
from .s3_service import S3Service
from .celery_client import get_celery_app_client
from .payment_service import PaymentService
from .telegram_ui import TelegramUI
from .insight_service import InsightService
from .translation_service import TranslationService
from .downloader_service import DownloaderService
from .business_analyzer_service import BusinessAnalyzerService
from .youtube_service import YouTubeService

logger = logging.getLogger(__name__)


class TelegramHandler:
    def __init__(self, token: str, database: Database, s3_service: S3Service,
                 payment_service: PaymentService, insight_service: InsightService,
                 translation_service: TranslationService, downloader_service: DownloaderService,
                 business_analyzer: BusinessAnalyzerService, youtube_service: YouTubeService):
        if not token: raise ValueError("Telegram token is required.")
        self.bot = Bot(token=token)
        self.database = database
        self.s3_service = s3_service
        self.payment_service = payment_service
        self.insight_service = insight_service
        self.translation_service = translation_service
        self.downloader_service = downloader_service
        self.business_analyzer = business_analyzer
        self.youtube_service = youtube_service

        self.celery_app_client = get_celery_app_client()
        self.admin_telegram_id = os.getenv('ADMIN_TELEGRAM_ID')
        self.ui = TelegramUI()

    async def set_bot_commands(self):
        commands = [
            BotCommand("start", "Restart the bot"),
            BotCommand("status", "Check your current plan"),
            BotCommand("search", "Search through your notes"),
            BotCommand("help", "Get help and information"),
            BotCommand("cancel", "Exit current mode (e.g., chat mode)")
        ]
        try:
            await self.bot.set_my_commands(commands)
            logger.info("Bot commands have been set successfully.")
        except Exception as e:
            logger.error(f"Failed to set bot commands: {e}")

    async def handle_update(self, update_data: dict):
        update = Update.de_json(update_data, bot=self.bot)
        if update.callback_query:
            try:
                await self._handle_callback_query(update.callback_query)
            except BadRequest as e:
                if "Query is too old" in str(e) or "Message is not modified" in str(e):
                    logger.warning(f"Handled known BadRequest: {e}")
                else:
                    logger.error(f"Unhandled BadRequest in handle_update: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"Unhandled exception in handle_update: {e}", exc_info=True)
            return

        if not update.message or not update.message.from_user:
            return

        user_id = str(update.message.from_user.id)
        chat_id = update.message.chat_id
        username = update.message.from_user.username

        if update.message.text and update.message.text.startswith('/'):
            await self._handle_command(user_id, chat_id, username, update.message.text)
            return

        user = self.database.get_user(user_id)
        if not user:
            user = await self._handle_start_command(user_id, chat_id, username)

        user_state = user.get('state')
        if user_state and user_state.get('mode') == 'chatting':
            await self._handle_chat_message(user_id, chat_id, update.message.text, user_state)
            return

        if update.message.photo:
            if user.get('state') == 'awaiting_payment_proof':
                await self.payment_service.handle_payment_proof(update.message)
                return

        file_to_process = update.message.document or update.message.audio or update.message.video or update.message.voice or update.message.video_note
        url_match = re.search(r'https?://\S+', update.message.text or "")

        if file_to_process:
            await self._handle_file_upload(file_to_process, user_id, chat_id)
        elif url_match:
            await self._handle_url(url_match.group(0), user_id, chat_id)
        elif update.message.text:
            await self._handle_text_note(update.message.text, user_id, chat_id)

    async def _handle_command(self, user_id: str, chat_id: int, username: Optional[str], text: str):
        command_parts = text.split()
        command = command_parts[0]

        if command == '/start':
            await self._handle_start_command(user_id, chat_id, username)
        elif command == '/status':
            await self._handle_status_command(user_id, chat_id)
        elif command == '/help':
            bot_user = await self.bot.get_me()
            add_to_group_url = f"https://t.me/{bot_user.username}?startgroup=true"
            await self.send_message(chat_id, self.ui.get_help_message(add_to_group_url))
        elif command == '/cancel':
            self.database.update_user(user_id, {'state': None})
            await self.send_message(chat_id, "✅ You have exited the current mode.")
        elif command == '/search':
            query = " ".join(command_parts[1:])
            if not query:
                await self.send_message(chat_id, "Usage: `/search <your query>`")
                return
            await self.send_message(chat_id, f"🔍 Searching for notes matching: `{query}`...")
            notes = self.database.search_notes_by_query(user_id, query)
            response_text = self.ui.format_search_results(notes, query)
            await self.send_message(chat_id, response_text)
        elif command == '/grant':
            if user_id != self.admin_telegram_id:
                await self.send_message(chat_id, "❌ You are not authorized to use this command.")
                return
            try:
                target_user_id = command_parts[1]
                days = int(command_parts[2])
                success = self.database.grant_premium_subscription(target_user_id, days)
                if success:
                    await self.send_message(chat_id, f"✅ Premium granted to user `{target_user_id}` for {days} days.")
                    try:
                        await self.send_message(int(target_user_id),
                                                f"🎉 Your premium has been extended by {days} days!")
                    except Exception as e:
                        logger.warning(f"Could not notify user {target_user_id}: {e}")
                else:
                    await self.send_message(chat_id, f"❌ Could not find user with ID `{target_user_id}`.")
            except (IndexError, ValueError):
                await self.send_message(chat_id, "Usage: `/grant <user_id> <days>`")

    async def _handle_chat_message(self, user_id: str, chat_id: int, question: str, state: dict):
        note_id_str = state.get('note_id')
        if not note_id_str:
            self.database.update_user(user_id, {'state': None})
            await self.send_message(chat_id, "Error: Chat context lost. Exiting chat mode.")
            return

        try:
            note_id = ObjectId(note_id_str)
            note = self.database.get_note_by_id(note_id)
            if not note:
                self.database.update_user(user_id, {'state': None})
                await self.send_message(chat_id,
                                        "Error: The note you were chatting with was deleted. Exiting chat mode.")
                return

            await self.bot.send_chat_action(chat_id, 'typing')

            context = note.get('content', '')
            answer = self.insight_service.get_answer_from_text(context, question)

            await self.send_message(chat_id, answer)

        except (bson_errors.InvalidId, Exception) as e:
            logger.error(f"Error during chat handling for user {user_id}: {e}", exc_info=True)
            await self.send_message(chat_id, "An error occurred. Exiting chat mode.")
            self.database.update_user(user_id, {'state': None})

    async def _handle_text_note(self, text: str, user_id: str, chat_id: int):
        try:
            note_id = self.database.save_note(user_id=user_id, content=text, tags=['plain_text'], source_type='text')
            await self.send_message(chat_id, f"✅ *Note saved:* ```{text[:250]}...```")
            message, reply_markup = self.ui.get_main_actions_menu(note_id)
            await self.send_message(chat_id, message, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error creating text note for user {user_id}: {e}")
            await self.send_message(chat_id, "❌ Sorry, an error occurred while saving your note.")

    async def _handle_url(self, url: str, user_id: str, chat_id: int):
        await self.send_message(chat_id, "🔗 Link received. Processing will start shortly...")
        if self.celery_app_client:
            logger.info(f"Sending URL processing task to Celery for URL: {url}")
            platform_payload = {'platform': 'telegram', 'chat_id': chat_id}
            self.celery_app_client.send_task('tasks.process_url', args=[user_id, url, {}, platform_payload])
        else:
            logger.error("Celery client not available. Cannot process URL.")
            await self.send_message(chat_id, "❌ Server error: cannot queue URL for processing.")

    async def _process_local_file(self, local_file_path: str, user_id: str, chat_id: int, source_type: str):
        try:
            object_key = f"{uuid.uuid4()}{os.path.splitext(local_file_path)[-1]}"
            if not self.s3_service.upload_file(local_file_path, object_key):
                await self.send_message(chat_id, "❌ Server error: could not upload file to storage.")
                return

            if self.celery_app_client:
                logger.info(f"Sending task to Celery for object {object_key}")
                platform_payload = {'platform': 'telegram', 'chat_id': chat_id, 'source_type': source_type}
                self.celery_app_client.send_task('tasks.process_media',
                                                 args=[user_id, object_key, {}, platform_payload])
                await self.send_message(chat_id, "✅ Upload complete. Your file is now being processed...")
        except Exception as e:
            logger.error(f"Error in _process_local_file: {e}", exc_info=True)
            await self.send_message(chat_id, "❌ An error occurred during file processing.")
        finally:
            if local_file_path and os.path.exists(local_file_path):
                os.remove(local_file_path)

    async def _handle_file_upload(self, file_obj: Message, user_id: str, chat_id: int):
        await self.send_message(chat_id, "✅ File received. Downloading...")
        local_file_path = None
        try:
            tg_file = await file_obj.get_file()
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(tg_file.file_path)[-1]) as temp_f:
                local_file_path = temp_f.name
                await tg_file.download_to_drive(custom_path=local_file_path)
            await self._process_local_file(local_file_path, user_id, chat_id, source_type='upload')
        except Exception as e:
            logger.error(f"Error during file download from Telegram: {e}", exc_info=True)
            await self.send_message(chat_id, "❌ Failed to download file from Telegram.")

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

    async def _handle_callback_query(self, query: Update.callback_query):
        await query.answer()
        payload = query.data
        user_id = str(query.from_user.id)

        parts = payload.split('_')
        try:
            note_id = ObjectId(parts[-1])
            action = '_'.join(parts[:-1])
        except (IndexError, bson_errors.InvalidId):
            await query.edit_message_text(f"Error: Invalid callback data '{payload}'", reply_markup=None)
            return

        note = self.database.get_note_by_id(note_id)
        if not note:
            await query.edit_message_text("This menu is no longer active as the note was deleted.", reply_markup=None)
            return

        if action == 'ACTION_CHAT':
            new_state = {'mode': 'chatting', 'note_id': str(note_id)}
            self.database.update_user(user_id, {'state': new_state})
            await query.edit_message_text(
                "You are now in chat mode. Ask me anything about the text!\n\nSend /cancel to exit.", reply_markup=None)
            return

        action_type = action.split('_')[0]
        if action_type == 'ACTION':
            await self._handle_main_action(query, note, action, parts)
        # ... (другие обработчики)

    async def _handle_main_action(self, query: Update.callback_query, note: dict, action: str, parts: List[str]):
        # Здесь ваша существующая логика для других кнопок (SUMMARIZE, DELETE и т.д.)
        # Этот метод нужно будет дописать или скопировать из вашей рабочей версии
        pass

    async def send_message(self, chat_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None):
        try:
            if len(text) > 4096:
                # Логика для отправки длинных сообщений
                parts = text.split('\n\n')
                current_message = ""
                for part in parts:
                    if len(current_message) + len(part) + 2 > 4096:
                        await self.bot.send_message(chat_id=chat_id, text=current_message,
                                                    parse_mode=ParseMode.MARKDOWN)
                        current_message = part
                    else:
                        current_message += "\n\n" + part
                if current_message:
                    await self.bot.send_message(chat_id=chat_id, text=current_message, parse_mode=ParseMode.MARKDOWN,
                                                reply_markup=reply_markup)
            else:
                await self.bot.send_message(
                    chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"Failed to send message to Telegram chat {chat_id}: {e}")
