# services/celery_worker.py
import os
import logging
import time
from dotenv import load_dotenv
from bson import ObjectId

load_dotenv()

from services.celery_client import get_celery_app_client
from services.database import Database
from services.s3_service import S3Service
from services.insight_service import InsightService
from services.business_analyzer_service import BusinessAnalyzerService
from services.transcription_service import TranscriptionService
from services.processing_config import CHECKBOX_CONFIG

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

celery_app = get_celery_app_client()

# --- Инициализация сервисов ---
try:
    db = Database()
    s3_service = S3Service()
    insight_service = InsightService()
    business_analyzer = BusinessAnalyzerService()
    transcription_service = TranscriptionService(s3_service=s3_service)

    logger.info("Celery worker: Все сервисы успешно инициализированы.")
except Exception as e:
    logger.critical(f"Celery worker: КРИТИЧЕСКАЯ ОШИБКА ИНИЦИАЛИЗАЦИИ: {e}", exc_info=True)


def queue_telegram_message(chat_id: int, text: str, priority: int = 5):
    """
    Добавляет сообщение в очередь для отправки веб-процессом
    """
    try:
        # Обрезаем слишком длинные сообщения
        if len(text) > 4000:
            text = text[:3990] + "\n\n[Сообщение обрезано]"

        message_doc = {
            'chat_id': chat_id,
            'text': text,
            'priority': priority,
            'status': 'pending',
            'created_at': time.time(),
            'attempts': 0
        }

        # Сохраняем в коллекцию message_queue
        result = db.db.message_queue.insert_one(message_doc)
        logger.info(f"Сообщение добавлено в очередь: {result.inserted_id} для чата {chat_id}")
        return True

    except Exception as e:
        logger.error(f"Ошибка добавления в очередь: {e}")
        return False


