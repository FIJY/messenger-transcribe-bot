# celery_worker.py
import os
import logging
import tempfile
import asyncio
import redis
import re
import uuid
import math
from celery import Celery
from celery.schedules import crontab
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from services.media_handler import MediaHandler
from services.transcription_service import TranscriptionService
from services.database import Database
from services.audio_processor import AudioProcessor
from services.s3_service import S3Service
from services.telegram_handler import TelegramHandler
from services.payment_service import PaymentService
from services.translation_service import TranslationService
from services.insight_service import InsightService
from services.localization_service import LocalizationService
from services.telegram_ui import TelegramUI
from telegram import Bot

from services.downloader_service import DownloaderService
from services.business_analyzer_service import BusinessAnalyzerService
from services.youtube_service import YouTubeService

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

redis_url = os.getenv('REDIS_URL')
if not redis_url: raise RuntimeError("REDIS_URL is not set!")
celery_app = Celery('tasks', broker=redis_url, backend=redis_url, include=['celery_worker'])


# ... (celery_app.conf.beat_schedule без изменений)

class LimitExceededError(Exception):
    pass


# Инициализация всех сервисов
try:
    database = Database()
    s3_service = S3Service()
    audio_processor = AudioProcessor()
    transcription_service = TranscriptionService()
    translation_service = TranslationService()
    insight_service = InsightService()
    downloader_service = DownloaderService()
    business_analyzer = BusinessAnalyzerService()
    youtube_service = YouTubeService()
    media_handler_service = MediaHandler(transcription_service)
    localizer = LocalizationService()

    telegram_token = os.getenv('TELEGRAM_TOKEN')
    if telegram_token:
        bot_instance = Bot(token=telegram_token)
        payment_service = PaymentService(bot=bot_instance, database=database)
        # ИЗМЕНЕНИЕ: TelegramHandler теперь нужен и воркеру для отправки статусов
        telegram_handler = TelegramHandler(
            token=telegram_token, database=database, s3_service=s3_service,
            payment_service=payment_service, insight_service=insight_service,
            translation_service=translation_service, downloader_service=downloader_service,
            business_analyzer=business_analyzer, youtube_service=youtube_service
        )
        telegram_handler.ui = TelegramUI(localizer)  # Убедимся, что UI тоже инициализирован
    else:
        telegram_handler = None
    logger.info("Celery worker: All services initialized successfully.")
except Exception as e:
    logger.error(f"Celery worker: CRITICAL INITIALIZATION ERROR: {e}", exc_info=True)
    database = s3_service = audio_processor = transcription_service = telegram_handler = None


def _run_async_task(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _update_telegram_status(chat_id, message_id, lang_code, status_key, **kwargs):
    """НОВАЯ ФУНКЦИЯ: Обновляет статусное сообщение в Telegram."""
    if not all([telegram_handler, localizer]): return
    try:
        text = localizer.get_string(lang_code, status_key, **kwargs)
        _run_async_task(telegram_handler.edit_message(chat_id, message_id, text))
        logger.info(f"Status updated for chat {chat_id}: {text}")
    except Exception as e:
        logger.error(f"Failed to update status for chat {chat_id}: {e}", exc_info=True)


def _handle_task_failure(task_self, exc, chat_id, message_id, lang_code):
    """Обрабатывает окончательную неудачу задачи и уведомляет пользователя."""
    logger.error(f"Task {task_self.request.id} failed after all retries for chat {chat_id}.")
    error_message = localizer.get_string(lang_code, 'error_generic')
    if telegram_handler and chat_id and message_id:
        _run_async_task(telegram_handler.edit_message(chat_id, message_id, error_message))


async def handle_telegram_success(chat_id: int, message_id: int, user_id: str, result: Dict[str, Any], s3_key: str,
                                  source_type: str, lang_code: str):
    """Обрабатывает успешное завершение и отправляет результат."""
    if not all([telegram_handler, database, localizer]): return

    # Сначала удаляем статусное сообщение "в обработке"
    try:
        await telegram_handler.delete_message(chat_id, message_id)
    except Exception as e:
        logger.warning(f"Could not delete status message {message_id} in chat {chat_id}: {e}")

    transcribed_text = result.get('transcription', '')
    if not transcribed_text:
        await telegram_handler.send_message(chat_id, "Could not extract any text from the file.")
        return

    lang_name = result.get('language_info', {}).get('name', 'N/A')
    note_id = database.save_note(user_id=user_id, content=transcribed_text, s3_object_key=s3_key, **result)

    header = localizer.get_string(lang_code, 'transcription_header', lang_name=lang_name)
    text_preview = (transcribed_text[:3500] + '...') if len(transcribed_text) > 3500 else transcribed_text
    full_message = f"{header}\n\n```{text_preview}```"
    await telegram_handler.send_message(chat_id, full_message)

    menu_text, reply_markup = telegram_handler.ui.get_main_actions_menu(lang_code, note_id)
    await telegram_handler.send_message(chat_id, menu_text, reply_markup=reply_markup)


def _download_file_from_s3(object_key: str) -> Optional[str]:
    """Загружает файл из S3 во временный файл."""
    try:
        file_suffix = os.path.splitext(object_key)[-1] or '.tmp'
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_suffix) as f:
            if s3_service.download_file(object_key, f.name):
                return f.name
            os.remove(f.name)
            return None
    except Exception as e:
        logger.error(f"Error downloading file from S3 in worker: {e}", exc_info=True)
        return None


