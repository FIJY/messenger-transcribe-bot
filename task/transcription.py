# tasks/transcription.py - Фоновые задачи для транскрипции и обработки
import logging
import asyncio
import tempfile
import os
from typing import Dict, Any, List
from celery import Celery
from celery.exceptions import Retry

from config import settings
from services.database import DatabaseService
from services.storage import StorageService
from services.transcription import TranscriptionService
from services.ai_processing import AIProcessingService
from services.telegram_client import TelegramClient
from utils.file_handler import create_export_files
from ui.localization import LocalizationService

logger = logging.getLogger(__name__)

# Создание Celery приложения
celery_app = Celery(
    'transcription_tasks',
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

# Конфигурация Celery
celery_app.conf.update(
    task_track_started=True,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    result_expires=3600,  # Результаты хранятся 1 час
)

# Инициализация сервисов
db = DatabaseService()
storage = StorageService()
transcription_service = TranscriptionService()
ai_processing = AIProcessingService()
telegram = TelegramClient(settings.TELEGRAM_TOKEN)
localization = LocalizationService()


@celery_app.task(bind=True, max_retries=3)
def transcribe_and_process_audio(self, audio_file_id: str, user_id: int,
                                 processing_options: List[str], language: str):
    """
    Основная задача: транскрипция аудио и последующая обработка
    """
    try:
        # Запускаем асинхронную обработку
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        result = loop.run_until_complete(
            _transcribe_and_process_async(audio_file_id, user_id, processing_options, language)
        )

        loop.close()
        return result

    except Exception as e:
        logger.error(f"❌ Ошибка в задаче транскрипции {audio_file_id}: {e}", exc_info=True)

        # Обновляем статус на failed
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            _handle_processing_error(audio_file_id, user_id, str(e), language)
        )
        loop.close()

        # Повтор задачи при определенных ошибках
        if self.request.retries < self.max_retries:
            logger.info(f"🔄 Повтор задачи {audio_file_id}, попытка {self.request.retries + 1}")
            raise self.retry(countdown=60 * (2 ** self.request.retries))  # Экспоненциальная задержка

        raise


async def _transcribe_and_process_async(audio_file_id: str, user_id: int,
                                        processing_options: List[str], language: str) -> Dict[str, Any]:
    """Асинхронная обработка файла"""

    # Инициализируем сервисы
    await db.initialize()

    try:
        # 1. Получаем информацию о файле
        audio_file = await db.get_audio_file(audio_file_id)
        if not audio_file:
            raise Exception(f"Аудио файл {audio_file_id} не найден")

        logger.info(f"🎵 Начинаем обработку файла {audio_file_id}")

        # 2. Обновляем статус
        await db.update_audio_file(audio_file_id, {"status": "transcribing"})
        await _send_status_update(user_id, "transcription_started", language)

        # 3. Скачиваем файл с S3
        local_file_path = await _download_file_from_s3(audio_file['s3_path'])

        # 4. Транскрипируем аудио
        transcription_result = await transcription_service.transcribe_audio(local_file_path)

        if not transcription_result['success']:
            raise Exception(f"Ошибка транскрипции: {transcription_result.get('error', 'Unknown error')}")

        # 5. Сохраняем транскрипцию в БД
        transcription = await db.create_transcription(
            audio_file_id=audio_file_id,
            user_id=user_id,
            text=transcription_result['text'],
            language=transcription_result.get('language', 'unknown'),
            confidence=transcription_result.get('confidence')
        )

        logger.info(f"✅ Транскрипция завершена: {len(transcription_result['text'])} символов")

        # 6. Отправляем базовую транскрипцию пользователю
        await _send_transcription_result(user_id, transcription, language)

        # 7. Обрабатываем дополнительные опции
        if processing_options:
            await db.update_audio_file(audio_file_id, {"status": "processing"})
            await _send_status_update(user_id, "ai_processing_started", language,
                                      options_count=len(processing_options))

            processing_results = await _process_additional_options(
                transcription_result['text'], processing_options, language
            )

            # Сохраняем результаты обработки
            await db.update_transcription_results(transcription['id'], processing_results)

            # Отправляем результаты пользователю
            await _send_processing_results(user_id, processing_results, language)

        # 8. Обновляем финальный статус
        await db.update_audio_file(audio_file_id, {"status": "completed"})

        # 9. Отправляем финальное сообщение с действиями
        await _send_completion_message(user_id, transcription['id'], language)

        # 10. Очищаем временные файлы
        if os.path.exists(local_file_path):
            os.unlink(local_file_path)

        logger.info(f"🎉 Полная обработка файла {audio_file_id} завершена")

        return {
            "success": True,
            "transcription_id": transcription['id'],
            "processing_results": processing_results if processing_options else {}
        }

    except Exception as e:
        logger.error(f"❌ Ошибка обработки файла {audio_file_id}: {e}", exc_info=True)
        raise

    finally:
        await db.close()


