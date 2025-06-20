# celery_worker.py - ФИНАЛЬНАЯ ВЕРСИЯ
import os
import logging
import requests
from celery import Celery
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Импорты ваших сервисов
from services.media_handler import MediaHandler
from services.transcription_service import TranscriptionService
from services.translation_service import TranslationService
from services.database import Database
from services.audio_processor import AudioProcessor

# Инициализация Celery
redis_url = os.getenv('REDIS_URL')
if not redis_url:
    raise RuntimeError("REDIS_URL не установлен в переменных окружения!")
celery_app = Celery('tasks', broker=redis_url, backend=redis_url)

# Инициализация всех сервисов, нужных воркеру
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
    """Отправляет текстовое сообщение пользователю от имени воркера."""
    if not PAGE_ACCESS_TOKEN:
        logger.error("PAGE_ACCESS_TOKEN не найден, не могу отправить сообщение.")
        return
    try:
        payload = {
            'recipient': {'id': recipient_id},
            'messaging_type': 'MESSAGE_TAG',
            'message': {'text': message_text},
            'tag': 'POST_PURCHASE_UPDATE',
            'access_token': PAGE_ACCESS_TOKEN
        }
        response = requests.post("https://graph.facebook.com/v18.0/me/messages", json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"Воркер успешно отправил сообщение пользователю {recipient_id}")
    except Exception as e:
        logger.error(f"Воркер не смог отправить сообщение пользователю {recipient_id}: {e}", exc_info=True)

@celery_app.task(bind=True, name='tasks.process_media', max_retries=2, default_retry_delay=60)
def process_media_task(self, sender_id: str, file_path: str, user_preferences: dict):
    """Фоновая задача Celery для тяжелой обработки медиа."""
    logger.info(f"[{self.request.id}] Начало асинхронной задачи для пользователя {sender_id}")
    if not media_handler:
        logger.error(f"[{self.request.id}] MediaHandler не инициализирован, задача прервана.")
        send_messenger_message(sender_id, "❌ Произошла внутренняя ошибка сервера. Пожалуйста, попробуйте позже.")
        return

    try:
        result = media_handler.process_media(file_path, user_preferences)
        if result.get('success'):
            lang_info = result.get('language_info', {})
            lang_name = lang_info.get('name', result.get('detected_language', ''))
            response_text = f"🎯 Язык: {lang_name}\n\n📝 Транскрипция:\n{result['transcription']}"
            send_messenger_message(sender_id, response_text)
            # Сохраняем в базу данных
            database.save_transcription(user_id=sender_id, **result)
            database.increment_usage(user_id=sender_id)
        else:
            send_messenger_message(sender_id, f"❌ Не удалось обработать ваш файл. Ошибка: {result.get('error', 'неизвестно')}")
    except Exception as exc:
        logger.error(f"[{self.request.id}] Критическая ошибка в задаче Celery: {exc}", exc_info=True)
        send_messenger_message(sender_id, "❌ Произошла критическая ошибка при обработке вашего файла.")
        raise self.retry(exc=exc)
    finally:
        # Очистка временных файлов
        original_file = result.get('original_file_path') if 'result' in locals() else file_path
        processed_file = result.get('processed_audio_path') if 'result' in locals() else None
        audio_processor.cleanup_temp_file(original_file)
        if processed_file and processed_file != original_file:
            audio_processor.cleanup_temp_file(processed_file)
        logger.info(f"[{self.request.id}] Временные файлы удалены.")