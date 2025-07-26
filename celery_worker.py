# celery_worker.py
import os
import logging
import asyncio
from dotenv import load_dotenv

# ИСПРАВЛЕНИЕ: Загружаем переменные окружения (например, MONGO_URI)
load_dotenv()

from services.celery_client import get_celery_app_client
from services.telegram_handler import TelegramHandler
from services.database import Database
from services.s3_service import S3Service
from services.insight_service import InsightService
from services.processing_config import CHECKBOX_CONFIG  # Для получения названий опций

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

celery_app = get_celery_app_client()

# --- Инициализация сервисов для воркера ---
try:
    db = Database()
    s3_service = S3Service()
    insight_service = InsightService()

    # Инициализируем TelegramHandler, чтобы отправлять сообщения из воркера
    # Передаем только те зависимости, которые действительно нужны
    telegram_handler = TelegramHandler(
        token=os.getenv('TELEGRAM_TOKEN'),
        database=db,
        s3_service=s3_service,
        insight_service=insight_service,
        # Остальные сервисы не нужны для отправки сообщений, передаем None
        payment_service=None,
        translation_service=None,
        downloader_service=None,
        business_analyzer=None,
        youtube_service=None
    )
    logger.info("Celery worker: All services initialized successfully.")
except Exception as e:
    logger.critical(f"Celery worker: CRITICAL INITIALIZATION ERROR: {e}", exc_info=True)
    telegram_handler = None
    db = None
    insight_service = None


# --- НОВАЯ ЗАДАЧА ДЛЯ СИСТЕМЫ ГАЛОЧЕК ---
@celery_app.task(name='tasks.process_media_v2')
def process_media_v2(user_id, s3_key, metadata, platform_payload, **kwargs):
    if not all([telegram_handler, db, insight_service]):
        logger.error("One or more core services are not initialized. Aborting task.")
        return

    # ИСПРАВЛЕНИЕ: Правильно получаем selected_options из kwargs
    selected_options = kwargs.get('selected_options', [])
    chat_id = platform_payload.get('chat_id')
    note_id = platform_payload.get('original_message_id')  # Используем для обновления

    logger.info(f"Starting V2 processing for user {user_id} with options: {selected_options}")

    # --- ЗАГЛУШКА ЛОГИКИ ОБРАБОТКИ ---
    # Здесь будет ваша реальная логика транскрибации и анализа
    # 1. Скачать файл из S3 (если нужно)
    # 2. Сделать транскрибацию -> full_text
    full_text = "Это полная транскрипция вашего файла. Она была сгенерирована в фоновом режиме."

    # Сохраняем основной текст транскрипции в БД
    note = db.get_note_by_id(note_id)
    if note:
        db.update_note(note_id, {"$set": {"content": full_text, "status": "processed"}})

    asyncio.run(telegram_handler.bot.send_message(chat_id, f"📝 *Полная транскрипция:*\n```{full_text}```",
                                                  parse_mode='Markdown'))

    # 3. Обработать каждую выбранную опцию
    for option in selected_options:
        try:
            result = None
            title = option  # Default title

            # Находим label для красивого заголовка
            for category in CHECKBOX_CONFIG.values():
                for item in category:
                    if item['code'] == option:
                        title = item['label']
                        break

            if option == 'summary':
                result = insight_service.get_summary(full_text)
            elif option == 'protocol':
                result = "Это сгенерированный протокол совещания на основе полного текста."
            # ... добавьте здесь логику для всех кодов из processing_config.py
            else:
                result = f"Результат для опции '{title}' успешно сгенерирован."

            if result:
                asyncio.run(
                    telegram_handler.bot.send_message(chat_id, f"✅ *{title}:*\n```{result}```", parse_mode='Markdown'))

        except Exception as e:
            logger.error(f"Error processing option '{option}' for user {user_id}: {e}")
            asyncio.run(telegram_handler.bot.send_message(chat_id, f"❌ Не удалось обработать опцию: {title}"))

    logger.info(f"Finished V2 processing for user {user_id}")
