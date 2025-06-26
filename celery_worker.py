# celery_worker.py
import os
import logging
import tempfile
import asyncio
import redis
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv
from typing import Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from datetime import datetime, timezone

from services.media_handler import MediaHandler
from services.transcription_service import TranscriptionService
from services.translation_service import TranslationService
from services.database import Database
from services.audio_processor import AudioProcessor
from services.s3_service import S3Service
from services.telegram_handler import TelegramHandler
from services.payment_service import PaymentService
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
    """Кастомное исключение для превышения лимитов."""
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

try:
    database = Database()
    s3_service = S3Service()
    audio_processor = AudioProcessor()
    transcription_service = TranscriptionService()
    translation_service = TranslationService()

    telegram_token = os.getenv('TELEGRAM_TOKEN')
    if telegram_token:
        bot_instance = Bot(token=telegram_token)
        payment_service = PaymentService(bot=bot_instance, database=database)
        telegram_handler = TelegramHandler(
            token=telegram_token,
            database=database,
            s3_service=s3_service,
            translation_service=translation_service,
            payment_service=payment_service
        )
    else:
        telegram_handler = None
        payment_service = None
        bot_instance = None
        logger.warning("Telegram Bot is disabled due to missing token.")

    media_handler_service = MediaHandler(transcription_service, translation_service)
    logger.info("Celery worker: All services initialized successfully.")
except Exception as e:
    logger.error(f"Celery worker: CRITICAL INITIALIZATION ERROR: {e}", exc_info=True)
    media_handler_service = None
    telegram_handler = None
    payment_service = None

@celery_app.task(bind=True, name='tasks.process_media', max_retries=2, default_retry_delay=60)
def process_media_task(self, sender_id: str, object_key: str, user_preferences: dict, platform_payload: dict):
    if not all([media_handler_service, database, audio_processor, payment_service]):
        logger.error("Worker handlers not initialized.");
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
                logger.info(f"Subscription for user {sender_id} has expired. Downgrading to free plan.")
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
            raise LimitExceededError(f"User {sender_id} limit exceeded. Required: {file_duration_min:.2f}, Left: {minutes_left:.2f}")

        result = media_handler_service.process_media(local_file_path, user_preferences)

        if result.get('success'):
            if platform == 'telegram' and telegram_handler and chat_id:
                handle_telegram_success(chat_id, user, result, user_preferences)
            duration_to_charge = result.get('duration_minutes', file_duration_min)
            database.update_minutes_used(sender_id, duration_to_charge)
            database.save_transcription(
                user_id=sender_id, object_key=object_key,
                transcription=result.get('transcription'),
                detected_language=result.get('detected_language'),
                duration_minutes=duration_to_charge
            )
        else:
            raise result.get('error', Exception('Unknown error during media processing'))

    except LimitExceededError as e:
        logger.warning(str(e))
        if platform == 'telegram' and payment_service and chat_id:
            asyncio.run(payment_service.send_payment_instructions(chat_id, sender_id))

    except Exception as exc:
        logger.error(f"[{self.request.id}] Error in Celery task: {exc}", exc_info=True)
        error_message = "❌ Failed to process your file. Please try again later."
        if platform == 'telegram' and telegram_handler and chat_id:
            asyncio.run(telegram_handler.send_message(chat_id, error_message))

    finally:
        if local_file_path: audio_processor.cleanup_temp_file(local_file_path)
        logger.info(f"[{self.request.id}] Task finished for object {object_key}.")


def handle_telegram_success(chat_id, user, result, user_preferences):
    if not telegram_handler: return

    is_retry = bool(user_preferences.get('preferred_language'))
    lang_info = result.get('language_info', {})
    lang_name = lang_info.get('name', 'N/A')

    response_text = f"📝 *Transcription ({lang_name}):*\n\n{result.get('transcription', '')}"

    confidence = result.get('confidence')
    if confidence:
        response_text += f"\n\n*Confidence:* {confidence:.0%}"

    alternatives = result.get('alternatives')
    if alternatives and len(alternatives) > 1:
        response_text += "\n\n*Other likely options:*"
        for i, alt_text in enumerate(alternatives[1:3], 1): # Показываем до 2х альтернатив
            response_text += f"\n{i+1}. `{alt_text}`"

    asyncio.run(telegram_handler.send_message(chat_id, response_text))

    if not is_retry:
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
            os.remove(f.name)
            return None
    except Exception as e:
        logger.error(f"Error downloading file from R2 in worker: {e}", exc_info=True)
        return None