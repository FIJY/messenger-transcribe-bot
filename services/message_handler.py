# services/message_handler.py
import logging
import os
import tempfile
import requests
import uuid
from typing import Dict, Any, Optional, List
from celery import Celery

# НОВЫЙ ИМПОРТ
from config.transcrib_suggestion_config import SUPPORTED_LANGUAGES_FOR_RETRY, MESSENGER_QUICK_REPLIES_LIMIT
from .database import Database
from .s3_service import S3Service
from .translation_service import TranslationService

logger = logging.getLogger(__name__)

redis_url = os.getenv('REDIS_URL')
if not redis_url:
    logger.warning("REDIS_URL не найден, Celery клиент не будет работать.")
    celery_app_client = None
else:
    celery_app_client = Celery('tasks_client', broker=redis_url)


class MessageHandler:
    def __init__(self, database: Database, translation_service: TranslationService):
        self.database = database
        self.s3_service = S3Service()
        self.translation_service = translation_service
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

            if 'message' in messaging_event:
                message = messaging_event['message']
                if 'quick_reply' in message and message['quick_reply'].get('payload'):
                    if self._handle_quick_reply(sender_id, message['quick_reply']['payload']):
                        return

                if 'text' in message and message.get('text'):
                    # Мы больше не используем диалог для исправления языка,
                    # поэтому обработка текстовых команд упрощается.
                    self._send_text_message(sender_id, "ℹ️ Чтобы начать, просто отправьте мне аудио или видео файл.")
                    return

                if 'attachments' in message:
                    self._handle_attachments(sender_id, message['attachments'], user)
                    return
        except Exception as e:
            logger.error(f"Ошибка в handle_message: {e}", exc_info=True)

    # НОВАЯ ФУНКЦИЯ для отправки кнопок
    def send_language_correction_options(self, sender_id: str):
        """
        Отправляет пользователю сообщение с кнопками для выбора правильного языка.
        """
        try:
            quick_replies = []
            for lang in SUPPORTED_LANGUAGES_FOR_RETRY[:MESSENGER_QUICK_REPLIES_LIMIT]:
                quick_replies.append({
                    "content_type": "text",
                    "title": lang['title'],
                    "payload": f"RETRY_AS_{lang['code']}"  # Новый формат payload
                })

            message_data = {
                "recipient": {"id": sender_id},
                "messaging_type": "RESPONSE",
                "message": {
                    "text": "🤔 Язык определен неверно? Выберите правильный язык ниже:",
                    "quick_replies": quick_replies
                }
            }
            self._send_api_request(message_data)
            logger.info(f"Пользователю {sender_id} отправлены кнопки для исправления языка.")

        except Exception as e:
            logger.error(f"Ошибка отправки кнопок исправления языка: {e}", exc_info=True)

    def _handle_quick_reply(self, sender_id: str, payload: str) -> bool:
        """Обрабатывает нажатия на быстрые кнопки."""
        # НОВАЯ ЛОГИКА для кнопок исправления языка
        if payload.startswith('RETRY_AS_'):
            lang_code = payload.replace('RETRY_AS_', '').lower()
            self._handle_retry_request(sender_id, lang_code)
            return True

        elif payload.startswith('TRANSLATE_'):
            target_lang_code = payload.replace('TRANSLATE_', '').lower()
            self._handle_translation_request(sender_id, target_lang_code)
            return True

        # Старый обработчик RETRY_INCORRECT_LANGUAGE больше не нужен, так как мы сразу предлагаем кнопки
        return False

    def _handle_retry_request(self, sender_id: str, lang_code: str):
        logger.info(f"Пользователь {sender_id} запросил ретрай с языком {lang_code}")
        last_doc = self.database.get_last_transcription(sender_id)
        if not last_doc or not last_doc.get('s3_object_key'):
            self._send_text_message(sender_id, "❌ Не нашел предыдущий файл для повторной обработки.")
            return

        # Находим название языка для красивого ответа
        lang_name = lang_code.upper()
        for lang in SUPPORTED_LANGUAGES_FOR_RETRY:
            if lang['code'] == lang_code:
                lang_name = lang['title']
                break

        object_key = last_doc['s3_object_key']
        user_preferences = {'preferred_language': lang_code}

        self._send_text_message(sender_id, f"✅ Принято! Повторяю обработку, думая, что это {lang_name}...")
        if celery_app_client:
            celery_app_client.send_task('tasks.process_media', args=[sender_id, object_key, user_preferences])

    def _handle_translation_request(self, sender_id: str, target_lang_code: str):
        logger.info(f"Пользователь {sender_id} запросил перевод на {target_lang_code}")
        last_doc = self.database.get_last_transcription(sender_id)
        if not last_doc or not last_doc.get('transcription'):
            self._send_text_message(sender_id, "❌ Нечего переводить.")
            return

        original_text = last_doc['transcription']
        source_lang = last_doc['detected_language']

        if target_lang_code == source_lang:
            self._send_text_message(sender_id, "🤔 Текст уже на этом языке!")
            return

        translation_result = self.translation_service.translate_text(original_text, target_lang_code, source_lang)
        if translation_result.get('success'):
            self._send_text_message(sender_id,
                                    f"🔄 **Перевод ({target_lang_code.upper()}):**\n\n{translation_result['translated_text']}")
        else:
            self._send_text_message(sender_id, f"❌ Не удалось выполнить перевод: {translation_result.get('error')}")

    def _handle_attachments(self, sender_id: str, attachments: List[Dict], user: Dict[str, Any]):
        local_file_path = None
        try:
            attachment = attachments[0]
            if attachment.get('type') not in ['audio', 'video']:
                self._send_text_message(sender_id, "Пожалуйста, отправьте аудио или видео файл.")
                return

            self._send_text_message(sender_id, "⏳ Скачиваю ваш файл...")
            local_file_path = self._download_file_locally(attachment)
            if not local_file_path:
                self._send_text_message(sender_id, "❌ Не удалось скачать файл.")
                return

            self._send_text_message(sender_id, "✔️ Файл скачан, загружаю в безопасное хранилище...")
            file_extension = os.path.splitext(local_file_path)[-1]
            object_key = f"{uuid.uuid4()}{file_extension}"
            upload_success = self.s3_service.upload_file(local_file_path, object_key)
            if not upload_success:
                self._send_text_message(sender_id, "❌ Ошибка сервера: не удалось сохранить файл.")
                return

            self._send_text_message(sender_id,
                                    "✅ Принял ваш файл в обработку. Результат пришлю, как только он будет готов.")
            user_preferences = {'preferred_language': user.get('preferred_language')}

            if celery_app_client:
                celery_app_client.send_task('tasks.process_media', args=[sender_id, object_key, user_preferences])
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
        message_data = {
            'recipient': {'id': recipient_id},
            'message': {'text': message_text}
        }
        self._send_api_request(message_data)

    def _send_api_request(self, message_data: Dict[str, Any]):
        """Централизованный метод для отправки запросов к Messenger API."""
        try:
            params = {'access_token': self.page_access_token}
            requests.post(
                "https://graph.facebook.com/v18.0/me/messages",
                params=params,
                json=message_data,
                timeout=10
            ).raise_for_status()
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения пользователю {message_data.get('recipient', {}).get('id')}: {e}")