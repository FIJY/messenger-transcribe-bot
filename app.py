# app.py
import os
import logging
import asyncio
import json
from quart import Quart, request, Response
from dotenv import load_dotenv

# Принудительно загружаем переменные окружения в самом начале
load_dotenv()

from services.telegram_handler import TelegramHandler
from services.database import Database
from services.s3_service import S3Service
from services.payment_service import PaymentService
from services.insight_service import InsightService
from services.translation_service import TranslationService
from services.downloader_service import DownloaderService
from services.business_analyzer_service import BusinessAnalyzerService
from services.youtube_service import YouTubeService
from services.message_queue_handler import MessageQueueHandler

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Quart(__name__)
telegram_handler = None
message_queue_handler = None


@app.before_serving
async def startup():
    global telegram_handler, message_queue_handler
    logger.info("Initializing services for web process...")
    try:
        database = Database()
        s3_service = S3Service()
        insight_service = InsightService()
        translation_service = TranslationService()
        downloader_service = DownloaderService()
        business_analyzer = BusinessAnalyzerService()
        youtube_service = YouTubeService()
        payment_service = PaymentService(
            bot=None, db=database, ui=None, localizer=None
        )

        telegram_handler = TelegramHandler(
            token=os.getenv('TELEGRAM_TOKEN'),
            database=database,
            s3_service=s3_service,
            payment_service=payment_service,
            insight_service=insight_service,
            translation_service=translation_service,
            downloader_service=downloader_service,
            business_analyzer=business_analyzer,
            youtube_service=youtube_service
        )
        payment_service.bot = telegram_handler.bot
        payment_service.ui = telegram_handler.ui
        payment_service.localizer = telegram_handler.localizer

        # Инициализируем обработчик очереди сообщений
        message_queue_handler = MessageQueueHandler(
            bot=telegram_handler.bot,
            database=database
        )

        await telegram_handler.set_bot_commands()

        # Запускаем обработку очереди сообщений
        await message_queue_handler.start_processing()

        logger.info("✅ Telegram Handler, Message Queue Handler и все сервисы инициализированы успешно.")

    except Exception as e:
        logger.critical(f"❌ КРИТИЧЕСКАЯ ОШИБКА ИНИЦИАЛИЗАЦИИ: {e}", exc_info=True)

    logger.info("✅ Web services initialized successfully.")


@app.after_serving
async def shutdown():
    """
    Корректно останавливаем сервисы при завершении
    """
    global message_queue_handler
    if message_queue_handler:
        logger.info("Останавливаем обработчик очереди сообщений...")
        await message_queue_handler.stop_processing()
    logger.info("✅ Сервисы корректно остановлены.")


# ИСПРАВЛЕНИЕ: Добавлена обертка для безопасной обработки обновлений
async def safe_handle_update(data):
    logger.info(">>> [safe_handle_update] Task started.")
    try:
        await telegram_handler.handle_update(data)
        logger.info("<<< [safe_handle_update] Task finished successfully.")
    except Exception as e:
        # Этот блок поймает любую ошибку и запишет ее в лог
        logger.error(f"!!! [safe_handle_update] Unhandled exception in handle_update task: {e}", exc_info=True)


@app.route('/telegram', methods=['POST'])
async def handle_telegram_webhook():
    logger.info("--> [/telegram] Webhook received a request.")
    if telegram_handler:
        data = await request.get_json()
        logger.info("--> [/telegram] JSON payload parsed. Creating background task for safe_handle_update.")
        # Используем безопасную обертку, чтобы не терять ошибки
        asyncio.create_task(safe_handle_update(data))
        logger.info("--> [/telegram] Background task created. Returning 200 OK to Telegram.")
    else:
        logger.error("!!! [/telegram] Telegram handler is not available. Cannot process update.")
    return Response(status=200)


@app.route('/health', methods=['GET'])
async def health_check():
    return Response("OK", status=200)


@app.route('/queue-stats', methods=['GET'])
async def queue_stats():
    """
    Эндпоинт для получения статистики очереди сообщений
    """
    if message_queue_handler:
        stats = message_queue_handler.get_queue_stats()
        return json.dumps(stats) if stats else Response("Error", status=500)
    return Response("Queue handler not available", status=503)


# Добавляем обработчик задач отправки результатов
async def handle_send_results_task():
    """
    Обрабатывает задачи отправки результатов из Celery
    """
    # Этот метод будет вызываться, когда Celery создает задачу send_results
    # Можно интегрировать с Celery через Redis или другую очередь
    pass


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))