# app.py
import os
import logging
import asyncio
from quart import Quart, request, Response
from dotenv import load_dotenv

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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Quart(__name__)
telegram_handler = None

@app.before_serving
async def startup():
    global telegram_handler
    logger.info("Initializing services for web process...")
    try:
        database = Database()
        s3_service = S3Service()
        insight_service = InsightService()
        translation_service = TranslationService()
        downloader_service = DownloaderService()
        business_analyzer = BusinessAnalyzerService()
        youtube_service = YouTubeService()
        payment_service = PaymentService(bot=None, db=database, ui=None, localizer=None)

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

        await telegram_handler.set_bot_commands()
        logger.info("✅ Telegram Handler and services initialized successfully.")
    except Exception as e:
        logger.critical(f"❌ CRITICAL INITIALIZATION ERROR: {e}", exc_info=True)
    logger.info("✅ Web services initialized successfully.")

async def safe_handle_update(data):
    logger.info(">>> Entering safe_handle_update task.")
    try:
        await telegram_handler.handle_update(data)
        logger.info("<<< Exiting safe_handle_update task successfully.")
    except Exception as e:
        logger.error(f"!!! Unhandled exception in handle_update task: {e}", exc_info=True)

@app.route('/telegram', methods=['POST'])
async def handle_telegram_webhook():
    logger.info("--> Received request on /telegram webhook.")
    if telegram_handler:
        data = await request.get_json()
        logger.info("--> Creating background task for handle_update.")
        asyncio.create_task(safe_handle_update(data))
        logger.info("--> Background task created. Returning 200 OK.")
    else:
        logger.error("Telegram handler is not available. Cannot process update.")
    return Response(status=200)

@app.route('/health', methods=['GET'])
async def health_check():
    return Response("OK", status=200)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
