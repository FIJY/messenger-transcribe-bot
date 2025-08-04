# celery_worker.py
import os
import tempfile
import logging
from celery import Celery
import asyncio
import sys
from dependency_injector.wiring import inject, Provide

# Добавляем корневую папку в пути импорта
sys.path.append('.')

from containers import Container
from services.database import Database
from services.s3_service import S3Service
from services.telegram_service import TelegramService
from services.transcription_service import TranscriptionService
from services.insight_service import InsightService
from utils.message_formatter import format_processed_message

# Настройка Celery
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
celery_app = Celery("worker", broker=CELERY_BROKER_URL, backend=CELERY_BROKER_URL)


# Декоратор @inject "научит" нашу задачу получать сервисы из контейнера
@celery_app.task(bind=True, name='process_media')
@inject
def process_media_task(
        self,
        note_id: str,
        chat_id: int,
        message_id: int,
        processing_options: list,
        # Указываем, какие сервисы нужно "внедрить" из контейнера
        db: Database = Provide[Container.db_service],
        s3: S3Service = Provide[Container.s3_service],
        telegram: TelegramService = Provide[Container.telegram_service],
        transcription: TranscriptionService = Provide[Container.transcription_service],
        insight: InsightService = Provide[Container.insight_service]
):
    """Фоновая задача для полной обработки медиафайла."""
    try:
        logging.info(f"Starting processing for note_id: {note_id}")
        note = db.get_note(note_id)
        if not note:
            raise ValueError(f"Note {note_id} not found.")

        with tempfile.TemporaryDirectory() as temp_dir:
            local_path = os.path.join(temp_dir, note['file_unique_id'])

            # Скачивание файла
            file_path_tg = asyncio.run(telegram.get_file_path(note['file_id']))
            asyncio.run(telegram.download_file(file_path_tg, local_path))

            # Загрузка в S3
            s3_path = s3.upload_file(local_path, f"{note['user_id']}/{note['file_unique_id']}")
            db.update_note(note_id, {"s3_path": s3_path, "status": "transcribing"})

            # Транскрибация
            presigned_url = s3.get_presigned_url(s3_path)
            full_text = transcription.transcribe_audio_from_url(presigned_url)
            db.update_note(note_id, {"content": full_text, "status": "generating_insights"})

            # Генерация инсайтов
            insights = {}
            if "summary" in processing_options:
                insights["summary"] = insight.get_summary(full_text)
            if "keywords" in processing_options:
                insights["keywords"] = insight.get_keywords(full_text)
            db.update_note(note_id, {"insights": insights, "status": "processed"})

            # Отправка результата
            final_message = format_processed_message(full_text, insights)
            asyncio.run(telegram.edit_message_text(chat_id, message_id, final_message))
            logging.info(f"Successfully processed note_id: {note_id}")

    except Exception as e:
        logging.error(f"Error in process_media_task for note_id {note_id}: {e}", exc_info=True)
        db.update_note(note_id, {"status": "error"})
        if 'telegram' in locals():
            asyncio.run(telegram.edit_message_text(chat_id, message_id, "Произошла ошибка во время обработки."))


# Инициализация контейнера для воркера
container = Container()
container.wire(modules=[__name__])