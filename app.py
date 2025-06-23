# app.py
import os
import logging
from flask import Flask, request, jsonify, render_template  # <== ДОБАВЛЕН render_template
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

# Импорты сервисов
from services.message_handler import MessageHandler
from services.database import Database
from services.translation_service import TranslationService

app = Flask(__name__)

# --- Инициализация ---
try:
    logger.info("Initializing services for web process...")
    database = Database()
    translation_service = TranslationService()
    message_handler = MessageHandler(database=database, translation_service=translation_service)
    logger.info("✅ Web services initialized successfully.")
except Exception as e:
    logger.error(f"❌ CRITICAL INITIALIZATION ERROR: {e}", exc_info=True)
    message_handler = None

# --- Роуты ---

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({'status': 'Bot web service is running'})


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
                logger.error("MessageHandler was not initialized due to a startup error.")
        return 'OK', 200
    except Exception as e:
        logger.error(f"Critical error in webhook_handler: {e}", exc_info=True)
        return 'OK', 200

# ===> НАЧАЛО ИЗМЕНЕНИЙ <===

@app.route('/privacy')
def privacy_policy():
    """Renders the privacy policy page from a template."""
    return render_template('privacy_policy.html')


@app.route('/terms')
def terms_of_service():
    """Renders the terms of service page from a template."""
    return render_template('terms_of_service.html')

# ===> КОНЕЦ ИЗМЕНЕНИЙ <===


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)