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
from services.translation_service import TranslationService
from services.insight_service import InsightService
from telegram import Bot

# ... (инициализация без изменений)

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
    # ...

    media_handler_service = MediaHandler(transcription_service)
    logger.info("Celery worker: All services initialized successfully.")
except Exception as e:


# ...

@celery_app.task(bind=True, name='tasks.process_media', max_retries=2, default_retry_delay=60)
def process_media_task(self, sender_id: str, object_key: str, user_preferences: dict, platform_payload: dict):
    # ... (логика проверки лимитов) ...
    try:
        # ...
        result = media_handler_service.process_media(local_file_path, user_preferences)

        if result.get('success'):
            if platform == 'telegram' and telegram_handler and chat_id:
                # Временно сохраняем сырую транскрипцию для подтверждения
                database.save_raw_transcription(s3_key=object_key, user_id=sender_id, **result)

                # Отправляем на подтверждение
                run_async_task(
                    handle_telegram_success(chat_id, user, result, object_key)
                )
            duration_to_charge = result.get('duration_minutes', 0)
            database.update_minutes_used(sender_id, duration_to_charge)
        else:
            raise result.get('error', Exception('Unknown error during media processing'))
    # ... (обработка ошибок) ...


# ... (run_async_task без изменений)

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


# ... (_download_file_from_r2 без изменений)

def _download_file_from_r2(object_key: str) -> Optional[str]:
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{object_key.split('.')[-1]}") as f:
            if s3_service.download_file(object_key, f.name): return f.name
            os.remove(f.name)
            return None
    except Exception as e:
        logger.error(f"Error downloading file from R2 in worker: {e}", exc_info=True)
        return None