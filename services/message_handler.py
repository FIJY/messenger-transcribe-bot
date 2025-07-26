# services/message_handler.py
import os
import logging
import tempfile
import uuid
import re
from telegram import Message, Bot
from celery import Celery

from .database import Database
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
        file_to_process = message.document or message.audio or message.video or message.voice or message.video_note
        url_match = re.search(r'https?://\S+', message.text or "")

        if file_to_process:
            await self._handle_file_upload(file_to_process, user, user_lang)
        elif url_match:
            await self._handle_url(url_match.group(0), user, user_lang)
        else:
            await self.bot.send_message(message.chat_id,
                                        "Пожалуйста, отправьте аудио/видео файл или ссылку для начала работы.")

    async def _handle_url(self, url: str, user: dict, lang_code: str):
        # ИСПРАВЛЕНО: Используем правильное поле 'user_id' вместо '_id'
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

    async def _handle_file_upload(self, file_obj: Message, user: dict, lang_code: str):
        # ИСПРАВЛЕНО: Используем правильное поле 'user_id' вместо '_id'
        user_id = user['user_id']
        chat_id = file_obj.chat_id

        status_message = await self.bot.send_message(chat_id, "Анализируем ваш файл...")
        local_file_path = None
        try:
            tg_file = await file_obj.get_file()
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(tg_file.file_path)[-1]) as temp_f:
                local_file_path = temp_f.name
                await tg_file.download_to_drive(custom_path=local_file_path)

            s3_key = f"{uuid.uuid4()}{os.path.splitext(local_file_path)[-1]}"
            self.s3_service.upload_file(local_file_path, s3_key)

            note_id = self.db.save_note(
                user_id=user_id,
                s3_object_key=s3_key,
                source_type='upload',
                status='pending_selection',
                selection_state={'selected': []}
            )

            await self.bot.delete_message(chat_id, status_message.message_id)

            user_plan = user.get('plan', 'free')
            text, markup = self.ui.get_checkbox_selection_menu(lang_code, note_id, user_plan, [])
            await self.bot.send_message(chat_id, text, reply_markup=markup)

        except Exception as e:
            logger.error(f"Error during file pre-processing: {e}", exc_info=True)
            if status_message:
                await self.bot.edit_message_text(chat_id, status_message.message_id,
                                                 "❌ Произошла ошибка при подготовке файла.")
        finally:
            if local_file_path and os.path.exists(local_file_path):
                os.remove(local_file_path)
