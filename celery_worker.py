# celery_worker.py
import os
import logging
import asyncio
from dotenv import load_dotenv
from bson import ObjectId
import tempfile

# Принудительно загружаем переменные окружения в самом начале
load_dotenv()

from services.celery_client import get_celery_app_client
from services.database import Database
from services.s3_service import S3Service
from services.insight_service import InsightService
from services.business_analyzer_service import BusinessAnalyzerService
from services.transcription_service import TranscriptionService
from services.processing_config import CHECKBOX_CONFIG
from services.export_service import ExportService
from services.telegram_handler import TelegramHandler  # Только для отправки сообщений

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

celery_app = get_celery_app_client()

# --- Инициализация сервисов для воркера ---
try:
    db = Database()
    s3_service = S3Service()
    insight_service = InsightService()
    business_analyzer = BusinessAnalyzerService()
    transcription_service = TranscriptionService(s3_service=s3_service)
    # Инициализируем TelegramHandler только для отправки сообщений, без полной логики
    telegram_bot = TelegramHandler(token=os.getenv('TELEGRAM_TOKEN'), database=db, s3_service=None,
                                   payment_service=None, insight_service=None, translation_service=None,
                                   downloader_service=None, business_analyzer=None, youtube_service=None).bot
    logger.info("Celery worker: All services initialized successfully.")
except Exception as e:
    logger.critical(f"Celery worker: CRITICAL INITIALIZATION ERROR: {e}", exc_info=True)
    telegram_bot = None


async def send_telegram_message(chat_id, text, parse_mode='Markdown'):
    if telegram_bot:
        await telegram_bot.send_message(chat_id, text, parse_mode=parse_mode)


async def send_telegram_document(chat_id, document_path, caption):
    if telegram_bot:
        with open(document_path, 'rb') as doc:
            await telegram_bot.send_document(chat_id=chat_id, document=doc, caption=caption)
        os.remove(document_path)  # Очищаем временный файл


@celery_app.task(name='tasks.process_media_v2')
def process_media_v2(user_id, s3_key, metadata, platform_payload, **kwargs):
    if not telegram_bot:
        logger.error("Telegram bot not initialized. Aborting task.")
        return

    selected_options = kwargs.get('selected_options', [])
    chat_id = platform_payload.get('chat_id')
    note_id = ObjectId(platform_payload.get('note_id'))

    logger.info(f"Starting V2 processing for note {note_id} with options: {selected_options}")

    try:
        # Шаг 1: Транскрибация
        # Этот метод нужно будет создать в TranscriptionService
        # Он должен скачивать файл из S3 и транскрибировать его
        full_text = transcription_service.transcribe_audio_from_s3(s3_key)
        if not full_text:
            raise ValueError("Transcription returned empty text.")

        db.update_note(note_id, {"$set": {"content": full_text, "status": "processed"}})
        asyncio.run(send_telegram_message(chat_id, f"📝 *Полная транскрипция:*\n\n`{full_text}`"))

    except Exception as e:
        logger.error(f"Transcription failed for note {note_id}: {e}", exc_info=True)
        asyncio.run(send_telegram_message(chat_id,
                                          "❌ Произошла критическая ошибка во время транскрибации. Обработка остановлена."))
        return

    # Шаг 2: Обработка выбранных опций
    all_options_map = {item['code']: item['label'] for category in CHECKBOX_CONFIG.values() for item in category}

    async def process_option(option_code):
        title = all_options_map.get(option_code, option_code)
        try:
            result_text = None
            file_path = None

            # 📝 ОСНОВНОЕ
            if option_code == 'summary':
                result_text = insight_service.get_summary(full_text)
            elif option_code == 'keywords':
                # Здесь нужна реализация get_keywords
                result_text = "Ключевые слова: ... (реализация в процессе)"

            # 💼 ДЛЯ РАБОТЫ
            elif option_code == 'protocol':
                # Здесь нужна реализация
                result_text = "Протокол совещания: ... (реализация в процессе)"
            elif option_code == 'action_items':
                analysis = business_analyzer.run_comprehensive_analysis(full_text)
                items = analysis.get('action_items', [])
                result_text = "\n".join(
                    [f"- {item['task']} (Ответственный: {item.get('assignee', 'не указан')})" for item in
                     items]) if items else "Не найдено."

            # 📱 ДЛЯ КОНТЕНТА
            elif option_code == 'post_instagram':
                # Здесь нужна реализация
                result_text = "Пост для Instagram: ... (реализация в процессе)"

            # 📄 Экспорт в файлы
            elif option_code in ['export_md', 'export_docx', 'export_pdf']:
                report_text = insight_service.get_summary(full_text)  # Для примера, используем summary как отчет
                exporter = ExportService(full_text, report_text, "Ваш документ")
                if option_code == 'export_md':
                    file_path = exporter.to_markdown()
                elif option_code == 'export_docx':
                    file_path = exporter.to_docx()
                elif option_code == 'export_pdf':
                    file_path = exporter.to_pdf()

            # Отправка результата
            if result_text:
                await send_telegram_message(chat_id, f"✅ *{title}:*\n\n`{result_text}`")
            elif file_path:
                await send_telegram_document(chat_id, file_path, f"✅ Ваш документ: *{title}*")

        except Exception as e:
            logger.error(f"Error processing option '{option_code}' for note {note_id}: {e}", exc_info=True)
            await send_telegram_message(chat_id, f"❌ Ошибка при обработке опции: *{title}*")

    # Асинхронно запускаем обработку всех выбранных опций
    async def run_all_options():
        tasks = [process_option(option) for option in selected_options]
        await asyncio.gather(*tasks)
        await send_telegram_message(chat_id, "🎉 Обработка всех выбранных опций завершена!")

    asyncio.run(run_all_options())
    logger.info(f"Finished V2 processing for note {note_id}")