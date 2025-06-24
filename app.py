# app.py
import os
import logging
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

# ===> НОВЫЕ ИМПОРТЫ <===
from services.message_handler import MessageHandler
from services.telegram_handler import TelegramHandler
from services.database import Database
from services.translation_service import TranslationService
from services.s3_service import S3Service

app = Flask(__name__)

# --- Инициализация ---
try:
    logger.info("Initializing services for web process...")
    database = Database()
    s3_service = S3Service()
    translation_service = TranslationService()

    # Инициализация обработчика для Messenger
    message_handler = MessageHandler(database=database, translation_service=translation_service)

    # ===> ИНИЦИАЛИЗАЦИЯ ОБРАБОТЧИКА ДЛЯ TELEGRAM <===
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
def health_check():
    return jsonify({'status': 'Bot web service is running'})


# --- Роуты для Messenger ---
@app.route('/webhook', methods=['GET'])
def webhook_verify():
    verify_token = os.getenv('VERIFY_TOKEN')
    if request.args.get('hub.verify_token') == verify_token:
        return request.args.get('hub.challenge', '')
    return 'Verification failed', 403


@app.route('/webhook', methods=['POST'])
def webhook_handler():
    try:
        data = request.get_json()
        if data and data.get('object') == 'page':
            if message_handler:
                message_handler.handle_message(data)
            else:
                logger.error("MessageHandler was not initialized.")
        return 'OK', 200
    except Exception as e:
        logger.error(f"Critical error in webhook_handler: {e}", exc_info=True)
        return 'OK', 200


# ===> НОВЫЙ РОУТ ДЛЯ TELEGRAM <===
@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook_handler():
    try:
        data = request.get_json()
        if data:
            if telegram_handler:
                telegram_handler.handle_update(data)
            else:
                logger.error("TelegramHandler was not initialized.")
        return 'OK', 200
    except Exception as e:
        logger.error(f"Critical error in telegram_webhook_handler: {e}", exc_info=True)
        return 'OK', 200


# --- Роуты для страниц Privacy Policy / Terms ---
@app.route('/privacy')
def privacy_policy():
    return render_template('privacy_policy.html')


@app.route('/terms')
def terms_of_service():
    return render_template('terms_of_service.html')


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)