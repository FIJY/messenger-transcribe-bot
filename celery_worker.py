# celery_worker.py - ФИНАЛЬНАЯ ВЕРСИЯ С ЯВНЫМ ИМПОРТОМ ЗАДАЧ
import os
import logging
import requests
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from services.media_handler import MediaHandler
from services.transcription_service import TranscriptionService
from services.translation_service import TranslationService
from services.database import Database
from services.audio_processor import AudioProcessor
from httpx import Timeout

redis_url = os.getenv('REDIS_URL')
if not redis_url:
    raise RuntimeError("REDIS_URL не установлен!")

# 🔧 ИЗМЕНЕНИЕ ЗДЕСЬ: Добавляем 'include'
# Это говорит Celery: "При запуске, пожалуйста, посмотри в модуль 'celery_worker' и зарегистрируй все задачи, которые там найдешь".
celery_app = Celery('tasks', broker=redis_url, backend=redis_url, include=['celery_worker'])

# ... (остальной код файла остается без изменений)

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
    if not PAGE_ACCESS_TOKEN:
        logger.error("PAGE_ACCESS_TOKEN не найден.")
        return
    try:
        payload = {
            'recipient': {'id': recipient_id},
            'messaging_type': 'MESSAGE_TAG',
            'message': {'text': message_text},
            'tag': 'POST_PURCHASE_UPDATE',
            'access_token': PAGE_ACCESS_TOKEN
        }
        requests.post("https://graph.facebook.com/v18.0/me/messages", json=payload, timeout=10).raise_for_status()
    except Exception as e:
        logger.error(f"Воркер не смог отправить сообщение: {e}", exc_info=True)

@celery_app.task(bind=True, name='tasks.process_media', max_retries=2, default_retry_delay=60)
def process_media_task(self, sender_id: str, file_path: str, user_preferences: dict):
    logger.info(f"[{self.request.id}] Начало задачи для {sender_id}")
    if not media_handler:
        send_messenger_message(sender_id, "❌ Ошибка сервера: обработчик не инициализирован.")
        return

    result = None
    try:
        result = media_handler.process_media(file_path, user_preferences)
        if result.get('success'):
            lang_info = result.get('language_info', {})
            lang_name = lang_info.get('name', result.get('detected_language', ''))
            response_text = f"🎯 Язык: {lang_name}\n\n📝 Транскрипция:\n{result['transcription']}"
            send_messenger_message(sender_id, response_text)
            database.save_transcription(user_id=sender_id, **result)
            database.increment_usage(user_id=sender_id)
        else:
            send_messenger_message(sender_id, f"❌ Не удалось обработать файл. Ошибка: {result.get('error', 'неизвестно')}")
    except Exception as exc:
        logger.error(f"[{self.request.id}] Критическая ошибка в задаче Celery: {exc}", exc_info=True)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            send_messenger_message(sender_id, "❌ Не удалось обработать ваш файл после нескольких попыток.")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"[{self.request.id}] Исходный временный файл удален.")
        if result and result.get('processed_audio_path') and result.get('processed_audio_path') != file_path:
            os.remove(result.get('processed_audio_path'))
            logger.info(f"[{self.request.id}] Обработанный временный файл удален.")