@celery_app.task(name='tasks.process_media_v2')
def process_media_v2(user_id, s3_key, metadata, platform_payload, **kwargs):
    """
    Основная задача обработки медиа - БЕЗ прямой отправки сообщений
    """
    try:
        selected_options = kwargs.get('selected_options', [])
        chat_id = platform_payload.get('chat_id')
        note_id = ObjectId(platform_payload.get('note_id'))

        logger.info(f"🚀 Начинаем обработку для заметки {note_id} с опциями: {selected_options}")

        # === ЭТАП 1: ТРАНСКРИБАЦИЯ ===
        try:
            logger.info("📝 Начинаем транскрибацию...")
            full_text = transcription_service.transcribe_audio_from_s3(s3_key)
            if not full_text:
                raise ValueError("Транскрибация вернула пустой текст.")

            # Обновляем заметку с транскрипцией
            db.update_note(note_id, {"$set": {
                "content": full_text,
                "status": "transcribed",
                "transcribed_at": time.time()
            }})

            # Добавляем транскрипцию в очередь с высоким приоритетом
            preview_text = full_text[:3500] + "..." if len(full_text) > 3500 else full_text
            queue_telegram_message(
                chat_id,
                f"📝 *Транскрипция завершена*\n\n{preview_text}",
                priority=1
            )

            logger.info("✅ Транскрибация завершена и добавлена в очередь")

        except Exception as e:
            logger.error(f"❌ Транскрибация не удалась: {e}", exc_info=True)
            db.update_note(note_id, {"$set": {
                "status": "transcription_error",
                "error": str(e),
                "error_at": time.time()
            }})
            queue_telegram_message(chat_id, "❌ Ошибка во время транскрибации.", priority=1)
            return

        # === ЭТАП 2: ОБРАБОТКА ОПЦИЙ ===
        all_options_map = {item['code']: item['label'] for category in CHECKBOX_CONFIG.values() for item in category}
        processing_results = {}

        logger.info(f"🔄 Начинаем обработку {len(selected_options)} опций...")

        for i, option_code in enumerate(selected_options):
            title = all_options_map.get(option_code, option_code)
            logger.info(f"🔍 Обрабатываем опцию {i + 1}/{len(selected_options)}: {title}")

            try:
                result_text = None

                # Получаем результат в зависимости от типа опции
                if option_code == 'summary':
                    result_text = insight_service.get_summary(full_text)
                elif option_code == 'key_points':
                    result_text = insight_service.get_key_points(full_text)
                elif option_code == 'action_items':
                    result_text = insight_service.get_action_items(full_text)
                elif option_code == 'questions':
                    result_text = insight_service.get_questions(full_text)
                elif option_code == 'post':
                    result_text = insight_service.get_social_post(full_text)
                # Добавьте здесь другие опции...
                else:
                    logger.warning(f"⚠️ Неизвестная опция: {option_code}")
                    result_text = f"Обработчик для опции '{option_code}' не найден."

                if result_text and result_text.strip():
                    # Обрезаем длинные результаты
                    if len(result_text) > 3700:
                        result_text = result_text[:3600] + "\n\n[Результат обрезан для Telegram]"

                    # Сохраняем результат
                    processing_results[option_code] = {
                        'title': title,
                        'content': result_text,
                        'status': 'success',
                        'processed_at': time.time()
                    }

                    # Добавляем в очередь с приоритетом по порядку
                    queue_telegram_message(
                        chat_id,
                        f"✅ *{title}*\n\n{result_text}",
                        priority=i + 2
                    )

                    logger.info(f"✅ Опция '{option_code}' обработана и добавлена в очередь")
                else:
                    # Пустой результат
                    processing_results[option_code] = {
                        'title': title,
                        'content': None,
                        'status': 'empty',
                        'processed_at': time.time()
                    }
                    queue_telegram_message(
                        chat_id,
                        f"⚠️ *{title}*\nПолучен пустой результат",
                        priority=i + 2
                    )
                    logger.warning(f"⚠️ Пустой результат для опции '{option_code}'")

            except Exception as e:
                logger.error(f"❌ Ошибка обработки опции '{option_code}': {e}", exc_info=True)
                processing_results[option_code] = {
                    'title': title,
                    'content': None,
                    'status': 'error',
                    'error': str(e),
                    'processed_at': time.time()
                }
                queue_telegram_message(
                    chat_id,
                    f"❌ *{title}*\nОшибка при обработке: {str(e)[:200]}",
                    priority=i + 2
                )

        # === ЭТАП 3: СОХРАНЕНИЕ ФИНАЛЬНЫХ РЕЗУЛЬТАТОВ ===
        try:
            db.update_note(note_id, {
                "$set": {
                    "processing_results": processing_results,
                    "status": "completed",
                    "completed_at": time.time(),
                    "selected_options": selected_options
                }
            })

            # Финальное сообщение с низким приоритетом
            successful_count = sum(1 for r in processing_results.values() if r['status'] == 'success')
            total_count = len(selected_options)

            final_message = f"🎉 *Обработка завершена!*\n\nУспешно: {successful_count}/{total_count} опций"
            queue_telegram_message(chat_id, final_message, priority=99)

            logger.info(f"🎯 Обработка полностью завершена для заметки {note_id}. "
                        f"Успешно: {successful_count}/{total_count}")

        except Exception as e:
            logger.error(f"❌ Ошибка сохранения финальных результатов: {e}", exc_info=True)
            queue_telegram_message(chat_id, "⚠️ Результаты обработаны, но возникла ошибка сохранения", priority=98)

    except Exception as e:
        logger.critical(f"💥 КРИТИЧЕСКИЙ СБОЙ в задаче Celery: {e}", exc_info=True)
        try:
            # Пытаемся сохранить информацию об ошибке
            chat_id = platform_payload.get('chat_id')
            note_id = platform_payload.get('note_id')

            if note_id:
                db.update_note(ObjectId(note_id), {
                    "$set": {
                        "status": "critical_error",
                        "error": str(e),
                        "error_at": time.time()
                    }
                })

            if chat_id:
                queue_telegram_message(
                    chat_id,
                    '💥 Произошла критическая ошибка при обработке. Попробуйте еще раз.',
                    priority=0
                )
        except:
            logger.error("Не удалось даже сохранить информацию об ошибке")

        # Пробрасываем исключение для мониторинга Celery
        raise