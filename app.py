# app.py
import os
import logging
import asyncio
# ===> ИЗМЕНЕНИЕ: Flask -> Quart <===
from quart import Quart, request, jsonify, render_template
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

from services.message_handler import MessageHandler
from services.telegram_handler import TelegramHandler
from services.database import Database
from services.translation_service import TranslationService
from services.s3_service import S3Service

# ===> ИЗМЕНЕНИЕ: app = Flask(__name__) -> app = Quart(__name__) <===
app = Quart(__name__)

# --- Инициализация ---
# ... (этот блок без изменений) ...
try:
    logger.info("Initializing services for web process...")
    database = Database()
    s3_service = S3Service()
    translation_service = TranslationService()
    message_handler = MessageHandler(database=database, translation_service=translation_service)
    telegram_token = os.getenv('TELEGRAM_TOKEN')
    if telegram_token:
        telegram_handler = TelegramHandler(token=telegram_token, database=database, s3_service=s3_service)
        logger.info("✅ Telegram Handler initialized successfully.")
    else:
        telegram_handler = None
        logger.warning("TELEGRAM_TOKEN not found. Telegram bot will be disabled.")
    logger.info("✅ Web services initialized successfully.")
except Exception as e:
    logger.error(f"❌ CRITICAL INITIALIZATION ERROR: {e}", exc_info=True)
    message_handler = None
    telegram_handler = None

# --- Роуты ---

@app.route('/', methods=['GET'])
async def health_check(): # <== Добавляем async
    return jsonify({'status': 'Bot web service is running'})

@app.route('/webhook', methods=['GET'])
async def webhook_verify(): # <== Добавляем async
    verify_token = os.getenv('VERIFY_TOKEN')
    if request.args.get('hub.verify_token') == verify_token:
        return request.args.get('hub.challenge', '')
    return 'Verification failed', 403

@app.route('/webhook', methods=['POST'])
async def webhook_handler(): # <== Добавляем async
    try:
        data = await request.get_json() # <== Добавляем await
        if data and data.get('object') == 'page':
            if message_handler:
                # message_handler должен быть асинхронным, но пока оставим как есть
                # для обратной совместимости. Если что, поправим его следующим.
                message_handler.handle_message(data)
            else:
                logger.error("MessageHandler was not initialized.")
        return 'OK', 200
    except Exception as e:
        logger.error(f"Critical error in webhook_handler: {e}", exc_info=True)
        return 'OK', 200

@app.route('/telegram_webhook', methods=['POST'])
async def telegram_webhook_handler(): # <== Добавляем async
    try:
        data = await request.get_json() # <== Добавляем await
        if data:
            if telegram_handler:
                # ===> ГЛАВНОЕ ИЗМЕНЕНИЕ: Убираем asyncio.run() <===
                await telegram_handler.handle_update(data)
            else:
                logger.error("TelegramHandler was not initialized.")
        return 'OK', 200
    except Exception as e:
        logger.error(f"Critical error in telegram_webhook_handler: {e}", exc_info=True)
        return 'OK', 200

@app.route('/privacy')
async def privacy_policy(): # <== Добавляем async
    return await render_template('privacy_policy.html')

@app.route('/terms')
async def terms_of_service(): # <== Добавляем async
    return await render_template('terms_of_service.html')

# Убираем if __name__ == '__main__' - Gunicorn/Hypercorn запускают приложение иначе