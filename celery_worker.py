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
from services.translation_service import TranslationService  # Восстановлен импорт
from telegram import Bot

# ... (инициализация без изменений)

try:
    database = Database()
    s3_service = S3Service()
    audio_processor = AudioProcessor()
    transcription_service = TranscriptionService()
    translation_service = TranslationService()  # Восстановлена инициализация

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
    # ... (без изменений)

    media_handler_service = MediaHandler(transcription_service, translation_service)  # Снова передаем
    logger.info("Celery worker: All services initialized successfully.")
except Exception as e:
    # ... (без изменений)

    # ... (остальная часть файла без изменений)
        logger.error(f"Error downloading file from R2 in worker: {e}", exc_info=True)
        return None