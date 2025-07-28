# services/celery_worker.py
import os
import logging
import asyncio
import httpx
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
from services.export_service import ExportService

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

    # Telegram Bot Token для прямых HTTP запросов
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN not found in environment variables")

    logger.info("Celery worker: Все сервисы успешно инициализированы.")
except Exception as e:
    logger.critical(f"Celery worker: КРИТИЧЕСКАЯ ОШИБКА ИНИЦИАЛИЗАЦИИ: {e}", exc_info=True)
    TELEGRAM_TOKEN = None


# --- HTTP-клиент для Telegram API ---
async def send_telegram_message_http(chat_id: int, text: str, parse_mode: str = 'Markdown'):
    """
    Отправка сообщения через прямой HTTP запрос к Telegram API
    """
    if not TELEGRAM_TOKEN:
        logger.error("Telegram token не настроен.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    # Экранируем специальные символы для Markdown
    if parse_mode == 'Markdown':
        # Простое экранирование основных символов
        text = text.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')

    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode
    }

    timeout = httpx.Timeout(30.0, connect=10.0)
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)

    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        try:
            response = await client.post(url, json=payload)
            if response.status_code == 200:
                logger.info(f"Сообщение успешно отправлено в чат {chat_id}")
                return True
            else:
                logger.error(f"Ошибка отправки сообщения: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Исключение при отправке сообщения: {e}")
            return False


# --- Основная асинхронная логика ---
async def _async_process_media(user_id, s3_key, platform_payload, **kwargs):
    selected_options = kwargs.get('selected_options', [])
    chat_id = platform_payload.get('chat_id')
    note_id = ObjectId(platform_payload.get('note_id'))

    logger.info(f"Начинаем обработку для заметки {note_id} с опциями: {selected_options}")

    try:
        # Транскрибация
        full_text = transcription_service.transcribe_audio_from_s3(s3_key)
        if not full_text:
            raise ValueError("Транскрибация вернула пустой текст.")

        # Обновляем заметку в БД
        db.update_note(note_id, {"$set": {"content": full_text, "status": "processed"}})

        # Отправляем транскрипцию (обрезаем если слишком длинная)
        if len(full_text) > 4000:
            preview_text = full_text[:4000] + "...\n\n[Текст обрезан]"
        else:
            preview_text = full_text

        success = await send_telegram_message_http(
            chat_id,
            f"📝 Полная транскрипция:\n\n{preview_text}"
        )

        if not success:
            logger.warning("Не удалось отправить транскрипцию, но продолжаем обработку")

    except Exception as e:
        logger.error(f"Транскрибация не удалась: {e}", exc_info=True)
        await send_telegram_message_http(chat_id, "❌ Ошибка во время транскрибации.")
        return

    # Получаем маппинг опций
    all_options_map = {item['code']: item['label'] for category in CHECKBOX_CONFIG.values() for item in category}

    async def process_option(option_code):
        title = all_options_map.get(option_code, option_code)
        try:
            result_text = None
            if option_code == 'summary':
                result_text = insight_service.get_summary(full_text)
            elif option_code == 'key_points':
                result_text = insight_service.get_key_points(full_text)
            elif option_code == 'action_items':
                result_text = insight_service.get_action_items(full_text)
            elif option_code == 'questions':
                result_text = insight_service.get_questions(full_text)
            # Добавьте здесь другие опции по мере необходимости

            if result_text:
                # Обрезаем слишком длинные результаты
                if len(result_text) > 4000:
                    result_text = result_text[:4000] + "...\n\n[Результат обрезан]"

                success = await send_telegram_message_http(
                    chat_id,
                    f"✅ {title}:\n\n{result_text}"
                )

                if success:
                    logger.info(f"Результат для опции '{option_code}' отправлен")
                else:
                    logger.warning(f"Не удалось отправить результат для опции '{option_code}'")
            else:
                await send_telegram_message_http(chat_id, f"⚠️ Не удалось обработать: {title}")

        except Exception as e:
            logger.error(f"Ошибка обработки опции '{option_code}': {e}", exc_info=True)
            await send_telegram_message_http(chat_id, f"❌ Ошибка при обработке: {title}")

    # Обрабатываем все выбранные опции
    try:
        processing_tasks = [process_option(option) for option in selected_options]
        await asyncio.gather(*processing_tasks, return_exceptions=True)

        await send_telegram_message_http(chat_id, "🎉 Обработка завершена!")
        logger.info(f"Завершена обработка для заметки {note_id}")

    except Exception as e:
        logger.error(f"Ошибка при обработке опций: {e}", exc_info=True)
        await send_telegram_message_http(chat_id, "❌ Ошибка при обработке некоторых опций.")


# --- Синхронная "обертка" для Celery ---
@celery_app.task(name='tasks.process_media_v2')
def process_media_v2(user_id, s3_key, metadata, platform_payload, **kwargs):
    """
    Celery задача для обработки медиа с правильным управлением event loop
    """
    try:
        # Создаем новый event loop для этой задачи
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Запускаем асинхронную обработку
            loop.run_until_complete(_async_process_media(user_id, s3_key, platform_payload, **kwargs))
        finally:
            # Правильно закрываем loop
            try:
                # Отменяем все оставшиеся задачи
                pending_tasks = asyncio.all_tasks(loop)
                for task in pending_tasks:
                    task.cancel()

                # Ждем завершения всех задач
                if pending_tasks:
                    loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))

            except Exception as cleanup_error:
                logger.warning(f"Ошибка при очистке задач: {cleanup_error}")
            finally:
                loop.close()

        logger.info(f"Задача Celery успешно завершена для {note_id}")

    except Exception as e:
        logger.critical(f"Критический сбой в задаче Celery: {e}", exc_info=True)
        # Попытаемся отправить сообщение об ошибке напрямую
        try:
            chat_id = platform_payload.get('chat_id')
            if chat_id:
                import requests
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                requests.post(url, json={
                    'chat_id': chat_id,
                    'text': '❌ Произошла критическая ошибка при обработке. Попробуйте еще раз.'
                }, timeout=10)
        except:
            pass  # Игнорируем ошибки при отправке сообщения об ошибке