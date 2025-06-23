# celery_worker.py
import os
import logging
import requests
import tempfile
from celery import Celery
from dotenv import load_dotenv
from typing import Optional, Dict, Any
import openai  # <== НОВЫЙ ИМПОРТ

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from services.media_handler import MediaHandler
from services.transcription_service import TranscriptionService
from services.translation_service import TranslationService
from services.database import Database
from services.audio_processor import AudioProcessor
from services.s3_service import S3Service
from services.message_handler import MessageHandler

redis_url = os.getenv('REDIS_URL')
if not redis_url: raise RuntimeError("REDIS_URL is not set!")
celery_app = Celery('tasks', broker=redis_url, backend=redis_url, include=['celery_worker'])

try:
    s3_service = S3Service()
    database = Database()
    audio_processor = AudioProcessor()
    transcription_service = TranscriptionService()
    translation_service = TranslationService()
    message_handler = MessageHandler(database=database, translation_service=translation_service)
    media_handler_service = MediaHandler(transcription_service, translation_service)
    PAGE_ACCESS_TOKEN = os.getenv('PAGE_ACCESS_TOKEN')
    logger.info("Celery worker: All services initialized successfully.")
except Exception as e:
    logger.error(f"Celery worker: CRITICAL INITIALIZATION ERROR: {e}", exc_info=True)
    media_handler_service = None;
    message_handler = None


def _send_celery_message(recipient_id: str, message_data: Dict[str, Any]):
    if not PAGE_ACCESS_TOKEN:
        logger.error("PAGE_ACCESS_TOKEN not found.");
        return
    try:
        payload = {'recipient': {'id': recipient_id}, 'messaging_type': 'RESPONSE', 'message': message_data,
                   'access_token': PAGE_ACCESS_TOKEN}
        requests.post("https://graph.facebook.com/v18.0/me/messages", json=payload, timeout=10).raise_for_status()
    except Exception as e:
        logger.error(f"Worker could not send message: {e}", exc_info=True)


def _download_file_from_r2(object_key: str) -> Optional[str]:
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{object_key.split('.')[-1]}") as f:
            if s3_service.download_file(object_key, f.name): return f.name
            os.remove(f.name);
            return None
    except Exception as e:
        logger.error(f"Error downloading file from R2 in worker: {e}", exc_info=True);
        return None


@celery_app.task(bind=True, name='tasks.process_media', max_retries=2, default_retry_delay=60)
def process_media_task(self, sender_id: str, object_key: str, user_preferences: dict):
    if not all([media_handler_service, message_handler]):
        _send_celery_message(sender_id, {'text': "❌ Server error: handler not initialized."});
        return

    local_file_path = _download_file_from_r2(object_key)
    if not local_file_path:
        _send_celery_message(sender_id, {'text': "❌ Server error: could not retrieve file from storage."});
        return

    is_retry = bool(user_preferences.get('preferred_language'))
    result = None
    processed_audio_for_debug = None

    try:
        result = media_handler_service.process_media(local_file_path, user_preferences)
        # Сохраняем путь к обработанному аудио для возможной отладки
        processed_audio_for_debug = result.get('processed_audio_path')

        if result.get('success'):
            lang_info = result.get('language_info', {})
            lang_name = lang_info.get('name', 'N/A')
            response_text = f"📝 **Transcription ({lang_name}):**\n\n{result['transcription']}"
            _send_celery_message(sender_id, {'text': response_text})

            if is_retry:
                message_handler.send_translation_options(sender_id)
            else:
                quick_replies = [
                    {"content_type": "text", "title": "✅ Looks Good", "payload": "CONFIRM_TRANSCRIPTION_OK"},
                    {"content_type": "text", "title": "🗣️ Other language", "payload": "CHOOSE_OTHER_LANGUAGE"}
                ]
                _send_celery_message(sender_id, {'text': "Is the language and transcription correct?",
                                                 'quick_replies': quick_replies})

            database.save_transcription(user_id=sender_id, object_key=object_key, **result)
            if not is_retry: database.increment_usage(user_id=sender_id)
        else:
            raise result.get('error', Exception('Unknown error during media processing'))

    # ===> НОВЫЙ БЛОК ОБРАБОТКИ ОШИБОК <===
    except openai.BadRequestError as e:
        # Ловим конкретно нашу ошибку от OpenAI
        error_str = str(e).lower()
        if 'language' in error_str and 'not supported' in error_str:
            logger.warning(f"Перехвачена ошибка 'Language not supported'. Сохраняем аудио для отладки.")
            # Сохраняем проблемный файл в R2
            if processed_audio_for_debug and os.path.exists(processed_audio_for_debug):
                debug_filename = f"debug/{os.path.basename(processed_audio_for_debug)}"
                s3_service.upload_file(processed_audio_for_debug, debug_filename)
                _send_celery_message(sender_id, {
                    'text': f"Обнаружена специфическая ошибка API. Отладочный файл сохранен как: {debug_filename}"})
            else:
                _send_celery_message(sender_id, {
                    'text': "Обнаружена специфическая ошибка API, но не удалось сохранить отладочный файл."})
        else:
            # Другие ошибки от OpenAI
            _send_celery_message(sender_id, {'text': f"❌ API Error: {e}"})

    except Exception as exc:
        logger.error(f"[{self.request.id}] Критическая ошибка в задаче Celery: {exc}", exc_info=True)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            _send_celery_message(sender_id, {'text': "❌ Failed to process your file after multiple attempts."})

    finally:
        if local_file_path: audio_processor.cleanup_temp_file(local_file_path)
        # Не удаляем отладочный файл, если он еще нужен
        if processed_audio_for_debug and os.path.exists(processed_audio_for_debug):
            audio_processor.cleanup_temp_file(processed_audio_for_debug)
        logger.info(f"[{self.request.id}] Task finished for object {object_key}.")