def _process_media_logic(sender_id: str, object_key: str, user_preferences: dict, platform_payload: dict):
    chat_id = platform_payload.get('chat_id')
    message_id = platform_payload.get('message_id')
    lang_code = platform_payload.get('lang_code', 'en')
    source_type = platform_payload.get('source_type', 'unknown')
    local_file_path = None

    try:
        user = database.get_user(sender_id)
        if not user: raise Exception(f"User {sender_id} not found.")

        _update_telegram_status(chat_id, message_id, lang_code, 'status_converting')
        local_file_path = _download_file_from_s3(object_key)
        if not local_file_path: raise Exception("Could not retrieve file from storage.")

        file_duration_sec = audio_processor.get_media_duration(local_file_path)
        file_duration_min = (file_duration_sec / 60) if file_duration_sec else 0

        # Проверка лимитов
        # ... (ваш код проверки лимитов)

        # Расчет ETA
        eta_minutes = math.ceil(file_duration_min / 2) if file_duration_min > 2 else 1
        _update_telegram_status(chat_id, message_id, lang_code, 'status_transcribing', eta=eta_minutes)

        result = media_handler_service.process_media(local_file_path, user_preferences)

        if result.get('success'):
            _update_telegram_status(chat_id, message_id, lang_code, 'status_finishing')
            database.save_raw_transcription(s3_key=object_key, user_id=sender_id, **result)
            _run_async_task(
                handle_telegram_success(chat_id, message_id, sender_id, result, object_key, source_type, lang_code)
            )
            database.update_minutes_used(sender_id, result.get('duration_minutes', 0))
        else:
            raise result.get('error', Exception('Unknown error during media processing'))

    finally:
        if local_file_path:
            audio_processor.cleanup_temp_file(local_file_path)


@celery_app.task(bind=True, name='tasks.process_media', max_retries=2)
def process_media_task(self, sender_id: str, object_key: str, user_preferences: dict, platform_payload: dict):
    if not all([media_handler_service, database, audio_processor, telegram_handler]):
        logger.error("Worker services not initialized. Aborting task.")
        return

    chat_id = platform_payload.get('chat_id')
    message_id = platform_payload.get('message_id')
    lang_code = platform_payload.get('lang_code', 'en')
    try:
        _process_media_logic(sender_id, object_key, user_preferences, platform_payload)
    except Exception as exc:
        logger.error(f"[{self.request.id}] Error in process_media_task: {exc}", exc_info=True)
        try:
            raise self.retry(exc=exc, countdown=60)
        except self.MaxRetriesExceededError:
            _handle_task_failure(self, exc, chat_id, message_id, lang_code)


@celery_app.task(bind=True, name='tasks.process_url', max_retries=2)
def process_url_task(self, sender_id: str, url: str, user_preferences: dict, platform_payload: dict):
    if not all([downloader_service, s3_service, youtube_service, telegram_handler]):
        logger.error("Worker services for URL processing not initialized. Aborting task.")
        return

    chat_id = platform_payload.get('chat_id')
    message_id = platform_payload.get('message_id')
    lang_code = platform_payload.get('lang_code', 'en')
    local_file_path = None
    try:
        source_type = 'url'
        if bool(re.search(r'(?:youtube\.com|youtu\.be)', url)):
            source_type = 'youtube'

        _update_telegram_status(chat_id, message_id, lang_code, 'status_downloading')
        local_file_path, error_type = downloader_service.download_audio(url)
        if not local_file_path:
            # ... (обработка ошибок скачивания)
            # Здесь можно добавить обновление статуса с ошибкой
            _handle_task_failure(self, Exception(f"Download failed with reason: {error_type}"), chat_id, message_id,
                                 lang_code)
            return

        object_key = f"{uuid.uuid4()}{os.path.splitext(local_file_path)[-1]}"
        if not s3_service.upload_file(local_file_path, object_key):
            raise Exception("Failed to upload downloaded file to S3.")

        platform_payload['source_type'] = source_type
        _process_media_logic(sender_id, object_key, user_preferences, platform_payload)

    except Exception as exc:
        logger.error(f"[{self.request.id}] Error in process_url_task: {exc}", exc_info=True)
        try:
            raise self.retry(exc=exc, countdown=60)
        except self.MaxRetriesExceededError:
            _handle_task_failure(self, exc, chat_id, message_id, lang_code)
    finally:
        if local_file_path:
            audio_processor.cleanup_temp_file(local_file_path)


@celery_app.task(name='celery_worker.ping_redis_task')
def ping_redis_task():
    try:
        redis_client = redis.from_url(redis_url)
        redis_client.ping()
        logger.info("Redis PING successful.")
    except Exception as e:
        logger.error(f"Error while pinging Redis: {e}")
