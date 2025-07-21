# celery_worker.py
import os
import logging
import tempfile
import asyncio
import redis
import re
import uuid
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv
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
from telegram import Bot

from services.downloader_service import DownloaderService
from services.business_analyzer_service import BusinessAnalyzerService
from services.youtube_service import YouTubeService

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


# Инициализация всех сервисов, которые могут понадобиться воркерам
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

    telegram_token = os.getenv('TELEGRAM_TOKEN')
    if telegram_token:
        bot_instance = Bot(token=telegram_token)
        payment_service = PaymentService(bot=bot_instance, database=database)
        telegram_handler = TelegramHandler(
            token=telegram_token, database=database, s3_service=s3_service,
            payment_service=payment_service, insight_service=insight_service,
            translation_service=translation_service, downloader_service=downloader_service,
            business_analyzer=business_analyzer, youtube_service=youtube_service
        )
    else:
        telegram_handler = None
        payment_service = None
        logger.warning("Telegram Bot is disabled due to missing token.")

    logger.info("Celery worker: All services initialized successfully.")
except Exception as e:
    logger.error(f"Celery worker: CRITICAL INITIALIZATION ERROR: {e}", exc_info=True)
    # Устанавливаем все в None, чтобы задачи корректно завершались с ошибкой
    database = s3_service = audio_processor = transcription_service = translation_service = insight_service = downloader_service = business_analyzer = youtube_service = media_handler_service = telegram_handler = payment_service = None


