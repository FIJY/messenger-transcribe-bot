# services/message_handler.py - ФИНАЛЬНАЯ ВЕРСИЯ С httpx
import logging
import os
import tempfile
import httpx  # 🔧 ИЗМЕНЕНИЕ: Используем httpx вместо requests
import uuid
from typing import Dict, Any, Optional, List
from celery import Celery
from urllib.parse import quote

from .database import Database

logger = logging.getLogger(__name__)

SHARED_DISK_PATH = "/var/data/shared_files"

redis_url = os.getenv('REDIS_URL')
if not redis_url:
    logger.warning("REDIS_URL не найден, Celery клиент не будет работать.")
    celery_app_client = None
else:
    celery_app_client = Celery('tasks_client', broker=redis_url)


class MessageHandler:
    def __init__(self, database: Database):
        self.database = database
        self.page_access_token = os.getenv('PAGE_ACCESS_TOKEN')
        if not os.path.exists(SHARED_DISK_PATH):
            logger.error(f"КРИТИЧЕСКАЯ ОШИБКА: Общий диск не найден по пути {SHARED_DISK_PATH}.")

    def handle_message(self, webhook_event: Dict[str, Any]):
        entry = webhook_event.get('entry', [])
        if not entry: return
        messaging = entry[0].get('messaging', [])
        if not messaging: return
        messaging_event = messaging[0]
        sender_id = messaging_event.get('sender', {}).get('id')
        if not sender_id: return

        user = self.database.get_user(sender_id)
        if not user:
            user = self.database.create_user(sender_id)
            self._send_text_message(sender_id, "🎉 Добро пожаловать! Отправьте аудио или видео файл для транскрипции.")
            return

        if 'message' in messaging_event and 'attachments' in messaging_event['message']:
            self._handle_attachments(sender_id, messaging_event['message']['attachments'], user)

    def _handle_attachments(self, sender_id: str, attachments: List[Dict], user: Dict[str, Any]):
        for attachment in attachments:
            if attachment.get('type') in ['audio', 'video']:
                self._process_media_attachment(sender_id, attachment, user)
                return
        self._send_text_message(sender_id, "Пожалуйста, отправьте поддерживаемый аудио или видео файл.")

    def _process_media_attachment(self, sender_id: str, attachment: Dict, user: Dict[str, Any]):
        try:
            if not os.path.exists(SHARED_DISK_PATH):
                logger.error(f"Невозможно обработать вложение, так как путь {SHARED_DISK_PATH} не существует.")
                self._send_text_message(sender_id, "❌ Ошибка сервера: хранилище файлов недоступно.")
                return

            file_path = self._download_file(attachment)
            if not file_path:
                self._send_text_message(sender_id, "❌ Не удалось скачать файл.")
                return

            self._send_text_message(sender_id,
                                    "✅ Принял ваш файл в обработку. Результат пришлю, как только он будет готов.")
            user_preferences = {'preferred_language': user.get('preferred_language')}

            if celery_app_client:
                celery_app_client.send_task('tasks.process_media', args=[sender_id, file_path, user_preferences])
                logger.info(f"Задача для файла {file_path} от пользователя {sender_id} добавлена в очередь.")
            else:
                logger.error("Celery клиент не инициализирован. Задача не может быть отправлена.")
                self._send_text_message(sender_id, "❌ Ошибка сервера: не удалось поставить задачу в очередь.")
        except Exception as e:
            logger.error(f"Ошибка при постановке задачи в очередь: {e}", exc_info=True)
            self._send_text_message(sender_id, "❌ Произошла ошибка при отправке файла на обработку.")

    def _download_file(self, attachment: Dict) -> Optional[str]:
        """Скачивает и сохраняет файл на общий диск, используя httpx."""
        try:
            file_url = attachment.get('payload', {}).get('url')
            if not file_url: return None

            headers = {'Authorization': f'Bearer {self.page_access_token}'}

            # 🔧 ИСПОЛЬЗУЕМ HTTpx ВМЕСТО REQUESTS
            with httpx.stream("GET", file_url, headers=headers, timeout=60) as response:
                response.raise_for_status()

                file_extension = os.path.splitext(file_url.split('?')[0])[-1] or '.tmp'
                unique_filename = f"{uuid.uuid4()}{file_extension}"
                file_path = os.path.join(SHARED_DISK_PATH, unique_filename)

                with open(file_path, 'wb') as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)

            logger.info(f"Файл сохранен на общий диск через httpx: {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"Ошибка при скачивании файла на диск через httpx: {e}", exc_info=True)
            return None

    def _send_text_message(self, recipient_id: str, message_text: str):
        """Отправляет текстовое сообщение пользователю, используя httpx."""
        try:
            headers = {'Content-Type': 'application/json'}
            params = {'access_token': self.page_access_token}
            json_data = {
                'recipient': {'id': recipient_id},
                'message': {'text': message_text}
            }
            # 🔧 ИСПОЛЬЗУЕМ HTTpx ВМЕСТО REQUESTS
            response = httpx.post(
                "https://graph.facebook.com/v18.0/me/messages",
                headers=headers,
                params=params,
                json=json_data,
                timeout=10
            )
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения пользователю {recipient_id} через httpx: {e}")