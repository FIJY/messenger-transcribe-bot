# services/message_handler.py
import logging
import os
import requests
from typing import Dict, Any, List, Optional
from celery import Celery

from .database import Database

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
                self._send_text_message(sender_id,
                                        "🎉 Добро пожаловать! Отправьте аудио или видео файл для транскрипции.")
                return

            if 'message' in messaging_event and 'attachments' in messaging_event['message']:
                self._handle_attachments(sender_id, messaging_event['message']['attachments'], user)
        except Exception as e:
            logger.error(f"Ошибка в handle_message: {e}", exc_info=True)

    def _handle_attachments(self, sender_id: str, attachments: List[Dict], user: Dict[str, Any]):
        for attachment in attachments:
            if attachment.get('type') in ['audio', 'video']:
                file_url = attachment.get('payload', {}).get('url')
                if file_url:
                    self._send_text_message(sender_id,
                                            "✅ Принял ваш файл в обработку. Результат пришлю, как только он будет готов.")
                    user_preferences = {'preferred_language': user.get('preferred_language')}

                    if celery_app_client:
                        # Передаем не путь к файлу, а сам URL
                        celery_app_client.send_task('tasks.process_media', args=[sender_id, file_url, user_preferences])
                        logger.info(f"Задача для URL {file_url} от {sender_id} добавлена в очередь.")
                    else:
                        logger.error("Celery клиент не инициализирован.")
                        self._send_text_message(sender_id, "❌ Ошибка сервера: не удалось поставить задачу в очередь.")
                else:
                    self._send_text_message(sender_id, "❌ Не удалось получить ссылку на файл.")
                return  # Обрабатываем только первое вложение
        self._send_text_message(sender_id, "Пожалуйста, отправьте поддерживаемый аудио или видео файл.")

    def _send_text_message(self, recipient_id: str, message_text: str):
        try:
            payload = {'recipient': {'id': recipient_id}, 'message': {'text': message_text},
                       'access_token': self.page_access_token}
            requests.post("https://graph.facebook.com/v18.0/me/messages", json=payload, timeout=10).raise_for_status()
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения пользователю {recipient_id}: {e}")