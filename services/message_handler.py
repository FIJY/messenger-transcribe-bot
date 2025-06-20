# services/message_handler.py - АСИНХРОННАЯ ВЕРСИЯ
import logging
import os
import tempfile
import requests
from typing import Dict, Any, Optional, List

from celery_worker import process_media_task
from .database import Database

logger = logging.getLogger(__name__)


class MessageHandler:
    def __init__(self, database: Database):
        self.database = database
        self.page_access_token = os.getenv('PAGE_ACCESS_TOKEN')

    def handle_message(self, webhook_event: Dict[str, Any]):
        sender_id = webhook_event.get('sender', {}).get('id')
        if not sender_id: return

        user = self.database.get_user(sender_id)
        if not user:
            user = self.database.create_user(sender_id)
            self._send_text_message(sender_id, "🎉 Добро пожаловать! Отправьте аудио или видео файл для транскрипции.")
            return

        if 'message' in webhook_event and 'attachments' in webhook_event['message']:
            self._handle_attachments(sender_id, webhook_event['message']['attachments'], user)
        # Другие команды (текст, quick reply) можно добавить здесь по мере необходимости

    def _handle_attachments(self, sender_id: str, attachments: List[Dict], user: Dict[str, Any]):
        for attachment in attachments:
            if attachment.get('type') in ['audio', 'video']:
                self._process_media_attachment(sender_id, attachment, user)
                return
        self._send_text_message(sender_id, "Пожалуйста, отправьте поддерживаемый аудио или видео файл.")

    def _process_media_attachment(self, sender_id: str, attachment: Dict, user: Dict[str, Any]):
        try:
            file_path = self._download_file(attachment)
            if not file_path:
                self._send_text_message(sender_id, "❌ Не удалось скачать файл.")
                return

            self._send_text_message(sender_id,
                                    "✅ Принял ваш файл в обработку. Результат пришлю, как только он будет готов.")
            user_preferences = {'preferred_language': user.get('preferred_language')}

            process_media_task.delay(sender_id, file_path, user_preferences)
            logger.info(f"Задача для файла {file_path} от пользователя {sender_id} добавлена в очередь.")
        except Exception as e:
            logger.error(f"Ошибка при постановке задачи в очередь: {e}", exc_info=True)
            self._send_text_message(sender_id, "❌ Произошла ошибка при отправке файла на обработку.")

    def _download_file(self, attachment: Dict) -> Optional[str]:
        try:
            file_url = attachment.get('payload', {}).get('url')
            if not file_url: return None
            headers = {'Authorization': f'Bearer {self.page_access_token}'}
            response = requests.get(file_url, headers=headers, stream=True, timeout=60)
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as temp_file:
                temp_file_path = temp_file.name
                for chunk in response.iter_content(chunk_size=8192):
                    temp_file.write(chunk)
            return temp_file_path
        except Exception as e:
            logger.error(f"Ошибка при скачивании файла: {e}", exc_info=True)
            return None

    def _send_text_message(self, recipient_id: str, message_text: str):
        try:
            payload = {'recipient': {'id': recipient_id}, 'message': {'text': message_text},
                       'access_token': self.page_access_token}
            requests.post("https://graph.facebook.com/v18.0/me/messages", json=payload, timeout=10).raise_for_status()
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения пользователю {recipient_id}: {e}")