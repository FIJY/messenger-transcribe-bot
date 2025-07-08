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
from telegram import InlineKeyboardMarkup
from datetime import datetime, timezone
from bson import ObjectId

from services.media_handler import MediaHandler
from services.transcription_service import TranscriptionService
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

    telegram_token = os.getenv('TELEGRAM_TOKEN')
    if telegram_token:
        bot_instance = Bot(token=telegram_token)
        payment_service = PaymentService(bot=bot_instance, database=database)
        telegram_handler = TelegramHandler(
            token=telegram_token,
            database=database,
            s3_service=s3_service,
            payment_service=payment_service
        )
    else:
        telegram_handler = None
        payment_service = None
        bot_instance = None
        logger.warning("Telegram Bot is disabled due to missing token.")

    media_handler_service = MediaHandler(transcription_service, None)
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