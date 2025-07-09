# celery_worker.py
import os
import logging
import tempfile
import asyncio
import redis
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from bson import ObjectId


from services.media_handler import MediaHandler
from services.transcription_service import TranscriptionService
from services.database import Database
from services.audio_processor import AudioProcessor
from services.s3_service import S3Service
from services.telegram_handler import TelegramHandler
from services.payment_service import PaymentService
from services.translation_service import TranslationService
from services.insight_service import InsightService
from telegram import Bot

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

redis_url = os.getenv('REDIS_URL')
if not redis_url: raise RuntimeError("REDIS_URL is not set!")
celery_app = Celery('tasks', broker=redis_url, backend=redis_url, include=['celery_worker'])

celery_app.conf.beat_schedule = {
    'ping-redis-every-10-minutes': {
        'task': 'celery_worker.ping_redis_task',
        'schedule': crontab(minute='*/10'),
    },
}


class LimitExceededError(Exception):
    pass


@celery_app.task(name='celery_worker.ping_redis_task')
def ping_redis_task():
    try:
        redis_client = redis.from_url(redis_url)
        if redis_client.ping():
            logger.info("Redis PING successful, keep-alive confirmed.")
        else:
            logger.warning("Redis PING failed.")
    except Exception as e:
        logger.error(f"Error while pinging Redis: {e}")

# ИСПРАВЛЕНИЕ: Объявляем все переменные как None до блока try
# Это гарантирует их существование в глобальной области видимости, даже если инициализация не удастся.
database = None
s3_service = None
audio_processor = None
transcription_service = None
translation_service = None
insight_service = None
telegram_handler = None
payment_service = None
bot_instance = None
media_handler_service = None

try:
    database = Database()
    s3_service = S3Service()
    audio_processor = AudioProcessor()
    transcription_service = TranscriptionService()
    translation_service = TranslationService()
    insight_service = InsightService()

    telegram_token = os.getenv('TELEGRAM_TOKEN')
    if telegram_token:
        bot_instance = Bot(token=telegram_token)
        payment_service = PaymentService(bot=bot_instance, database=database)
        telegram_handler = TelegramHandler(
            token=telegram_token,
            database=database,
            s3_service=s3_service,
            payment_service=payment_service,
            insight_service=insight_service,
            translation_service=translation_service
        )
    else:
        logger.warning("Telegram Bot is disabled due to missing token.")

    media_handler_service = MediaHandler(transcription_service)
    logger.info("Celery worker: All services initialized successfully.")
except Exception as e:
    logger.error(f"Celery worker: CRITICAL INITIALIZATION ERROR: {e}", exc_info=True)


@celery_app.task(bind=True, name='tasks.process_media', max_retries=2, default_retry_delay=60)
def process_media_task(self, sender_id: str, object_key: str, user_preferences: dict, platform_payload: dict):
    if not all([media_handler_service, database, audio_processor, payment_service, telegram_handler]):
        logger.error("Worker handlers not initialized. A service probably failed during startup. Check logs above.")
        return

    local_file_path = None
    platform = platform_payload.get('platform')
    chat_id = platform_payload.get('chat_id')

    try:
        user = database.get_user(sender_id)
        if not user:
            raise Exception(f"User {sender_id} not found in database.")

        if user.get('plan') in ['basic', 'premium']:
            expires_at = user.get('subscription_expires_at')
            if expires_at and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at and expires_at < datetime.now(timezone.utc):
                database.downgrade_user_to_free(sender_id)
                user = database.get_user(sender_id)

        local_file_path = _download_file_from_r2(object_key)
        if not local_file_path:
            raise Exception("Could not retrieve file from storage.")

        file_duration_sec = audio_processor.get_media_duration(local_file_path)
        file_duration_min = (file_duration_sec / 60) if file_duration_sec else 0

        minutes_limit = user.get('minutes_limit', 0)
        minutes_used = user.get('minutes_used', 0)
        minutes_left = minutes_limit - minutes_used

        if file_duration_min > minutes_left:
            raise LimitExceededError(f"User {sender_id} limit exceeded.")

        result = media_handler_service.process_media(local_file_path, user_preferences)

        if result.get('success'):
            if platform == 'telegram' and chat_id:
                database.save_raw_transcription(s3_key=object_key, user_id=sender_id, **result)
                run_async_task(
                    handle_telegram_success(chat_id, user, result, object_key)
                )
            duration_to_charge = result.get('duration_minutes', 0)
            database.update_minutes_used(sender_id, duration_to_charge)
        else:
            raise result.get('error', Exception('Unknown error during media processing'))

    except LimitExceededError as e:
        logger.warning(str(e))
        if platform == 'telegram' and payment_service and chat_id:
            run_async_task(payment_service.send_payment_instructions(chat_id, sender_id))
    except Exception as exc:
        logger.error(f"[{self.request.id}] Error in Celery task: {exc}", exc_info=True)
        error_message = "❌ Failed to process your file. Please try again later."
        if platform == 'telegram' and telegram_handler and chat_id:
            run_async_task(telegram_handler.send_message(chat_id, error_message))
    finally:
        if local_file_path: audio_processor.cleanup_temp_file(local_file_path)
        logger.info(f"[{self.request.id}] Task finished for object {object_key}.")


def run_async_task(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(coro)


async def handle_telegram_success(chat_id: int, user: Dict[str, Any], result: Dict[str, Any], s3_key: str):
    if not telegram_handler: return

    lang_info = result.get('language_info', {})
    lang_name = lang_info.get('name', 'N/A')

    message, reply_markup = telegram_handler.ui.get_transcription_confirmation_message(
        text=result['transcription'],
        lang_name=lang_name,
        s3_key=s3_key
    )
    await telegram_handler.send_message(chat_id, message, reply_markup=reply_markup)


def _download_file_from_r2(object_key: str) -> Optional[str]:
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{object_key.split('.')[-1]}") as f:
            if s3_service.download_file(object_key, f.name): return f.name
            os.remove(f.name)
            return None
    except Exception as e:
        logger.error(f"Error downloading file from R2 in worker: {e}", exc_info=True)
        return None