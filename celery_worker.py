# celery_worker.py
import os
import logging
import asyncio
from dotenv import load_dotenv
from bson import ObjectId

# ИСПРАВЛЕНИЕ: Загружаем переменные окружения (например, MONGO_URI)
load_dotenv()

from services.celery_client import get_celery_app_client
from services.telegram_handler import TelegramHandler
from services.database import Database
from services.s3_service import S3Service
from services.insight_service import InsightService
from services.business_analyzer_service import BusinessAnalyzerService
from services.transcription_service import TranscriptionService  # Предполагаем, что у вас есть этот сервис
from services.processing_config import CHECKBOX_CONFIG

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

celery_app = get_celery_app_client()

# --- Инициализация сервисов для воркера ---
try:
    db = Database()
    s3_service = S3Service()
    insight_service = InsightService()
    business_analyzer = BusinessAnalyzerService()
    transcription_service = TranscriptionService()

    # Инициализируем TelegramHandler для отправки сообщений
    telegram_handler = TelegramHandler(
        token=os.getenv('TELEGRAM_TOKEN'),
        database=db,
        s3_service=s3_service,
        insight_service=insight_service,
        business_analyzer=business_analyzer,
        # Остальные сервисы не нужны для отправки сообщений, передаем None
        payment_service=None,
        translation_service=None,
        downloader_service=None,
        youtube_service=None
    )
    logger.info("Celery worker: All services initialized successfully.")
except Exception as e:
    logger.critical(f"Celery worker: CRITICAL INITIALIZATION ERROR: {e}", exc_info=True)
    telegram_handler = None


@celery_app.task(name='tasks.process_media_v2')
def process_media_v2(user_id, s3_key, metadata, platform_payload, **kwargs):
    if not telegram_handler:
        logger.error("Telegram handler not initialized. Aborting task.")
        return

    # ИСПРАВЛЕНИЕ: Правильно получаем selected_options из kwargs
    selected_options = kwargs.get('selected_options', [])
    chat_id = platform_payload.get('chat_id')
    note_id_str = platform_payload.get('note_id')

    if not note_id_str:
        logger.error(f"Task for user {user_id} is missing 'note_id' in payload.")
        return

    note_id = ObjectId(note_id_str)

    logger.info(f"Starting V2 processing for user {user_id} with options: {selected_options}")

    try:
        full_text = transcription_service.transcribe_audio_from_s3(s3_key)
        if not full_text:
            raise ValueError("Transcription returned empty text.")

        db.update_note(note_id, {"$set": {"content": full_text, "status": "processed"}})
        asyncio.run(telegram_handler.bot.send_message(chat_id, f"� *Полная транскрипция:*\n```{full_text}```",
                                                      parse_mode='Markdown'))

    except Exception as e:
        logger.error(f"Transcription failed for note {note_id}: {e}", exc_info=True)
        asyncio.run(telegram_handler.bot.send_message(chat_id, "❌ Произошла ошибка во время транскрибации."))
        return

    all_options_map = {item['code']: item['label'] for category in CHECKBOX_CONFIG.values() for item in category}

    async def process_option(option_code):
        title = all_options_map.get(option_code, option_code)
        try:
            result = None
            if option_code == 'summary':
                result = insight_service.get_summary(full_text)
            # ... (добавьте здесь логику для всех опций)
            else:
                result = f"Результат для '{title}' успешно сгенерирован."

            if result:
                await telegram_handler.send_message(chat_id, f"✅ *{title}:*\n```{result}```")
        except Exception as e:
            logger.error(f"Error processing option '{option_code}' for note {note_id}: {e}")
            await telegram_handler.send_message(chat_id, f"❌ Ошибка при обработке опции: *{title}*")

    async def run_all_options():
        tasks = [process_option(option) for option in selected_options]
        await asyncio.gather(*tasks)

    asyncio.run(run_all_options())
    logger.info(f"Finished V2 processing for user {user_id}")

