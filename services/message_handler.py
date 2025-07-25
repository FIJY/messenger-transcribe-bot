# services/message_handler.py
import os
import logging
import tempfile
import uuid
import re
from typing import Optional
from telegram import Message, Bot
from telegram.constants import ParseMode
from celery import Celery

from .database import Database
from .telegram_ui import TelegramUI
from .localization_service import LocalizationService
from .s3_service import S3Service
from .insight_service import InsightService
from .payment_service import PaymentService

logger = logging.getLogger(__name__)

class MessageHandler:
    def __init__(self, bot: Bot, db: Database, ui: TelegramUI, localizer: LocalizationService,
                 s3: S3Service, celery: Celery, insight: InsightService, payment: PaymentService):
        self.bot = bot
        self.db = db
        self.ui = ui
        self.localizer = localizer
        self.s3_service = s3
        self.celery_app_client = celery
        self.insight_service = insight
        self.payment_service = payment

    async def handle(self, message: Message, user: dict, user_lang: str):
        user_id = str(message.from_user.id)
        chat_id = message.chat_id
        user_state = user.get('state')

        if isinstance(user_state, dict) and user_state.get('mode') == 'chatting':
            # This logic is intentionally simple for now, as most chat interactions start from a callback.
            # You can expand this if needed.
            await self.bot.send_message(chat_id, "Please use the menu to interact with the text, or use /cancel to exit chat mode.")
            return

        if message.photo and isinstance(user_state, dict) and user_state.get('mode') == 'awaiting_payment_proof':
            await self.payment_service.handle_payment_proof(message)
            return

        file_to_process = message.document or message.audio or message.video or message.voice or message.video_note
        url_match = re.search(r'https?://\S+', message.text or "")

        if file_to_process:
            await self._handle_file_upload(file_to_process, user_id, chat_id, user_lang)
        elif url_match:
            await self._handle_url(url_match.group(0), user_id, chat_id, user_lang)
        elif message.text:
            await self._handle_text_note(message.text, user_id, chat_id, user_lang)

    async def _handle_text_note(self, text: str, user_id: str, chat_id: int, lang_code: str):
        try:
            note_id = self.db.save_note(user_id=user_id, content=text, tags=['plain_text'], source_type='text')
            await self.bot.send_message(chat_id, f"✅ *Note saved:* ```{text[:250]}...```", parse_mode=ParseMode.MARKDOWN)
            message, reply_markup = self.ui.get_main_actions_menu(lang_code, note_id)
            await self.bot.send_message(chat_id, message, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error creating text note for user {user_id}: {e}")
            await self.bot.send_message(chat_id, "❌ Sorry, an error occurred while saving your note.")

    async def _handle_url(self, url: str, user_id: str, chat_id: int, lang_code: str):
        status_message = await self.bot.send_message(chat_id, self.localizer.get_string(lang_code, 'task_accepted'))
        if not status_message: return
        if self.celery_app_client:
            platform_payload = {'platform': 'telegram', 'chat_id': chat_id, 'lang_code': lang_code, 'message_id': status_message.message_id}
            self.celery_app_client.send_task('tasks.process_url', args=[user_id, url, {}, platform_payload])
        else:
            await self.bot.edit_message_text(chat_id, status_message.message_id, "❌ Server error: cannot queue URL for processing.")

    async def _handle_file_upload(self, file_obj: Message, user_id: str, chat_id: int, lang_code: str):
        status_message = await self.bot.send_message(chat_id, self.localizer.get_string(lang_code, 'file_received'))
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
            await self.bot.edit_message_text(chat_id, status_message.message_id, "❌ Failed to download file from Telegram.")

    async def _process_local_file(self, local_file_path: str, user_id: str, chat_id: int, source_type: str, lang_code: str, status_message: Message, transcription_language: Optional[str] = None):
        try:
            object_key = f"{uuid.uuid4()}{os.path.splitext(local_file_path)[-1]}"
            if not self.s3_service.upload_file(local_file_path, object_key):
                await self.bot.edit_message_text(chat_id, status_message.message_id, "❌ Server error: could not upload file to storage.")
                return
            if self.celery_app_client:
                task_kwargs = {'language': transcription_language} if transcription_language else {}
                platform_payload = {'platform': 'telegram', 'chat_id': chat_id, 'source_type': source_type, 'lang_code': lang_code, 'message_id': status_message.message_id}
                self.celery_app_client.send_task('tasks.process_media', args=[user_id, object_key, {}, platform_payload], kwargs=task_kwargs)
                await self.bot.edit_message_text(chat_id, status_message.message_id, self.localizer.get_string(lang_code, 'upload_complete'))
        except Exception as e:
            logger.error(f"Error in _process_local_file: {e}", exc_info=True)
            await self.bot.edit_message_text(chat_id, status_message.message_id, "❌ An error occurred during file processing.")
        finally:
            if local_file_path and os.path.exists(local_file_path):
                os.remove(local_file_path)
