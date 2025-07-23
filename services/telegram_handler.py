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
from .localization_service import LocalizationService
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

        self.localizer = LocalizationService()
        self.ui = TelegramUI(self.localizer)

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

        effective_user = None
        effective_chat = None

        if update.callback_query:
            effective_user = update.callback_query.from_user
            effective_chat = update.callback_query.message.chat
        elif update.message:
            effective_user = update.message.from_user
            effective_chat = update.message.chat

        if not effective_user or not effective_chat:
            return

        user_id = str(effective_user.id)
        chat_id = effective_chat.id
        username = effective_user.username
        lang_code = effective_user.language_code or 'en'

        user = self.database.get_user(user_id)
        if not user:
            user = self.database.create_user(user_id, username=username, language_code=lang_code)

        user_lang = user.get('language_code', 'en')

        if update.callback_query:
            await self._handle_callback_query(update.callback_query, user_lang)
            return

        if update.message and update.message.text and update.message.text.startswith('/'):
            await self._handle_command(user_id, chat_id, username, update.message.text, user_lang)
            return

        user_state = user.get('state')
        if update.message and isinstance(user_state, dict) and user_state.get('mode') == 'chatting':
            await self._handle_chat_message(user_id, chat_id, update.message.text, user_state, user_lang)
            return

        if update.message and update.message.photo and isinstance(user_state, dict) and user_state.get(
                'mode') == 'awaiting_payment_proof':
            await self.payment_service.handle_payment_proof(update.message)
            return

        if update.message:
            file_to_process = update.message.document or update.message.audio or update.message.video or update.message.voice or update.message.video_note
            url_match = re.search(r'https?://\S+', update.message.text or "")

            if file_to_process:
                await self._handle_file_upload(file_to_process, user_id, chat_id, user_lang)
            elif url_match:
                await self._handle_url(url_match.group(0), user_id, chat_id, user_lang)
            elif update.message.text:
                await self._handle_text_note(update.message.text, user_id, chat_id, user_lang)

    async def _handle_command(self, user_id: str, chat_id: int, username: Optional[str], text: str, lang_code: str):
        command_parts = text.split()
        command = command_parts[0]

        if command == '/start':
            await self._handle_start_command(user_id, chat_id, username, lang_code)
        elif command == '/status':
            await self._handle_status_command(user_id, chat_id)
        elif command == '/help':
            bot_user = await self.bot.get_me()
            add_to_group_url = f"https://t.me/{bot_user.username}?startgroup=true"
            await self.send_message(chat_id, self.ui.get_help_message(lang_code, add_to_group_url))
        elif command == '/cancel':
            self.database.update_user(user_id, {'state': None})
            await self.send_message(chat_id, self.localizer.get_string(lang_code, 'chat_mode_exited'))
        elif command == '/search':
            query = " ".join(command_parts[1:])
            if not query:
                await self.send_message(chat_id, "Usage: `/search <your query>`")
                return
            await self.send_message(chat_id, f"🔍 Searching for notes matching: `{query}`...")
            notes = self.database.search_notes_by_query(user_id, query)
            response_text = self.ui.format_search_results(lang_code, notes, query)
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

    async def _handle_chat_message(self, user_id: str, chat_id: int, question: str, state: dict, lang_code: str):
        # ИСПРАВЛЕНИЕ: Проверяем, что пользователь прислал именно текст
        if not question:
            await self.send_message(chat_id,
                                    "Please send a text question. I can't process other message types in chat mode.")
            return

        note_id_str = state.get('note_id')
        if not note_id_str:
            self.database.update_user(user_id, {'state': None})
            await self.send_message(chat_id, self.localizer.get_string(lang_code, 'error_chat_context_lost'))
            return
        try:
            note = self.database.get_note_by_id(ObjectId(note_id_str))
            if not note:
                self.database.update_user(user_id, {'state': None})
                await self.send_message(chat_id, self.localizer.get_string(lang_code, 'error_note_deleted'))
                return
            await self.bot.send_chat_action(chat_id, 'typing')
            answer = self.insight_service.get_answer_from_text(note.get('content', ''), question)
            await self.send_message(chat_id, answer)
        except Exception as e:
            logger.error(f"Error during chat handling: {e}", exc_info=True)
            await self.send_message(chat_id, self.localizer.get_string(lang_code, 'error_generic'))
            self.database.update_user(user_id, {'state': None})

    async def _handle_text_note(self, text: str, user_id: str, chat_id: int, lang_code: str):
        try:
            note_id = self.database.save_note(user_id=user_id, content=text, tags=['plain_text'], source_type='text')
            await self.send_message(chat_id, f"✅ *Note saved:* ```{text[:250]}...```")
            message, reply_markup = self.ui.get_main_actions_menu(lang_code, note_id)
            await self.send_message(chat_id, message, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error creating text note for user {user_id}: {e}")
            await self.send_message(chat_id, "❌ Sorry, an error occurred while saving your note.")

    async def _handle_url(self, url: str, user_id: str, chat_id: int, lang_code: str):
        status_message = await self.send_message(chat_id, self.localizer.get_string(lang_code, 'task_accepted'))
        if not status_message: return

        if self.celery_app_client:
            platform_payload = {'platform': 'telegram', 'chat_id': chat_id, 'lang_code': lang_code,
                                'message_id': status_message.message_id}
            self.celery_app_client.send_task('tasks.process_url', args=[user_id, url, {}, platform_payload])
        else:
            await self.edit_message(chat_id, status_message.message_id,
                                    "❌ Server error: cannot queue URL for processing.")

    async def _process_local_file(self, local_file_path: str, user_id: str, chat_id: int, source_type: str,
                                  lang_code: str, status_message: Message):
        try:
            object_key = f"{uuid.uuid4()}{os.path.splitext(local_file_path)[-1]}"
            if not self.s3_service.upload_file(local_file_path, object_key):
                await self.edit_message(chat_id, status_message.message_id,
                                        "❌ Server error: could not upload file to storage.")
                return

            if self.celery_app_client:
                logger.info(f"Sending task to Celery for object {object_key}")
                platform_payload = {
                    'platform': 'telegram',
                    'chat_id': chat_id,
                    'source_type': source_type,
                    'lang_code': lang_code,
                    'message_id': status_message.message_id
                }
                self.celery_app_client.send_task('tasks.process_media',
                                                 args=[user_id, object_key, {}, platform_payload])
                await self.edit_message(chat_id, status_message.message_id,
                                        self.localizer.get_string(lang_code, 'upload_complete'))
        except Exception as e:
            logger.error(f"Error in _process_local_file: {e}", exc_info=True)
            await self.edit_message(chat_id, status_message.message_id, "❌ An error occurred during file processing.")
        finally:
            if local_file_path and os.path.exists(local_file_path):
                os.remove(local_file_path)

    async def _handle_file_upload(self, file_obj: Message, user_id: str, chat_id: int, lang_code: str):
        status_message = await self.send_message(chat_id, self.localizer.get_string(lang_code, 'file_received'))
        if not status_message: return
        local_file_path = None
        try:
            tg_file = await file_obj.get_file()
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(tg_file.file_path)[-1]) as temp_f:
                local_file_path = temp_f.name
                await tg_file.download_to_drive(custom_path=local_file_path)
            await self._process_local_file(local_file_path, user_id, chat_id, 'upload', lang_code, status_message)
        except Exception as e:
            logger.error(f"Error during file download from Telegram: {e}", exc_info=True)
            await self.edit_message(chat_id, status_message.message_id, "❌ Failed to download file from Telegram.")

    async def _handle_start_command(self, user_id: str, chat_id: int, username: Optional[str], lang_code: str):
        user = self.database.get_user(user_id)
        if not user:
            user = self.database.create_user(user_id, username=username, language_code=lang_code)
        await self.send_message(chat_id, self.ui.get_welcome_message(lang_code))
        return user

    async def _handle_status_command(self, user_id: str, chat_id: int):
        user = self.database.get_user(user_id)
        if not user:
            await self.send_message(chat_id, "Please use /start first.")
            return
        message = self.ui.get_status_message(user)
        await self.send_message(chat_id, message)

    async def _handle_callback_query(self, query: Update.callback_query, lang_code: str):
        await query.answer()
        payload = query.data
        user_id = str(query.from_user.id)

        parts = payload.split('_')
        try:
            note_id = ObjectId(parts[-1])
            action = '_'.join(parts[:-1])
        except (IndexError, bson_errors.InvalidId):
            return

        note = self.database.get_note_by_id(note_id)
        if not note:
            await query.edit_message_text("This menu is no longer active.", reply_markup=None)
            return

        if action == 'ACTION_CHAT':
            new_state = {'mode': 'chatting', 'note_id': str(note_id)}
            self.database.update_user(user_id, {'state': new_state})
            await query.edit_message_text(self.localizer.get_string(lang_code, 'chat_mode_entered'), reply_markup=None)
            return

        await self._handle_main_action(query, note, action, parts, lang_code)

    async def _handle_main_action(self, query: Update.callback_query, note: dict, action: str, parts: List[str],
                                  lang_code: str):
        note_id = note['_id']
        chat_id = query.message.chat_id

        if action == 'ACTION_SUMMARIZE':
            await self.bot.send_chat_action(chat_id, 'typing')
            summary = self.insight_service.get_summary(note['content'])
            await self.send_message(chat_id, f"*Summary:*\n{summary or 'Could not generate summary.'}")

        elif action == 'ACTION_BIZANALYSIS':
            await query.edit_message_text("🤖 Starting comprehensive business analysis...", reply_markup=None)
            analysis_result = self.business_analyzer.run_comprehensive_analysis(note['content'])
            if analysis_result:
                self.database.update_note(note_id, {"$set": {"business_analysis": analysis_result}})
                # This part assumes a method exists in UI to get this specific menu
                # For now, we just send a confirmation.
                await self.send_message(chat_id, "Business analysis is complete.")
                await query.delete_message()
            else:
                await self.send_message(chat_id, "❌ Failed to perform business analysis.")

        elif action == 'ACTION_DELETE':
            text, markup = self.ui.get_delete_confirmation(lang_code, note_id)
            await query.edit_message_text(text, reply_markup=markup)

        elif action == 'ACTION_DELETE_CONFIRM':
            if self.database.delete_note(note_id):
                await query.edit_message_text("🗑️ Note successfully deleted.", reply_markup=None)

        elif action == 'ACTION_DELETE_CANCEL':
            text, markup = self.ui.get_main_actions_menu(lang_code, note_id)
            await query.edit_message_text(text, reply_markup=markup)

        elif action == 'ACTION_SUBTITLES':
            await self.bot.send_chat_action(chat_id, 'typing')
            s3_key = note.get('s3_object_key', '')
            match = re.search(r'yt_([a-zA-Z0-9_-]{11})', s3_key)
            if not match:
                await self.send_message(chat_id, "Could not extract YouTube video ID from the record.")
                return

            video_id = match.group(1)
            video_url = f"https://www.youtube.com/watch?v={video_id}"

            await self.send_message(chat_id, "🤖 Trying to download existing subtitles from YouTube...")
            srt_path, error = self.youtube_service.download_subtitles(video_url)

            if srt_path:
                try:
                    with open(srt_path, 'rb') as srt_file:
                        await self.bot.send_document(chat_id=chat_id, document=srt_file, filename=f"{note_id}.srt",
                                                     caption="Here are the subtitles from YouTube.")
                finally:
                    if os.path.exists(srt_path): os.remove(srt_path)
            else:
                await self.send_message(chat_id, f"Could not download subtitles: {error}.")

    async def send_message(self, chat_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None) -> \
    Optional[Message]:
        try:
            return await self.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN,
                                               reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to send message to Telegram chat {chat_id}: {e}")
            return None

    async def edit_message(self, chat_id: int, message_id: int, text: str,
                           reply_markup: Optional[InlineKeyboardMarkup] = None):
        try:
            await self.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text,
                                             parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                logger.error(f"Failed to edit message {message_id} in chat {chat_id}: {e}")
        except Exception as e:
            logger.error(f"Failed to edit message {message_id} in chat {chat_id}: {e}")

    async def delete_message(self, chat_id: int, message_id: int):
        try:
            await self.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.error(f"Failed to delete message {message_id} in chat {chat_id}: {e}")