async def _download_file_from_s3(s3_path: str) -> str:
    """Скачивает файл с S3 во временную директорию"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(s3_path)[1]) as temp_file:
        temp_path = temp_file.name

    success = await storage.download_file(s3_path, temp_path)
    if not success:
        raise Exception(f"Не удалось скачать файл с S3: {s3_path}")

    return temp_path


async def _process_additional_options(text: str, processing_options: List[str],
                                      language: str) -> Dict[str, Any]:
    """Обрабатывает дополнительные опции с помощью AI"""
    results = {}

    for option in processing_options:
        try:
            logger.info(f"🤖 Обработка опции: {option}")

            if option == "summary":
                results[option] = await ai_processing.create_summary(text)

            elif option == "keypoints":
                results[option] = await ai_processing.extract_key_points(text)

            elif option.startswith("translate_"):
                target_lang = option.split("_")[1]
                results[option] = await ai_processing.translate_text(text, target_lang)

            elif option == "meeting_protocol":
                results[option] = await ai_processing.create_meeting_protocol(text)

            elif option == "action_items":
                results[option] = await ai_processing.extract_action_items(text)

            elif option == "instagram_post":
                results[option] = await ai_processing.create_instagram_post(text)

            elif option == "shorts_clips":
                results[option] = await ai_processing.extract_shorts_clips(text)

            elif option == "lecture_notes":
                results[option] = await ai_processing.create_lecture_notes(text)

            elif option == "exam_questions":
                results[option] = await ai_processing.generate_exam_questions(text)

            # Добавляем другие опции обработки...

            else:
                logger.warning(f"⚠️ Неизвестная опция обработки: {option}")
                continue

            logger.info(f"✅ Опция {option} обработана успешно")

        except Exception as e:
            logger.error(f"❌ Ошибка обработки опции {option}: {e}")
            results[option] = {"error": str(e)}

    return results


async def _send_status_update(user_id: int, message_key: str, language: str, **kwargs):
    """Отправляет обновление статуса пользователю"""
    try:
        message_text = localization.get_text(message_key, language, **kwargs)
        await telegram.send_message(chat_id=user_id, text=message_text)
    except Exception as e:
        logger.error(f"Ошибка отправки статуса пользователю {user_id}: {e}")


async def _send_transcription_result(user_id: int, transcription: Dict[str, Any], language: str):
    """Отправляет результат транскрипции пользователю"""
    try:
        # Основное сообщение с транскрипцией
        transcript_text = transcription['text']

        # Ограничиваем длину сообщения в Telegram (4096 символов)
        if len(transcript_text) > 3800:
            preview_text = transcript_text[:3800] + "..."
            full_text = transcript_text
        else:
            preview_text = transcript_text
            full_text = transcript_text

        message_header = localization.get_text("transcription_completed", language).format(
            word_count=len(transcript_text.split()),
            language=transcription.get('language', 'unknown')
        )

        full_message = f"{message_header}\n\n{preview_text}"

        await telegram.send_message(chat_id=user_id, text=full_message)

        # Создаем и отправляем файлы
        files = await create_export_files(full_text, "transcription")

        for file_path, file_type in files:
            try:
                await telegram.send_document(
                    chat_id=user_id,
                    document_path=file_path,
                    caption=f"📄 Транскрипция ({file_type})"
                )
                # Удаляем временный файл
                os.unlink(file_path)
            except Exception as e:
                logger.error(f"Ошибка отправки файла {file_path}: {e}")

    except Exception as e:
        logger.error(f"Ошибка отправки транскрипции пользователю {user_id}: {e}")


async def _send_processing_results(user_id: int, results: Dict[str, Any], language: str):
    """Отправляет результаты обработки пользователю"""
    from ui.keyboards import create_result_actions_keyboard

    for option, result in results.items():
        if isinstance(result, dict) and 'error' in result:
            # Пропускаем результаты с ошибками
            continue

        try:
            # Получаем название опции для пользователя
            option_name = localization.get_processing_option_name(option, language)

            # Форматируем результат
            if isinstance(result, str):
                content = result
            elif isinstance(result, dict):
                content = result.get('text', str(result))
            else:
                content = str(result)

            # Отправляем сообщение
            message_text = f"**{option_name}**\n\n{content}"

            # Ограничиваем длину сообщения
            if len(message_text) > 4000:
                message_text = message_text[:3900] + "...\n\n_Полный текст в файле_"

            await telegram.send_message(
                chat_id=user_id,
                text=message_text,
                parse_mode="Markdown"
            )

            # Создаем файл для длинных результатов
            if len(content) > 3000:
                files = await create_export_files(content, option_name)
                for file_path, file_type in files:
                    try:
                        await telegram.send_document(
                            chat_id=user_id,
                            document_path=file_path,
                            caption=f"📄 {option_name} ({file_type})"
                        )
                        os.unlink(file_path)
                    except Exception as e:
                        logger.error(f"Ошибка отправки файла результата: {e}")

        except Exception as e:
            logger.error(f"Ошибка отправки результата {option}: {e}")


async def _send_completion_message(user_id: int, transcription_id: str, language: str):
    """Отправляет финальное сообщение с вариантами действий"""
    from ui.keyboards import create_result_actions_keyboard

    try:
        completion_text = localization.get_text("processing_completed", language)
        keyboard = create_result_actions_keyboard(transcription_id, language)

        await telegram.send_message(
            chat_id=user_id,
            text=completion_text,
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка отправки финального сообщения пользователю {user_id}: {e}")


async def _handle_processing_error(audio_file_id: str, user_id: int, error_message: str, language: str):
    """Обработка ошибки при обработке файла"""
    try:
        await db.initialize()

        # Обновляем статус файла
        await db.update_audio_file(audio_file_id, {
            "status": "failed",
            "error_message": error_message
        })

        # Отправляем сообщение об ошибке пользователю
        error_text = localization.get_text("processing_failed", language)

        keyboard = {
            "inline_keyboard": [
                [{"text": "🔄 Попробовать снова", "callback_data": f"retry:{audio_file_id}"}],
                [{"text": "🏠 Главное меню", "callback_data": "main_menu"}]
            ]
        }

        await telegram.send_message(
            chat_id=user_id,
            text=error_text,
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка обработки ошибки для файла {audio_file_id}: {e}")

    finally:
        await db.close()


# Дополнительные задачи

@celery_app.task
def cleanup_old_files():
    """Периодическая очистка старых файлов"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(_cleanup_old_files_async())
    finally:
        loop.close()


