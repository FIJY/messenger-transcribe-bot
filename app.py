# app.py
import os
import logging
import asyncio
from quart import Quart, request, jsonify
from dotenv import load_dotenv

from services.database import Database
from services.s3_service import S3Service
from services.payment_service import PaymentService
from services.telegram_handler import TelegramHandler
from services.insight_service import InsightService
from services.translation_service import TranslationService
from telegram import Bot

# Загружаем переменные окружения
load_dotenv()

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Инициализация сервисов ---
logger.info("Initializing services for web process...")
try:
    database = Database()
    s3_service = S3Service()
    insight_service = InsightService()
    translation_service = TranslationService()
    telegram_token = os.getenv('TELEGRAM_TOKEN')

    if not telegram_token:
        raise ValueError("TELEGRAM_TOKEN is not set. Web service cannot start.")

    bot_instance = Bot(token=telegram_token)
    payment_service = PaymentService(bot=bot_instance, database=database)

    telegram_handler = TelegramHandler(
        token=telegram_token,
        database=database,
        s3_service=s3_service,
        payment_service=payment_service,
        insight_service=insight_service,
        translation_service=translation_service
    )
    logger.info("✅ Telegram Handler and services initialized successfully.")
except Exception as e:
    logger.error(f"❌ CRITICAL INITIALIZATION ERROR: {e}", exc_info=True)
    telegram_handler = None

# Создаем экземпляр веб-приложения Quart
app = Quart(__name__)


@app.before_serving
async def startup():
    """Выполняется один раз перед запуском сервера."""
    if telegram_handler:
        loop = asyncio.get_event_loop()
        # Устанавливаем команды бота при старте
        loop.create_task(telegram_handler.set_bot_commands())
        logger.info("✅ Web services initialized successfully.")
    else:
        logger.error("❌ Web service started, but Telegram Handler is not available due to an initialization error.")


@app.route('/')
async def health_check():
    """Простая проверка, что сервис жив."""
    return jsonify({"status": "ok"}), 200


@app.route('/webhook/telegram', methods=['POST'])
async def telegram_webhook():
    """Принимает обновления от Telegram."""
    if not telegram_handler:
        return jsonify({"status": "error", "message": "Handler not initialized"}), 500

    data = await request.get_json()
    # Обрабатываем обновление в фоновом режиме, чтобы не задерживать ответ Telegram
    asyncio.create_task(telegram_handler.handle_update(data))
    return jsonify({"status": "ok"})

# Этот блок больше не нужен, так как Hypercorn запускает приложение
# if __name__ == '__main__':
#     app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)))