# services/telegram_handler.py
import os
import logging
import tempfile
import httpx  # Используем httpx вместо requests для асинхронных запросов
import uuid
from telegram import Update

from .database import Database
from .s3_service import S3Service
from .celery_client import get_celery_app_client

logger = logging.getLogger(__name__)


class TelegramHandler:
    def __init__(self, token: str, database: Database, s3_service: S3Service):
        if not token:
            raise ValueError("Telegram token is required.")
        self.token = token
        self.database = database
        self.s3_service = s3_service
        self.celery_app_client = get_celery_app_client()

    # ==> СДЕЛАНО АСИНХРОННЫМ
    async def handle_update(self, update_data: dict):
        """Главный метод, который парсит входящие данные от Telegram."""
        update = Update.de_json(update_data, bot=None)

        if not update.message or not update.message.from_user:
            logger.warning("Received an update without a message or user.")
            return

        user_id = update.message.from_user.id
        chat_id = update.message.chat_id

        user = self.database.get_user(str(user_id))
        if not user:
            self.database.create_user(str(user_id))
            await self.send_message(chat_id, "🎉 Welcome! Send me an audio, video, or voice message to start.")

        file_to_process = update.message.document or update.message.audio or update.message.video or update.message.voice
        if file_to_process:
            await self._handle_file(file_to_process, user_id, chat_id)
        elif update.message.text:
            await self.send_message(chat_id, "ℹ️ To get started, please send me an audio, video, or voice message.")

    # ==> СДЕЛАНО АСИНХРОННЫМ
    async def _handle_file(self, file_obj, user_id: int, chat_id: int):
        """Обрабатывает любой тип файла (аудио, видео, документ)."""
        await self.send_message(chat_id, "✅ File received. Processing...")
        local_file_path = None
        try:
            # ===> ГЛАВНОЕ ИСПРАВЛЕНИЕ: ДОБАВЛЕНО 'await' <===
            tg_file = await file_obj.get_file()

            original_filename = file_obj.file_name if hasattr(file_obj, 'file_name') and file_obj.file_name else ''
            file_extension = os.path.splitext(original_filename)[-1] if original_filename else '.tmp'

            async with httpx.AsyncClient() as client:
                response = await client.get(tg_file.file_path, timeout=60)
                response.raise_for_status()
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_f:
                    local_file_path = temp_f.name
                    temp_f.write(response.content)

            object_key = f"{uuid.uuid4()}{file_extension}"
            if not self.s3_service.upload_file(local_file_path, object_key):
                await self.send_message(chat_id, "❌ Server error: could not save the file.")
                return

            if self.celery_app_client:
                task_payload = {'platform': 'telegram', 'chat_id': chat_id}
                self.celery_app_client.send_task(
                    'tasks.process_media',
                    args=[str(user_id), object_key, {}, task_payload]
                )

        except Exception as e:
            logger.error(f"Error handling Telegram file: {e}", exc_info=True)
            await self.send_message(chat_id, "❌ An error occurred while processing your file.")
        finally:
            if local_file_path and os.path.exists(local_file_path):
                os.remove(local_file_path)

    # ==> СДЕЛАНО АСИНХРОННЫМ
    async def send_message(self, chat_id: int, text: str):
        """Отправляет текстовое сообщение пользователю в Telegram."""
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'}
        try:
            async with httpx.AsyncClient() as client:
                await client.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"Failed to send message to Telegram chat {chat_id}: {e}")