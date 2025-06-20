# celery_worker.py - ФИНАЛЬНАЯ ВЕРСИЯ С ДИАГНОСТИКОЙ ДИСКА
import os
import logging
import requests
import time  # Для небольшой задержки
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Импорты ваших сервисов
from services.media_handler import MediaHandler
from services.transcription_service import TranscriptionService
from services.translation_service import TranslationService
from services.database import Database
from services.audio_processor import AudioProcessor
from httpx import Timeout

# Инициализация Celery
redis_url = os.getenv('REDIS_URL')
if not redis_url:
    raise RuntimeError("REDIS_URL не установлен в переменных окружения!")

# Говорим Celery, чтобы он искал задачи в этом же файле
celery_app = Celery('tasks', broker=redis_url, backend=redis_url, include=['celery_worker'])

# Инициализация сервисов
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
        requests.post("https://graph.facebook.com/v18.0/me/messages", json=payload, timeout=10).raise_for_status()
        logger.info(f"Воркер успешно отправил сообщение пользователю {recipient_id}")
    except Exception as e:
        logger.error(f"Воркер не смог отправить сообщение пользователю {recipient_id}: {e}", exc_info=True)


@celery_app.task(bind=True, name='tasks.process_media', max_retries=2, default_retry_delay=60)
def process_media_task(self, sender_id: str, file_path: str, user_preferences: dict):
    """Фоновая задача Celery с диагностикой диска."""
    logger.info(f"[{self.request.id}] Начало задачи для {sender_id}, целевой файл: {file_path}")
    if not media_handler:
        send_messenger_message(sender_id, "❌ Ошибка сервера: обработчик не инициализирован.")
        return

    result = None
    try:
        # --- ДИАГНОСТИКА ДИСКА ---
        shared_dir_path = os.path.dirname(file_path)
        logger.info(f"Проверяем содержимое общей папки: {shared_dir_path}")
        try:
            # Пытаемся прочитать содержимое папки, в которой должен быть наш файл
            shared_dir_contents = os.listdir(shared_dir_path)
            logger.info(f"Содержимое папки {shared_dir_path}: {shared_dir_contents}")
        except Exception as list_e:
            logger.error(f"Не удалось прочитать содержимое папки {shared_dir_path}: {list_e}")
        # --- КОНЕЦ ДИАГНОСТИКИ ---

        # Добавим небольшую паузу на случай, если есть задержка синхронизации диска
        time.sleep(2)

        # Выполняем основную работу
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
            send_messenger_message(sender_id,
                                   f"❌ Не удалось обработать ваш файл. Ошибка: {result.get('error', 'неизвестно')}")

    except Exception as exc:
        logger.error(f"[{self.request.id}] Критическая ошибка в задаче Celery: {exc}", exc_info=True)
        try:
            # Попытка повторить задачу
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            send_messenger_message(sender_id, "❌ Не удалось обработать ваш файл после нескольких попыток.")
    finally:
        # Очистка временных файлов
        # file_path - это оригинальный файл, который скачал message_handler
        # result['processed_audio_path'] - это файл .wav, который создал audio_processor
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"[{self.request.id}] Исходный временный файл удален: {file_path}")
        if result and result.get('processed_audio_path') and os.path.exists(result['processed_audio_path']):
            if result.get('processed_audio_path') != file_path:
                os.remove(result.get('processed_audio_path'))
                logger.info(
                    f"[{self.request.id}] Обработанный временный файл удален: {result.get('processed_audio_path')}")