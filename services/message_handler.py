# services/message_handler.py
import os
import logging
import tempfile
import uuid
import re
from telegram import Message, Bot
from celery import Celery

from infrastructure.database import Database
from .telegram_ui import TelegramUI
from .localization_service import LocalizationService
from .s3_service import S3Service
from .payment_service import PaymentService

logger = logging.getLogger(__name__)


class MessageHandler:
    def __init__(self, bot: Bot, db: Database, ui: TelegramUI, localizer: LocalizationService,
                 s3: S3Service, celery: Celery, payment: PaymentService):
        self.bot = bot
        self.db = db
        self.ui = ui
        self.localizer = localizer
        self.s3_service = s3
        self.celery_app_client = celery
        self.payment_service = payment

    async def handle(self, message: Message, user: dict, user_lang: str):
        logger.info("--> [MessageHandler] Starting handle.")
        file_to_process = message.document or message.audio or message.video or message.voice or message.video_note
        url_match = re.search(r'https?://\S+', message.text or "")

        if file_to_process:
            logger.info("[MessageHandler] Detected a file. Routing to _handle_file_upload.")
            await self._handle_file_upload(message, user, user_lang)
        elif url_match:
            logger.info("[MessageHandler] Detected a URL. Routing to _handle_url.")
            await self._handle_url(url_match.group(0), user, user_lang)
        else:
            logger.info("[MessageHandler] Detected a text message.")
            await self.bot.send_message(message.chat_id,
                                        "Пожалуйста, отправьте аудио/видео файл или ссылку для начала работы.")
        logger.info("--> [MessageHandler] Finished handle.")

    async def _handle_url(self, url: str, user: dict, lang_code: str):
        logger.info(f"--> [MessageHandler] Starting _handle_url for user {user['user_id']}.")
        user_id = user['user_id']
        chat_id = int(user_id)

        note_id = self.db.save_note(
            user_id=user_id,
            source_type='url',
            source_url=url,
            status='pending_selection',
            selection_state={'selected': []}
        )
        user_plan = user.get('plan', 'free')
        text, markup = self.ui.get_checkbox_selection_menu(lang_code, note_id, user_plan, [])
        await self.bot.send_message(chat_id, text, reply_markup=markup)
        logger.info(f"--> [MessageHandler] Finished _handle_url for user {user['user_id']}.")

    async def _handle_file_upload(self, message: Message, user: dict, lang_code: str):
        logger.info("--> [MessageHandler] Starting _handle_file_upload.")
        user_id = user['user_id']
        chat_id = message.chat_id
        file_obj = message.document or message.audio or message.video or message.voice or message.video_note

        logger.info(f"[MessageHandler] Sending status message to chat_id: {chat_id}")
        status_message = await self.bot.send_message(chat_id, "Анализируем ваш файл...")
        logger.info("[MessageHandler] Status message sent. Starting file download.")
        local_file_path = None
        try:
            tg_file = await file_obj.get_file()
            logger.info("[MessageHandler] Got file object from Telegram.")
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(tg_file.file_path)[-1]) as temp_f:
                local_file_path = temp_f.name
                await tg_file.download_to_drive(custom_path=local_file_path)
            logger.info(f"[MessageHandler] File downloaded to {local_file_path}. Uploading to S3.")

            s3_key = f"{uuid.uuid4()}{os.path.splitext(local_file_path)[-1]}"
            self.s3_service.upload_file(local_file_path, s3_key)
            logger.info(f"[MessageHandler] File uploaded to S3 with key: {s3_key}.")

            note_id = self.db.save_note(
                user_id=user_id,
                s3_object_key=s3_key,
                source_type='upload',
                status='pending_selection',
                selection_state={'selected': []}
            )
            logger.info(f"[MessageHandler] Note saved to DB with id: {note_id}.")

            await self.bot.delete_message(chat_id, status_message.message_id)
            logger.info("[MessageHandler] Status message deleted.")

            user_plan = user.get('plan', 'free')
            text, markup = self.ui.get_checkbox_selection_menu(lang_code, note_id, user_plan, [])
            await self.bot.send_message(chat_id, text, reply_markup=markup)
            logger.info("[MessageHandler] Checkbox menu sent.")

        except Exception as e:
            logger.error(f"Error during file pre-processing: {e}", exc_info=True)
            if status_message:
                try:
                    await self.bot.edit_message_text("❌ Произошла ошибка при подготовке файла.", chat_id=chat_id,
                                                     message_id=status_message.message_id)
                except Exception as edit_e:
                    logger.error(f"Could not edit status message: {edit_e}")
        finally:
            if local_file_path and os.path.exists(local_file_path):
                os.remove(local_file_path)
            logger.info("--> [MessageHandler] Finished _handle_file_upload.")
