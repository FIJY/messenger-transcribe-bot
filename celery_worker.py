# celery_worker.py
import os
import logging
import requests
import tempfile
from celery import Celery
from dotenv import load_dotenv
from typing import Optional, Dict, Any


load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Импорты сервисов ---
from services.media_handler import MediaHandler
from services.transcription_service import TranscriptionService
from services.translation_service import TranslationService
from services.database import Database
from services.audio_processor import AudioProcessor
from services.s3_service import S3Service
# ===> НОВЫЙ ВАЖНЫЙ ИМПОРТ <===
from services.message_handler import MessageHandler

redis_url = os.getenv('REDIS_URL')
if not redis_url: raise RuntimeError("REDIS_URL не установлен!")
celery_app = Celery('tasks', broker=redis_url, backend=redis_url, include=['celery_worker'])

# --- Инициализация сервисов для воркера ---
try:
    s3_service = S3Service()
    transcription_service = TranscriptionService()
    translation_service = TranslationService()
    database = Database()
    audio_processor = AudioProcessor()

    # ===> ИНИЦИАЛИЗИРУЕМ MessageHandler <===
    # Он нужен для вызова новой функции отправки кнопок
    message_handler = MessageHandler(database=database, translation_service=translation_service)

    # MediaHandler должен идти после инициализации своих зависимостей
    media_handler_service = MediaHandler(transcription_service, translation_service)

    PAGE_ACCESS_TOKEN = os.getenv('PAGE_ACCESS_TOKEN')
    logger.info("Celery воркер: Все сервисы успешно инициализированы.")
except Exception as e:
    logger.error(f"Celery воркер: КРИТИЧЕСКАЯ ОШИБКА ИНИЦИАЛИЗАЦИИ: {e}", exc_info=True)
    media_handler_service = None
    message_handler = None


def _send_celery_message(recipient_id: str, message_data: Dict[str, Any]):
    """Отправляет простое текстовое сообщение от имени воркера."""
    if not PAGE_ACCESS_TOKEN:
        logger.error("PAGE_ACCESS_TOKEN не найден.")
        return
    try:
        # Для прямых ответов лучше использовать стандартный messaging_type RESPONSE
        payload = {
            'recipient': {'id': recipient_id},
            'messaging_type': 'RESPONSE',
            'message': message_data,
            'access_token': PAGE_ACCESS_TOKEN
        }
        # Используем стандартный эндпоинт для сообщений
        requests.post("https://graph.facebook.com/v18.0/me/messages", json=payload, timeout=10).raise_for_status()
    except Exception as e:
        logger.error(f"Воркер не смог отправить сообщение: {e}", exc_info=True)


def _download_file_from_r2(object_key: str) -> Optional[str]:
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{object_key.split('.')[-1]}") as temp_f:
            local_file_path = temp_f.name
        if s3_service.download_file(object_key, local_file_path):
            logger.info(f"Файл {object_key} успешно скачан из R2 в {local_file_path}")
            return local_file_path
        else:
            os.remove(local_file_path)
            return None
    except Exception as e:
        logger.error(f"Ошибка при скачивании файла из R2 в воркере: {e}", exc_info=True)
        return None


@celery_app.task(bind=True, name='tasks.process_media', max_retries=2, default_retry_delay=60)
def process_media_task(self, sender_id: str, object_key: str, user_preferences: dict):
    logger.info(f"[{self.request.id}] Начало задачи для {sender_id}, ключ R2: {object_key}")
    if not all([media_handler_service, s3_service, message_handler]):
        _send_celery_message(sender_id, {'text': "❌ Ошибка сервера: обработчик не инициализирован."})
        return

    local_file_path = _download_file_from_r2(object_key)
    if not local_file_path:
        _send_celery_message(sender_id, {'text': "❌ Ошибка сервера: не удалось получить файл из хранилища."})
        return

    result = None
    try:
        result = media_handler_service.process_media(local_file_path, user_preferences)
        if result.get('success'):
            # ===> ПОЛНОСТЬЮ ОБНОВЛЕННЫЙ БЛОК ОТПРАВКИ РЕЗУЛЬТАТА <===

            # 1. Отправляем основной результат (только текст транскрипции)
            lang_info = result.get('language_info', {})
            lang_name = lang_info.get('name', result.get('detected_language', ''))
            response_text = f"🎯 Язык: {lang_name}\n\n📝 Транскрипция:\n{result['transcription']}"
            _send_celery_message(sender_id, {'text': response_text})

            # 2. СРАЗУ ЖЕ отправляем второе сообщение с кнопками для исправления языка
            message_handler.send_language_correction_options(sender_id)

            # 3. Сохраняем результат в базу данных
            database.save_transcription(
                user_id=sender_id,
                object_key=object_key,
                **result
            )
            database.increment_usage(user_id=sender_id)
        else:
            _send_celery_message(sender_id, {
                'text': f"❌ Не удалось обработать ваш файл. Ошибка: {result.get('error', 'неизвестно')}"})
    except Exception as exc:
        logger.error(f"[{self.request.id}] Критическая ошибка в задаче Celery: {exc}", exc_info=True)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            _send_celery_message(sender_id, {'text': "❌ Не удалось обработать ваш файл после нескольких попыток."})
    finally:
        audio_processor.cleanup_temp_file(local_file_path)
        if result and result.get('processed_audio_path'):
            audio_processor.cleanup_temp_file(result.get('processed_audio_path'))
        logger.info(f"[{self.request.id}] Временные локальные файлы удалены. Объект в R2 {object_key} сохранен.")