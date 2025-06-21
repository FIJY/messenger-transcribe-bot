# services/message_handler.py
import logging
import os
import tempfile
import requests
import uuid
from typing import Dict, Any, Optional, List
from celery import Celery

from .database import Database
from .s3_service import S3Service

logger = logging.getLogger(__name__)

redis_url = os.getenv('REDIS_URL')
if not redis_url:
    logger.warning("REDIS_URL не найден, Celery клиент не будет работать.")
    celery_app_client = None
else:
    celery_app_client = Celery('tasks_client', broker=redis_url)


class MessageHandler:
    def __init__(self, database: Database):
        self.database = database
        self.s3_service = S3Service()
        self.page_access_token = os.getenv('PAGE_ACCESS_TOKEN')

    def handle_message(self, webhook_event: Dict[str, Any]):
        try:
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
                self._send_text_message(sender_id, "🎉 Добро пожаловать! Отправьте аудио или видео файл.")
                return
            if 'message' in messaging_event and 'attachments' in messaging_event['message']:
                self._handle_attachments(sender_id, messaging_event['message']['attachments'], user)
        except Exception as e:
            logger.error(f"Ошибка в handle_message: {e}", exc_info=True)

    def _handle_attachments(self, sender_id: str, attachments: List[Dict], user: Dict[str, Any]):
        for attachment in attachments:
            if attachment.get('type') in ['audio', 'video']:
                self._process_media_attachment(sender_id, attachment, user)
                return
        self._send_text_message(sender_id, "Пожалуйста, отправьте поддерживаемый аудио или видео файл.")

    def _process_media_attachment(self, sender_id: str, attachment: Dict, user: Dict[str, Any]):
        local_file_path = None
        try:
            local_file_path = self._download_file_locally(attachment)
            if not local_file_path:
                self._send_text_message(sender_id, "❌ Не удалось скачать файл.")
                return

            file_extension = os.path.splitext(local_file_path)[-1]
            object_key = f"{uuid.uuid4()}{file_extension}"

            upload_success = self.s3_service.upload_file(local_file_path, object_key)
            if not upload_success:
                self._send_text_message(sender_id, "❌ Ошибка сервера: не удалось сохранить файл в хранилище.")
                return

            self._send_text_message(sender_id,
                                    "✅ Принял ваш файл в обработку. Результат пришлю, как только он будет готов.")
            user_preferences = {'preferred_language': user.get('preferred_language')}

            if celery_app_client:
                celery_app_client.send_task('tasks.process_media', args=[sender_id, object_key, user_preferences])
                logger.info(f"Задача для ключа {object_key} от {sender_id} добавлена в очередь.")
            else:
                logger.error("Celery клиент не инициализирован.")
        except Exception as e:
            logger.error(f"Ошибка при постановке задачи в очередь: {e}", exc_info=True)
        finally:
            if local_file_path and os.path.exists(local_file_path):
                os.remove(local_file_path)

    def _download_file_locally(self, attachment: Dict) -> Optional[str]:
        try:
            file_url = attachment.get('payload', {}).get('url')
            if not file_url: return None
            with requests.get(file_url, stream=True, timeout=60) as response:
                response.raise_for_status()
                with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as temp_f:
                    for chunk in response.iter_content(chunk_size=8192):
                        temp_f.write(chunk)
                    return temp_f.name
        except Exception as e:
            logger.error(f"Ошибка при локальном скачивании файла: {e}", exc_info=True)
            return None

    def _send_text_message(self, recipient_id: str, message_text: str):
        try:
            payload = {'recipient': {'id': recipient_id}, 'message': {'text': message_text},
                       'access_token': self.page_access_token}
            requests.post("https://graph.facebook.com/v18.0/me/messages", json=payload, timeout=10).raise_for_status()
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения пользователю {recipient_id}: {e}")