def _run_async_task(coro):
    """Безопасно запускает асинхронную задачу."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _handle_task_failure(task_self, exc, chat_id):
    """Обрабатывает окончательную неудачу задачи и уведомляет пользователя."""
    logger.error(f"Task {task_self.request.id} failed after all retries for chat {chat_id}.")
    error_message = "❌ We are sorry, but we could not process your file after several attempts. Please try again later or contact support."
    if telegram_handler and chat_id:
        _run_async_task(telegram_handler.send_message(chat_id, error_message))


def _process_media_logic(sender_id: str, object_key: str, user_preferences: dict, platform_payload: dict):
    """
    Общая логика обработки медиафайла после его загрузки в S3.
    Вынесена в отдельную функцию, чтобы избежать дублирования кода.
    """
    chat_id = platform_payload.get('chat_id')
    source_type = platform_payload.get('source_type', 'unknown')
    local_file_path = None

    try:
        user = database.get_user(sender_id)
        if not user:
            raise Exception(f"User {sender_id} not found in database.")

        # Проверка и обновление статуса подписки
        if user.get('plan') in ['basic', 'premium']:
            expires_at = user.get('subscription_expires_at')
            if expires_at and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at and expires_at < datetime.now(timezone.utc):
                database.downgrade_user_to_free(sender_id)
                user = database.get_user(sender_id)

        local_file_path = _download_file_from_s3(object_key)
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
            if platform_payload.get('platform') == 'telegram' and chat_id:
                database.save_raw_transcription(s3_key=object_key, user_id=sender_id, **result)
                _run_async_task(
                    handle_telegram_success(chat_id, sender_id, result, object_key, source_type)
                )
            duration_to_charge = result.get('duration_minutes', 0)
            database.update_minutes_used(sender_id, duration_to_charge)
        else:
            raise result.get('error', Exception('Unknown error during media processing'))

    finally:
        if local_file_path:
            audio_processor.cleanup_temp_file(local_file_path)
        logger.info(f"Finished processing for object {object_key}.")


@celery_app.task(bind=True, name='tasks.process_media', max_retries=2)
def process_media_task(self, sender_id: str, object_key: str, user_preferences: dict, platform_payload: dict):
    """
    Задача для обработки файла, который УЖЕ загружен в S3 (например, прямой аплоад).
    """
    if not all([media_handler_service, database, audio_processor, payment_service, telegram_handler]):
        logger.error("Worker services not initialized. Aborting task.")
        return

    chat_id = platform_payload.get('chat_id')
    try:
        _process_media_logic(sender_id, object_key, user_preferences, platform_payload)
    except LimitExceededError as e:
        logger.warning(str(e))
        if payment_service and chat_id:
            _run_async_task(payment_service.send_payment_instructions(chat_id, sender_id))
    except Exception as exc:
        logger.error(f"[{self.request.id}] Error in process_media_task: {exc}", exc_info=True)
        try:
            raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
        except self.MaxRetriesExceededError:
            _handle_task_failure(self, exc, chat_id)


@celery_app.task(bind=True, name='tasks.process_url', max_retries=2)
def process_url_task(self, sender_id: str, url: str, user_preferences: dict, platform_payload: dict):
    """
    НОВАЯ ЗАДАЧА: Скачивает аудио из URL, загружает в S3 и затем обрабатывает.
    """
    if not all([downloader_service, s3_service, youtube_service, telegram_handler]):
        logger.error("Worker services for URL processing not initialized. Aborting task.")
        return

    chat_id = platform_payload.get('chat_id')
    local_file_path = None
    try:
        # Определяем источник и формируем ключ S3
        source_type = 'url'
        object_key = None
        if bool(re.search(r'(?:youtube\.com|youtu\.be)', url)):
            source_type = 'youtube'
            video_info = youtube_service.get_info(url)
            if video_info and video_info.get('id'):
                # Добавляем UUID для уникальности
                object_key = f"yt_{video_info['id']}_{uuid.uuid4()}.mp3"
            else:
                logger.warning(f"Could not get video ID for YouTube URL: {url}")

        # Скачиваем файл
        local_file_path, error_type = downloader_service.download_audio(url)
        if not local_file_path:
            error_message = "❌ Failed to download audio from the link. The link might be broken or from an unsupported site."
            if error_type == 'LOGIN_REQUIRED':
                error_message = "❌ This content is private or protected. Please download it manually and send the file."
            _run_async_task(telegram_handler.send_message(chat_id, error_message))
            return

        # Загружаем в S3
        object_key = object_key or f"{uuid.uuid4()}{os.path.splitext(local_file_path)[-1]}"
        if not s3_service.upload_file(local_file_path, object_key):
            raise Exception("Failed to upload downloaded file to S3.")

        # Обновляем payload для следующего шага
        platform_payload['source_type'] = source_type

        # Вызываем общую логику обработки
        _process_media_logic(sender_id, object_key, user_preferences, platform_payload)

    except LimitExceededError as e:
        logger.warning(str(e))
        if payment_service and chat_id:
            _run_async_task(payment_service.send_payment_instructions(chat_id, sender_id))
    except Exception as exc:
        logger.error(f"[{self.request.id}] Error in process_url_task: {exc}", exc_info=True)
        try:
            raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
        except self.MaxRetriesExceededError:
            _handle_task_failure(self, exc, chat_id)
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


async def handle_telegram_success(chat_id: int, user_id: str, result: Dict[str, Any], s3_key: str, source_type: str):
    if not telegram_handler or not database: return

    transcribed_text = result.get('transcription', '')
    if not transcribed_text:
        await telegram_handler.send_message(chat_id, "Could not extract any text from the file.")
        return

    lang_name = result.get('language_info', {}).get('name', 'N/A')

    note_id = database.save_note(
        user_id=user_id, content=transcribed_text, s3_object_key=s3_key,
        detected_language=result.get('detected_language'),
        duration_minutes=result.get('duration_minutes', 0),
        tags=['plain_text', source_type], source_type=source_type
    )

    header = f"📝 *Transcription ({lang_name})*:"
    text_preview = (transcribed_text[:3500] + '...') if len(transcribed_text) > 3500 else transcribed_text
    full_message = f"{header}\n\n```{text_preview}```"
    await telegram_handler.send_message(chat_id, full_message)

    menu_text, reply_markup = telegram_handler.ui.get_main_actions_menu(note_id)
    await telegram_handler.send_message(chat_id, menu_text, reply_markup=reply_markup)


def _download_file_from_s3(object_key: str) -> Optional[str]:
    try:
        file_suffix = os.path.splitext(object_key)[-1] or '.tmp'
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_suffix) as f:
            if s3_service.download_file(object_key, f.name): return f.name
            os.remove(f.name)
            return None
    except Exception as e:
        logger.error(f"Error downloading file from S3 in worker: {e}", exc_info=True)
        return None
