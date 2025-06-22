# celery_worker.py
import os
import logging
import requests
import tempfile
from celery import Celery
from dotenv import load_dotenv
from typing import Optional, List, Dict, Any

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Импорты ваших сервисов
from services.media_handler import MediaHandler
from services.transcription_service import TranscriptionService
from services.translation_service import TranslationService
from services.database import Database
from services.audio_processor import AudioProcessor
from services.s3_service import S3Service

redis_url = os.getenv('REDIS_URL')
if not redis_url: raise RuntimeError("REDIS_URL не установлен!")
celery_app = Celery('tasks', broker=redis_url, backend=redis_url, include=['celery_worker'])

try:
    s3_service = S3Service()
    transcription_service = TranscriptionService()
    translation_service = TranslationService()
    database = Database()
    media_handler = MediaHandler(transcription_service, translation_service)
    audio_processor = AudioProcessor()
    PAGE_ACCESS_TOKEN = os.getenv('PAGE_ACCESS_TOKEN')
    logger.info("Celery воркер: Все сервисы успешно инициализированы.")
except Exception as e:
    logger.error(f"Celery воркер: КРИТИЧЕСКАЯ ОШИБКА ИНИЦИАЛИЗАЦИИ: {e}", exc_info=True)
    media_handler = None


def _send_celery_message(recipient_id: str, message_data: Dict[str, Any]):
    """Централизованный метод отправки сообщений от воркера."""
    if not PAGE_ACCESS_TOKEN:
        logger.error("PAGE_ACCESS_TOKEN не найден.")
        return
    try:
        payload = {
            'recipient': {'id': recipient_id},
            'messaging_type': 'MESSAGE_TAG',
            'message': message_data,
            'tag': 'POST_PURCHASE_UPDATE',
            'access_token': PAGE_ACCESS_TOKEN
        }
        requests.post("https://graph.facebook.com/v18.0/me/messages", json=payload, timeout=10).raise_for_status()
        logger.info(f"Воркер успешно отправил сообщение пользователю {recipient_id}")
    except Exception as e:
        logger.error(f"Воркер не смог отправить сообщение: {e}", exc_info=True)


@celery_app.task(bind=True, name='tasks.process_media', max_retries=2, default_retry_delay=60)
def process_media_task(self, sender_id: str, object_key: str, user_preferences: dict):
    logger.info(f"[{self.request.id}] Начало задачи для {sender_id}, ключ объекта в R2: {object_key}")
    if not all([media_handler, s3_service]):
        _send_celery_message(sender_id, {'text': "❌ Ошибка сервера: обработчик не инициализирован."})
        return

    # Создаем временный файл, куда скачаем содержимое из R2
    with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as temp_f:
        local_file_path = temp_f.name

    result = None
    try:
        download_success = s3_service.download_file(object_key, local_file_path)
        if not download_success:
            _send_celery_message(sender_id, {'text': "❌ Ошибка сервера: не удалось получить файл из хранилища."})
            return

        result = media_handler.process_media(local_file_path, user_preferences)
        if result.get('success'):
            lang_info = result.get('language_info', {})
            lang_name = lang_info.get('name', result.get('detected_language', ''))
            response_text = f"🎯 Язык: {lang_name}\n\n📝 Транскрипция:\n{result['transcription']}"

            # Формируем кнопки и отправляем
            quick_replies = [
                {"content_type": "text", "title": "Перевести на English", "payload": "TRANSLATE_EN"},
                {"content_type": "text", "title": "Перевести на Русский", "payload": "TRANSLATE_RU"}
            ]
            message_data = {'text': response_text, 'quick_replies': quick_replies}
            _send_celery_message(sender_id, message_data)

            # Сохраняем в базу ключ от R2
            database.save_transcription(
                user_id=sender_id,
                transcription=result['transcription'],
                detected_language=result['detected_language'],
                object_key=object_key,
                quality_analysis=result.get('quality_analysis', {})
            )
            database.increment_usage(user_id=sender_id)
        else:
            _send_celery_message(sender_id, {
                'text': f"❌ Не удалось обработать ваш файл. Ошибка: {result.get('error', 'неизвестно')}"})
    except Exception as exc:
        logger.error(f"[{self.request.id}] Критическая ошибка в задаче Celery: {exc}", exc_info=True)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            _send_celery_message(sender_id, {'text': "❌ Не удалось обработать ваш файл после нескольких попыток."})
    finally:
        # 🔧 ИЗМЕНЕНИЕ: НЕ УДАЛЯЕМ файл из R2, только локальные копии
        audio_processor.cleanup_temp_file(local_file_path)
        if result and result.get('processed_audio_path'):
            audio_processor.cleanup_temp_file(result.get('processed_audio_path'))
        logger.info(f"[{self.request.id}] Временные локальные файлы удалены. Объект в R2 сохранен для ретраев.")