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

from .database import Database
from .s3_service import S3Service
from .celery_client import get_celery_app_client
from .translation_service import TranslationService
from .payment_service import PaymentService
from .telegram_ui import TelegramUI
from .youtube_service import YouTubeService
from config.transcrib_suggestion_config import SUPPORTED_LANGUAGES_MAP

logger = logging.getLogger(__name__)


class TelegramHandler:
    def __init__(self, token: str, database: Database, s3_service: S3Service,
                 translation_service: TranslationService, payment_service: PaymentService):
        if not token: raise ValueError("Telegram token is required.")
        self.bot = Bot(token=token)
        self.database = database
        self.s3_service = s3_service
        self.translation_service = translation_service
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
            BotCommand("languages", "See list of supported languages"),
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
            # Сначала проверяем на YouTube ссылку
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
                    bot_user = await self.bot.get_me()
                    add_to_group_url = f"https://t.me/{bot_user.username}?startgroup=true"
                    await self.send_message(chat_id, self.ui.get_help_message(add_to_group_url))
                    return
                if command == '/languages':
                    await self._handle_languages_command(chat_id)
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

        if update.message.text:
            state = user.get('state')
            if state == 'awaiting_language_input_transcription':
                await self._handle_language_text_input(user_id, user, update.message.text, 'transcription')
            elif state == 'awaiting_language_input_translation':
                await self._handle_language_text_input(user_id, user, update.message.text, 'translation')
            else:
                await self.send_message(chat_id,
                                        "ℹ️ To get started, please send me an audio or video file, or a YouTube link.")
            return

        file_to_process = update.message.document or update.message.audio or update.message.video or update.message.voice
        if file_to_process:
            await self._handle_file(file_to_process, user_id, chat_id)

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
            if not self._queue_file_for_processing(local_file_path, user_id, chat_id):
                await self.send_message(chat_id, "❌ A server error occurred while queuing the file.")
        finally:
            if local_file_path and os.path.exists(local_file_path):
                os.remove(local_file_path)

    async def _handle_file(self, file_obj, user_id: str, chat_id: int):
        TELEGRAM_FILE_SIZE_LIMIT = 20 * 1024 * 1024
        if file_obj.file_size and file_obj.file_size > TELEGRAM_FILE_SIZE_LIMIT:
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

            if not self._queue_file_for_processing(local_file_path, user_id, chat_id):
                await self.send_message(chat_id, "❌ A server error occurred while queuing the file.")
        except Exception as e:
            logger.error(f"Error handling Telegram file: {e}", exc_info=True)
            if "File is too big" in str(e):
                await self.send_message(chat_id, "❌ Error: The file is too large to download (over 20MB).")
            else:
                await self.send_message(chat_id, "❌ An error occurred while processing your file.")
        finally:
            if local_file_path and os.path.exists(local_file_path): os.remove(local_file_path)

    def _queue_file_for_processing(self, local_file_path: str, user_id: str, chat_id: int) -> bool:
        try:
            object_key = f"{uuid.uuid4()}{os.path.splitext(local_file_path)[-1]}"
            if not self.s3_service.upload_file(local_file_path, object_key):
                logger.error("Failed to upload file to S3.")
                return False
            if self.celery_app_client:
                # Отправляем задачу в Celery
                self.celery_app_client.send_task('tasks.process_media', args=[user_id, object_key, {},
                                                                              {'platform': 'telegram',
                                                                               'chat_id': chat_id}])
                return True
            return False
        except Exception as e:
            logger.error(f"Error in _queue_file_for_processing: {e}", exc_info=True)
            return False

    # ... (остальные методы без изменений)

    async def _handle_start_command(self, user_id: str, chat_id: int, username: Optional[str]):
        user = self.database.get_user(user_id)
        if not user:
            user = self.database.create_user(user_id, username=username)
        await self.send_message(chat_id, self.ui.get_welcome_message())
        return user

    async def _handle_languages_command(self, chat_id: int):
        message_chunks = self.ui.get_languages_message_chunks()
        for chunk in message_chunks:
            await self.send_message(chat_id, chunk)
            await asyncio.sleep(0.5)

    async def _handle_status_command(self, user_id: str, chat_id: int):
        user = self.database.get_user(user_id)
        if not user:
            await self.send_message(chat_id, "Please use /start first.")
            return
        message = self.ui.get_status_message(user)
        await self.send_message(chat_id, message)

    async def _handle_confirm_command(self, command_parts: List[str], chat_id: int):
        if len(command_parts) != 3:
            await self.send_message(chat_id, "❌ Incorrect format. Use: `/confirm <user_id> <plan_name>`")
            return

        user_to_activate, plan_name = command_parts[1], command_parts[2].lower()
        if plan_name not in ['basic', 'premium']:
            await self.send_message(chat_id, f"❌ Unknown plan '{plan_name}'.")
            return

        target_user = self.database.get_user(user_to_activate)
        if not target_user:
            await self.send_message(chat_id, f"❌ User with ID `{user_to_activate}` not found.")
            return

        if target_user.get('plan') == plan_name and target_user.get('subscription_expires_at',
                                                                    datetime.now(timezone.utc)) > datetime.now(
                timezone.utc):
            await self.send_message(chat_id, f"⚠️ **Warning:** User `{user_to_activate}` is already on this plan.")
            return

        self.database.update_user_subscription(user_to_activate, plan_name)
        await self.send_message(chat_id, f"✅ User `{user_to_activate}` upgraded to *{plan_name.capitalize()}*.")

        try:
            await self.send_message(int(user_to_activate), f"🎉 Your *{plan_name.capitalize()}* plan is now active!")
        except Exception as e:
            logger.error(f"Failed to send confirmation to user {user_to_activate}: {e}")
            await self.send_message(chat_id, f"⚠️ Could not notify user {user_to_activate} directly.")

    async def _handle_check_command(self, command_parts: List[str], chat_id: int):
        if len(command_parts) != 2:
            await self.send_message(chat_id, "❌ Incorrect format. Use: `/check <user_id>`")
            return

        user_to_check = command_parts[1]
        user_data = self.database.get_user(user_to_check)
        if not user_data:
            await self.send_message(chat_id, f"❌ User with ID `{user_to_check}` not found.")
            return

        message = self.ui.get_status_message(user_data)
        await self.send_message(chat_id, f"ℹ️ *Status for user `{user_to_check}`*\n\n" + message)

    async def _handle_callback_query(self, query: Update.callback_query):
        await query.answer()
        payload = query.data
        user_id = str(query.from_user.id)
        chat_id = query.message.chat_id
        user = self.database.get_user(user_id)
        if not user: return

        if payload.startswith('RETRY_AS_'):
            lang_code = payload.replace('RETRY_AS_', '').lower()
            await self._handle_retry_request(user_id, chat_id, lang_code)
        elif payload.startswith('TRANSLATE_'):
            target_lang_code = payload.replace('TRANSLATE_', '').lower()
            await self._handle_translation_request(user_id, chat_id, target_lang_code)
        elif payload == 'CHOOSE_OTHER_LANGUAGE':
            await self.send_language_correction_options(chat_id, user)
        elif payload == 'CONFIRM_TRANSCRIPTION_OK':
            await self.send_translation_options(chat_id, user)
        elif payload == 'SHOW_PAYMENT_QR':
            payment_qr_file_id = os.getenv('PAYMENT_QR_CODE_FILE_ID')
            if payment_qr_file_id:
                await self.bot.send_photo(chat_id, photo=payment_qr_file_id,
                                          caption="Scan this QR code in your ABA app.")
            else:
                await self.send_message(chat_id, "Sorry, the QR code is temporarily unavailable.")
        elif payload == 'INPUT_OTHER_TRANSCRIPTION_LANG':
            self.database.update_user(user_id, {'state': 'awaiting_language_input_transcription'})
            await self.send_message(chat_id, "Please type the source language name or its 2-letter code.")
        elif payload == 'INPUT_OTHER_TRANSLATION_LANG':
            self.database.update_user(user_id, {'state': 'awaiting_language_input_translation'})
            await self.send_message(chat_id, "Please type the target language for translation.")

    async def send_language_correction_options(self, chat_id: int, user: Dict[str, Any]):
        reply_markup = self.ui.build_smart_buttons(user, 'transcription')
        await self.send_message(chat_id, "Got it. What was the language, actually?", reply_markup)

    async def send_translation_options(self, chat_id: int, user: Dict[str, Any]):
        reply_markup = self.ui.build_smart_buttons(user, 'translation')
        await self.send_message(chat_id, "What language would you like to translate to?", reply_markup)

    async def _handle_language_text_input(self, user_id: str, user: Dict[str, Any], text: str, context: str):
        lang_code = SUPPORTED_LANGUAGES_MAP.get(text.lower().strip())
        chat_id = int(user_id)
        if lang_code:
            self.database.update_user(user_id, {'state': None})
            self.database.increment_language_usage(user_id, lang_code, context)
            handler = self._handle_retry_request if context == 'transcription' else self._handle_translation_request
            await handler(user_id, chat_id, lang_code)
        else:
            await self.send_message(chat_id, f"Sorry, I don't recognize '{text}'. Please try again.")

    async def _handle_retry_request(self, user_id: str, chat_id: int, lang_code: str):
        last_doc = self.database.get_last_transcription(user_id)
        if not last_doc or not last_doc.get('s3_object_key'):
            await self.send_message(chat_id, "❌ Couldn't find the previous file...");
            return
        lang_name = next((l['title'] for l in DEFAULT_POPULAR_TRANSCRIPTION_LANGS if l['code'] == lang_code),
                         lang_code.upper())
        await self.send_message(chat_id, f"✅ Got it! Retrying as {lang_name}...")
        if self.celery_app_client:
            self.celery_app_client.send_task('tasks.process_media', args=[user_id, last_doc['s3_object_key'],
                                                                          {'preferred_language': lang_code},
                                                                          {'platform': 'telegram', 'chat_id': chat_id}])

    async def _handle_translation_request(self, user_id: str, chat_id: int, target_lang_code: str):
        last_doc = self.database.get_last_transcription(user_id)
        if not last_doc or not last_doc.get('transcription'):
            await self.send_message(chat_id, "❌ Nothing to translate.");
            return
        text, source_lang = last_doc['transcription'], last_doc['detected_language']
        if target_lang_code == source_lang:
            await self.send_message(chat_id, "🤔 The text is already in this language!");
            return
        res = self.translation_service.translate_text(text, target_lang_code, source_lang)
        if res.get('success'):
            await self.send_message(chat_id,
                                    f"🔄 *Translation ({target_lang_code.upper()}):*\n\n{res['translated_text']}")
        else:
            await self.send_message(chat_id, f"❌ Translation failed: {res.get('error')}")

    async def send_message(self, chat_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None):
        """Отправляет сообщение, используя встроенный клиент."""
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send message to Telegram chat {chat_id}: {e}")