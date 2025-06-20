# celery_worker.py
import os
import logging
import requests
import tempfile
from typing import Optional

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Импорты ваших сервисов
from services.media_handler import MediaHandler
from services.transcription_service import TranscriptionService
from services.translation_service import TranslationService
from services.database import Database
from services.audio_processor import AudioProcessor

redis_url = os.getenv('REDIS_URL')
if not redis_url:
    raise RuntimeError("REDIS_URL не установлен!")

celery_app = Celery('tasks', broker=redis_url, backend=redis_url, include=['celery_worker'])

try:
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

def send_messenger_message(recipient_id: str, message_text: str):
    if not PAGE_ACCESS_TOKEN:
        logger.error("PAGE_ACCESS_TOKEN не найден.")
        return
    try:
        payload = {
            'recipient': {'id': recipient_id},
            'messaging_type': 'MESSAGE_TAG',
            'message': {'text': message_text},
            'tag': 'POST_PURCHASE_UPDATE',
            'access_token': PAGE_ACCESS_TOKEN
        }
        requests.post("https://graph.facebook.com/v18.0/me/messages", json=payload, timeout=10).raise_for_status()
    except Exception as e:
        logger.error(f"Воркер не смог отправить сообщение: {e}", exc_info=True)

def _download_file_from_url(file_url: str) -> Optional[str]:
    """Скачивает файл по URL и сохраняет его во временный файл."""
    try:
        # Здесь мы не используем httpx, так как проблема была в другом
        with requests.get(file_url, stream=True, timeout=60) as response:
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as temp_f:
                for chunk in response.iter_content(chunk_size=8192):
                    temp_f.write(chunk)
                logger.info(f"Файл успешно скачан во временный файл: {temp_f.name}")
                return temp_f.name
    except Exception as e:
        logger.error(f"Воркер не смог скачать файл по URL {file_url}: {e}", exc_info=True)
        return None

@celery_app.task(bind=True, name='tasks.process_media', max_retries=2, default_retry_delay=60)
def process_media_task(self, sender_id: str, file_url: str, user_preferences: dict):
    logger.info(f"[{self.request.id}] Начало задачи для {sender_id}, URL: {file_url}")
    if not media_handler:
        send_messenger_message(sender_id, "❌ Ошибка сервера: обработчик не инициализирован.")
        return

    local_file_path = _download_file_from_url(file_url)
    if not local_file_path:
        send_messenger_message(sender_id, "❌ Не удалось скачать ваш файл для обработки.")
        return

    result = None
    try:
        result = media_handler.process_media(local_file_path, user_preferences)
        if result.get('success'):
            lang_info = result.get('language_info', {})
            lang_name = lang_info.get('name', result.get('detected_language', ''))
            response_text = f"🎯 Язык: {lang_name}\n\n📝 Транскрипция:\n{result['transcription']}"
            send_messenger_message(sender_id, response_text)
            database.save_transcription(user_id=sender_id, **result)
            database.increment_usage(user_id=sender_id)
        else:
            send_messenger_message(sender_id, f"❌ Не удалось обработать ваш файл. Ошибка: {result.get('error', 'неизвестно')}")
    except Exception as exc:
        logger.error(f"[{self.request.id}] Критическая ошибка в задаче Celery: {exc}", exc_info=True)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            send_messenger_message(sender_id, "❌ Не удалось обработать ваш файл после нескольких попыток.")
    finally:
        # local_file_path - это файл, который скачал этот воркер
        # result['processed_audio_path'] - это файл .wav, который создал audio_processor
        if os.path.exists(local_file_path):
            os.remove(local_file_path)
            logger.info(f"[{self.request.id}] Временный файл скачивания удален: {local_file_path}")
        if result and result.get('processed_audio_path') and os.path.exists(result['processed_audio_path']):
            if result.get('processed_audio_path') != local_file_path:
                 os.remove(result.get('processed_audio_path'))
                 logger.info(f"[{self.request.id}] Обработанный временный файл удален.")