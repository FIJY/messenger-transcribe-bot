# celery_worker.py
import os
import logging
import asyncio

from services.celery_client import get_celery_app_client
from services.telegram_handler import TelegramHandler
# ... (импортируйте все ваши сервисы, как в app.py)
from services.database import Database
from services.s3_service import S3Service
from services.payment_service import PaymentService
from services.insight_service import InsightService
from services.translation_service import TranslationService
from services.downloader_service import DownloaderService
from services.business_analyzer_service import BusinessAnalyzerService
from services.youtube_service import YouTubeService

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

celery_app = get_celery_app_client()

# --- Инициализация сервисов для воркера ---
try:
    db = Database()
    s3_service = S3Service()
    # ... (инициализируйте остальные сервисы, которые нужны для обработки)
    insight_service = InsightService()

    # Инициализируем TelegramHandler, чтобы отправлять сообщения из воркера
    telegram_handler = TelegramHandler(
        token=os.getenv('TELEGRAM_TOKEN'),
        database=db,
        s3_service=s3_service,
        # ... (передайте все зависимости)
        payment_service=None,  # Не нужен в воркере
        insight_service=insight_service,
        translation_service=None,
        downloader_service=None,
        business_analyzer=None,
        youtube_service=None
    )
    logger.info("Celery worker: All services initialized successfully.")
except Exception as e:
    logger.error(f"Celery worker: CRITICAL INITIALIZATION ERROR: {e}", exc_info=True)
    telegram_handler = None


# --- НОВАЯ ЗАДАЧА ДЛЯ СИСТЕМЫ ГАЛОЧЕК ---
@celery_app.task(name='tasks.process_media_v2')
def process_media_v2(user_id, s3_key, metadata, platform_payload):
    if not telegram_handler:
        logger.error("Telegram handler not initialized. Aborting task.")
        return

    selected_options = platform_payload.get('kwargs', {}).get('selected_options', [])
    chat_id = platform_payload.get('chat_id')
    logger.info(f"Starting V2 processing for user {user_id} with options: {selected_options}")

    # --- ЗАГЛУШКА ЛОГИКИ ОБРАБОТКИ ---
    # Здесь будет ваша реальная логика транскрибации и анализа
    # 1. Скачать файл из S3
    # 2. Сделать транскрибацию -> full_text
    full_text = "Это полная транскрипция вашего файла."
    asyncio.run(telegram_handler.bot.send_message(chat_id, f"📝 *Полная транскрипция:*\n```{full_text}```",
                                                  parse_mode='Markdown'))

    # 3. Обработать каждую выбранную опцию
    for option in selected_options:
        try:
            if option == 'summary':
                result = insight_service.get_summary(full_text)
                title = "Краткое содержание"
            elif option == 'protocol':
                result = "Это сгенерированный протокол совещания."
                title = "Протокол совещания"
            # ... добавьте здесь логику для всех кодов из processing_config.py
            else:
                result = f"Результат для опции '{option}'."
                title = f"Результат: {option}"

            # Отправляем результат пользователю
            asyncio.run(
                telegram_handler.bot.send_message(chat_id, f"✅ *{title}:*\n```{result}```", parse_mode='Markdown'))

        except Exception as e:
            logger.error(f"Error processing option '{option}' for user {user_id}: {e}")
            asyncio.run(telegram_handler.bot.send_message(chat_id, f"❌ Не удалось обработать опцию: {option}"))

    logger.info(f"Finished V2 processing for user {user_id}")


# Старые задачи можно оставить для обратной совместимости или удалить
@celery_app.task(name='tasks.process_media')
def process_media(*args, **kwargs):
    logger.warning("Legacy task 'process_media' called. Please update to V2.")


@celery_app.task(name='tasks.process_url')
def process_url(*args, **kwargs):
    logger.warning("Legacy task 'process_url' called. Please update to V2.")