async def _cleanup_old_files_async():
    """Асинхронная очистка старых файлов"""
    await db.initialize()

    try:
        # Очищаем файлы старше 30 дней
        deleted_count = await db.cleanup_old_files(days=30)
        logger.info(f"🧹 Очистка завершена: удалено {deleted_count} файлов")

        # Также очищаем файлы из S3 storage
        await storage.cleanup_old_files(days=30)

    except Exception as e:
        logger.error(f"Ошибка очистки старых файлов: {e}")
    finally:
        await db.close()


@celery_app.task
def send_usage_statistics():
    """Отправка статистики использования (для админов)"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(_send_usage_statistics_async())
    finally:
        loop.close()


async def _send_usage_statistics_async():
    """Асинхронная отправка статистики"""
    await db.initialize()

    try:
        stats = await db.get_system_statistics()

        # Отправляем статистику админу (если настроено)
        if hasattr(settings, 'ADMIN_CHAT_ID') and settings.ADMIN_CHAT_ID:
            stats_text = f"""
📊 **Статистика системы**

👥 **Пользователи:**
• Всего: {stats['total_users']}
• Активные за неделю: {stats['active_users_week']}

🎵 **Файлы:**
• Всего обработано: {stats['total_files']}
• Транскрипций создано: {stats['total_transcriptions']}

📈 **Активность:**
• Конверсия: {(stats['active_users_week'] / max(stats['total_users'], 1) * 100):.1f}%
"""

            await telegram.send_message(
                chat_id=settings.ADMIN_CHAT_ID,
                text=stats_text,
                parse_mode="Markdown"
            )

    except Exception as e:
        logger.error(f"Ошибка отправки статистики: {e}")
    finally:
        await db.close()


# Настройка периодических задач
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    # Очистка старых файлов каждый день в 2:00
    'cleanup-old-files': {
        'task': 'tasks.transcription.cleanup_old_files',
        'schedule': crontab(hour=2, minute=0),
    },
    # Статистика каждый понедельник в 9:00
    'weekly-statistics': {
        'task': 'tasks.transcription.send_usage_statistics',
        'schedule': crontab(hour=9, minute=0, day_of_week=1),
    },
}


# Альтернативная задача для быстрого запуска без Celery (для разработки)
async def process_audio_sync(audio_file_id: str, user_id: int,
                             processing_options: List[str], language: str):
    """Синхронная обработка файла (для разработки без Celery)"""
    return await _transcribe_and_process_async(audio_file_id, user_id, processing_options, language)