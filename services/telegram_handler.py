# services/telegram_handler.py
import os
import logging
import tempfile
from telegram import Update
from telegram.ext import CallbackContext
import requests
import uuid

# Эти сервисы мы импортируем из нашего существующего кода
from .database import Database
from .s3_service import S3Service
from .celery_client import get_celery_app_client  # Мы создадим этот файл для удобства

logger = logging.getLogger(__name__)


class TelegramHandler:
    def __init__(self, token: str, database: Database, s3_service: S3Service):
        if not token:
            raise ValueError("Telegram token is required.")
        self.token = token
        self.database = database
        self.s3_service = s3_service
        self.celery_app_client = get_celery_app_client()

    def handle_update(self, update_data: dict):
        """Главный метод, который парсит входящие данные от Telegram."""
        update = Update.de_json(update_data, bot=None)

        if not update.message or not update.message.from_user:
            logger.warning("Received an update without a message or user.")
            return

        user_id = update.message.from_user.id
        chat_id = update.message.chat_id

        # Проверяем, есть ли пользователь в базе, если нет - создаем
        user = self.database.get_user(str(user_id))
        if not user:
            self.database.create_user(str(user_id))
            self.send_message(chat_id, "🎉 Welcome! Send me an audio, video, or voice message to start.")

        # Обрабатываем разные типы вложений
        if update.message.document:
            self._handle_file(update.message.document, user_id, chat_id, is_document=True)
        elif update.message.audio:
            self._handle_file(update.message.audio, user_id, chat_id)
        elif update.message.video:
            self._handle_file(update.message.video, user_id, chat_id)
        elif update.message.voice:
            self._handle_file(update.message.voice, user_id, chat_id)
        elif update.message.text:
            self.send_message(chat_id, "ℹ️ To get started, please send me an audio, video, or voice message.")

    def _handle_file(self, file_obj, user_id: int, chat_id: int, is_document: bool = False):
        """Обрабатывает любой тип файла (аудио, видео, документ)."""
        self.send_message(chat_id, "✅ File received. Processing...")
        local_file_path = None
        try:
            # Скачиваем файл с серверов Telegram
            tg_file = file_obj.get_file()
            file_url = tg_file.file_path

            # Определяем расширение
            original_filename = file_obj.file_name if hasattr(file_obj, 'file_name') and file_obj.file_name else ''
            file_extension = os.path.splitext(original_filename)[-1] if original_filename else '.tmp'

            with requests.get(file_url, stream=True) as r:
                r.raise_for_status()
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_f:
                    local_file_path = temp_f.name
                    for chunk in r.iter_content(chunk_size=8192):
                        temp_f.write(chunk)

            # Загружаем в наше S3/R2 хранилище
            object_key = f"{uuid.uuid4()}{file_extension}"
            if not self.s3_service.upload_file(local_file_path, object_key):
                self.send_message(chat_id, "❌ Server error: could not save the file.")
                return

            # Отправляем задачу в Celery (используем тот же самый таск)
            if self.celery_app_client:
                # Указываем платформу, чтобы воркер знал, куда отправлять ответ
                task_payload = {'platform': 'telegram', 'chat_id': chat_id}
                self.celery_app_client.send_task(
                    'tasks.process_media',
                    args=[str(user_id), object_key, {}, task_payload]
                )

        except Exception as e:
            logger.error(f"Error handling Telegram file: {e}", exc_info=True)
            self.send_message(chat_id, "❌ An error occurred while processing your file.")
        finally:
            if local_file_path and os.path.exists(local_file_path):
                os.remove(local_file_path)

    def send_message(self, chat_id: int, text: str):
        """Отправляет текстовое сообщение пользователю в Telegram."""
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'Markdown'
        }
        try:
            requests.post(url, json=payload, timeout=10).raise_for_status()
        except Exception as e:
            logger.error(f"Failed to send message to Telegram chat {chat_id}: {e}")