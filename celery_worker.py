# celery_worker.py
import os
import logging
import requests
import tempfile
import asyncio
import redis  # <== НОВЫЙ ИМПОРТ
from celery import Celery
from celery.schedules import crontab  # <== НОВЫЙ ИМПОРТ
from dotenv import load_dotenv
from typing import Optional, Dict, Any
import openai
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# ... (импорты ваших сервисов без изменений) ...
from services.media_handler import MediaHandler
from services.transcription_service import TranscriptionService
from services.translation_service import TranslationService
from services.database import Database
from services.audio_processor import AudioProcessor
from services.s3_service import S3Service
from services.message_handler import MessageHandler
from services.telegram_handler import TelegramHandler

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

redis_url = os.getenv('REDIS_URL')
if not redis_url: raise RuntimeError("REDIS_URL is not set!")
celery_app = Celery('tasks', broker=redis_url, backend=redis_url, include=['celery_worker'])

# ===> НАЧАЛО НОВОГО КОДА: РАСПИСАНИЕ ДЛЯ CELERY BEAT <===

celery_app.conf.beat_schedule = {
    'ping-redis-every-10-minutes': {
        'task': 'celery_worker.ping_redis_task',
        'schedule': crontab(minute='*/10'),  # Выполнять каждые 10 минут
    },
}


@celery_app.task(name='celery_worker.ping_redis_task')
def ping_redis_task():
    """
    Простая задача, которая "пингует" Redis, чтобы он не "засыпал" на бесплатном тарифе.
    """
    try:
        redis_client = redis.from_url(redis_url)
        if redis_client.ping():
            logger.info("Redis PING successful, keep-alive confirmed.")
        else:
            logger.warning("Redis PING failed.")
    except Exception as e:
        logger.error(f"Error while pinging Redis: {e}")


# ===> КОНЕЦ НОВОГО КОДА <===


# ... (инициализация сервисов без изменений) ...
try:
    database = Database()
    s3_service = S3Service()
    audio_processor = AudioProcessor()
    transcription_service = TranscriptionService()
    translation_service = TranslationService()
    messenger_handler = MessageHandler(database=database, translation_service=translation_service)
    telegram_token = os.getenv('TELEGRAM_TOKEN')
    if telegram_token:
        telegram_handler = TelegramHandler(token=telegram_token, database=database, s3_service=s3_service)
    else:
        telegram_handler = None
    media_handler_service = MediaHandler(transcription_service, translation_service)
    logger.info("Celery worker: All services initialized successfully.")
except Exception as e:
    logger.error(f"Celery worker: CRITICAL INITIALIZATION ERROR: {e}", exc_info=True)
    media_handler_service = None;
    messenger_handler = None;
    telegram_handler = None


# ... (остальной код celery_worker.py без изменений) ...
@celery_app.task(bind=True, name='tasks.process_media', max_retries=2, default_retry_delay=60)
def process_media_task(self, sender_id: str, object_key: str, user_preferences: dict, platform_payload: dict):
    if not all([media_handler_service, messenger_handler]):
        logger.error("Worker handlers not initialized.");
        return

    local_file_path = None
    processed_audio_path = None

    platform = platform_payload.get('platform', 'messenger')
    chat_id = platform_payload.get('chat_id', sender_id)

    try:
        local_file_path = _download_file_from_r2(object_key)
        if not local_file_path:
            raise Exception("Could not retrieve file from storage.")

        result = media_handler_service.process_media(local_file_path, user_preferences)
        processed_audio_path = result.get('processed_audio_path')

        if result.get('success'):
            user = database.get_user(sender_id)
            if platform == 'telegram':
                handle_telegram_success(chat_id, user, result, user_preferences)
            else:  # Messenger
                handle_messenger_success(sender_id, user, result, user_preferences)

            database.save_transcription(user_id=sender_id, object_key=object_key, **result)
            if not user_preferences.get('preferred_language'):
                database.increment_usage(user_id=sender_id)
        else:
            raise result.get('error', Exception('Unknown error during media processing'))

    except Exception as exc:
        logger.error(f"[{self.request.id}] Error in Celery task: {exc}", exc_info=True)
        error_message = f"❌ Failed to process your file. Error: {str(exc)}"

        if platform == 'telegram':
            if telegram_handler:
                asyncio.run(telegram_handler.send_message(chat_id, error_message))
        else:
            messenger_handler._send_text_message(sender_id, error_message)

    finally:
        if local_file_path: audio_processor.cleanup_temp_file(local_file_path)
        if processed_audio_path: audio_processor.cleanup_temp_file(processed_audio_path)
        logger.info(f"[{self.request.id}] Task finished for object {object_key}.")


def handle_messenger_success(sender_id, user, result, user_preferences):
    is_retry = bool(user_preferences.get('preferred_language'))
    lang_info = result.get('language_info', {})
    lang_name = lang_info.get('name', 'N/A')
    response_text = f"📝 **Transcription ({lang_name}):**\n\n{result['transcription']}"
    messenger_handler._send_text_message(sender_id, response_text)

    if is_retry:
        messenger_handler.send_translation_options(sender_id, user)
    else:
        quick_replies = [
            {"content_type": "text", "title": "✅ Looks Good", "payload": "CONFIRM_TRANSCRIPTION_OK"},
            {"content_type": "text", "title": "🗣️ Other language", "payload": "CHOOSE_OTHER_LANGUAGE"}
        ]
        messenger_handler._send_api_request({
            'recipient': {'id': sender_id},
            'message': {'text': "Is the language and transcription correct?", 'quick_replies': quick_replies}
        })


def handle_telegram_success(chat_id, user, result, user_preferences):
    if not telegram_handler: return

    is_retry = bool(user_preferences.get('preferred_language'))
    lang_info = result.get('language_info', {})
    lang_name = lang_info.get('name', 'N/A')

    response_text = f"📝 *Transcription ({lang_name}):*\n\n{result['transcription']}"
    asyncio.run(telegram_handler.send_message(chat_id, response_text))

    keyboard = []
    if is_retry:
        asyncio.run(telegram_handler.send_translation_options(chat_id, user))
    else:
        keyboard = [[
            InlineKeyboardButton("✅ Looks Good", callback_data="CONFIRM_TRANSCRIPTION_OK"),
            InlineKeyboardButton("🗣️ Other language", callback_data="CHOOSE_OTHER_LANGUAGE")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        asyncio.run(telegram_handler.send_message(chat_id, "Is the language and transcription correct?",
                                                  reply_markup=reply_markup))


def _download_file_from_r2(object_key: str) -> Optional[str]:
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{object_key.split('.')[-1]}") as f:
            if s3_service.download_file(object_key, f.name): return f.name
            os.remove(f.name);
            return None
    except Exception as e:
        logger.error(f"Error downloading file from R2 in worker: {e}", exc_info=True);
        return None