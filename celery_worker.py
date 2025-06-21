# celery_worker.py
import os
import logging
import requests
import tempfile
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
from services.s3_service import S3Service

redis_url = os.getenv('REDIS_URL')
if not redis_url:
    raise RuntimeError("REDIS_URL не установлен!")
celery_app = Celery('tasks', broker=redis_url, backend=redis_url, include=['celery_worker'])

try:
    s3_service = S3Service()
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
    s3_service = None

def send_messenger_message(recipient_id: str, message_text: str):
    if not PAGE_ACCESS_TOKEN:
        logger.error("PAGE_ACCESS_TOKEN не найден.")
        return
    try:
        payload = {'recipient': {'id': recipient_id}, 'message': {'text': message_text}, 'messaging_type': 'MESSAGE_TAG', 'tag': 'POST_PURCHASE_UPDATE', 'access_token': PAGE_ACCESS_TOKEN}
        requests.post("https://graph.facebook.com/v18.0/me/messages", json=payload, timeout=10).raise_for_status()
    except Exception as e:
        logger.error(f"Воркер не смог отправить сообщение: {e}", exc_info=True)

@celery_app.task(bind=True, name='tasks.process_media', max_retries=2, default_retry_delay=60)
def process_media_task(self, sender_id: str, object_key: str, user_preferences: dict):
    logger.info(f"[{self.request.id}] Начало задачи для {sender_id}, ключ объекта в R2: {object_key}")
    if not all([media_handler, s3_service]):
        send_messenger_message(sender_id, "❌ Ошибка сервера: обработчик не инициализирован.")
        return

    local_file_path = os.path.join(tempfile.gettempdir(), object_key)
    result = None
    try:
        download_success = s3_service.download_file(object_key, local_file_path)
        if not download_success:
            send_messenger_message(sender_id, "❌ Ошибка сервера: не удалось получить файл из хранилища.")
            return

        result = media_handler.process_media(local_file_path, user_preferences)
        if result.get('success'):
            lang_info = result.get('language_info', {})
            lang_name = lang_info.get('name', result.get('detected_language', ''))
            response_text = f"🎯 Язык: {lang_name}\n\n📝 Транскрипция:\n{result['transcription']}"
            send_messenger_message(sender_id, response_text)
            database.save_transcription(user_id=sender_id, **result)
            database.increment_usage(user_id=sender_id)
        else:
            send_messenger_message(sender_id, f"❌ Не удалось обработать ваш файл. Ошибка: {result.get('error', 'неизвестно')}")

    except Exception as exc:
        logger.error(f"[{self.request.id}] Критическая ошибка в задаче Celery: {exc}", exc_info=True)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            send_messenger_message(sender_id, "❌ Не удалось обработать ваш файл после нескольких попыток.")
    finally:
        # Очищаем все временные файлы и файл в R2
        audio_processor.cleanup_temp_file(local_file_path)
        if result and result.get('processed_audio_path'):
            audio_processor.cleanup_temp_file(result.get('processed_audio_path'))
        s3_service.delete_file(object_key)
        logger.info(f"[{self.request.id}] Все временные файлы и объект в R2 удалены.")