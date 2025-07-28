# celery_worker.py
import os
import logging
import asyncio
from dotenv import load_dotenv
from bson import ObjectId
from telegram import Bot

load_dotenv()

from services.celery_client import get_celery_app_client
from services.database import Database
from services.s3_service import S3Service
from services.insight_service import InsightService
from services.business_analyzer_service import BusinessAnalyzerService
from services.transcription_service import TranscriptionService
from services.processing_config import CHECKBOX_CONFIG
from services.export_service import ExportService

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

celery_app = get_celery_app_client()

# --- Инициализация сервисов для воркера ---
# Эти сервисы будут доступны во всех задачах Celery
try:
    db = Database()
    s3_service = S3Service()
    insight_service = InsightService()
    business_analyzer = BusinessAnalyzerService()
    transcription_service = TranscriptionService(s3_service=s3_service)
    telegram_bot = Bot(token=os.getenv('TELEGRAM_TOKEN'))
    logger.info("Celery worker: Все сервисы успешно инициализированы.")
except Exception as e:
    logger.critical(f"Celery worker: КРИТИЧЕСКАЯ ОШИБКА ИНИЦИАЛИЗАЦИИ: {e}", exc_info=True)
    telegram_bot = None


# --- Асинхронные хелперы ---
async def send_telegram_message(chat_id, text, parse_mode='Markdown'):
    if telegram_bot:
        await telegram_bot.send_message(chat_id, text, parse_mode=parse_mode)


async def send_telegram_document(chat_id, document_path, caption):
    if telegram_bot:
        with open(document_path, 'rb') as doc:
            await telegram_bot.send_document(chat_id=chat_id, document=doc, caption=caption)
        os.remove(document_path)


# --- Основная асинхронная логика задачи ---
async def _async_process_media(user_id, s3_key, metadata, platform_payload, **kwargs):
    if not telegram_bot:
        logger.error("Telegram бот не инициализирован. Прерывание задачи.")
        return

    selected_options = kwargs.get('selected_options', [])
    chat_id = platform_payload.get('chat_id')
    note_id = ObjectId(platform_payload.get('note_id'))

    logger.info(f"Начинаем асинхронную обработку V2 для заметки {note_id} с опциями: {selected_options}")

    try:
        # Шаг 1: Транскрибация
        full_text = transcription_service.transcribe_audio_from_s3(s3_key)
        if not full_text:
            raise ValueError("Транскрибация вернула пустой текст.")

        db.update_note(note_id, {"$set": {"content": full_text, "status": "processed"}})
        await send_telegram_message(chat_id, f"📝 *Полная транскрипция:*\n\n`{full_text}`")

    except Exception as e:
        logger.error(f"Транскрибация не удалась для заметки {note_id}: {e}", exc_info=True)
        await send_telegram_message(chat_id,
                                    "❌ Произошла критическая ошибка во время транскрипции. Обработка остановлена.")
        return

    # Шаг 2: Обработка выбранных опций
    all_options_map = {item['code']: item['label'] for category in CHECKBOX_CONFIG.values() for item in category}

    async def process_option(option_code):
        title = all_options_map.get(option_code, option_code)
        try:
            result_text = None
            file_path = None

            if option_code == 'summary':
                result_text = insight_service.get_summary(full_text)
            elif option_code == 'action_items':
                analysis = business_analyzer.run_comprehensive_analysis(full_text)
                items = analysis.get('action_items', [])
                result_text = "\n".join([f"- {item['task']}" for item in items]) if items else "Задачи не найдены."
            # Добавьте здесь обработку других опций...

            if result_text:
                await send_telegram_message(chat_id, f"✅ *{title}:*\n\n{result_text}")
            elif file_path:
                await send_telegram_document(chat_id, file_path, f"✅ Ваш документ: *{title}*")

        except Exception as e:
            logger.error(f"Ошибка обработки опции '{option_code}' для заметки {note_id}: {e}", exc_info=True)
            await send_telegram_message(chat_id, f"❌ Ошибка при обработке опции: *{title}*")

    processing_tasks = [process_option(option) for option in selected_options]
    await asyncio.gather(*processing_tasks)
    await send_telegram_message(chat_id, "🎉 Обработка всех выбранных опций завершена!")
    logger.info(f"Завершена обработка V2 для заметки {note_id}")


# --- Синхронная "обертка" для задачи Celery ---
@celery_app.task(name='tasks.process_media_v2')
def process_media_v2(user_id, s3_key, metadata, platform_payload, **kwargs):
    """
    Синхронная точка входа для Celery, которая запускает асинхронную логику.
    """
    try:
        asyncio.run(_async_process_media(user_id, s3_key, metadata, platform_payload, **kwargs))
    except Exception as e:
        logger.critical(f"Критический сбой в задаче Celery process_media_v2: {e}", exc_info=True)
