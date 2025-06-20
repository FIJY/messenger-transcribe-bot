# app.py
import os
import logging
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from services.message_handler import MessageHandler
from services.database import Database

app = Flask(__name__)

# Инициализация сервисов, нужных только для веб-процесса
try:
    logger.info("Инициализируем сервисы для веб-процесса...")
    database = Database()
    message_handler = MessageHandler(database=database)
    logger.info("✅ Веб-сервисы успешно инициализированы")
except Exception as e:
    logger.error(f"❌ Ошибка инициализации веб-сервисов: {e}", exc_info=True)
    message_handler = None

@app.route('/', methods=['GET'])
def health_check():
    """Проверка здоровья приложения"""
    return jsonify({
        'status': 'Bot is running',
        'message': 'Messenger Transcribe Bot is active',
        'version': '1.1.0 (проверяем деплой)', # <--- ИЗМЕНИТЕ ЭТУ СТРОКУ
        'endpoints': {
            'health': '/api/health',
            'webhook': '/webhook'
        }
    })


@app.route('/webhook', methods=['GET'])
def webhook_verify():
    verify_token = os.getenv('VERIFY_TOKEN')
    if request.args.get('hub.verify_token') == verify_token:
        logger.info("Webhook верифицирован")
        return request.args.get('hub.challenge', '')
    logger.error("Неверный verify token")
    return 'Verification failed', 403

@app.route('/webhook', methods=['POST'])
def webhook_handler():
    try:
        if message_handler:
            message_handler.handle_message(request.get_json())
        else:
            logger.error("MessageHandler не инициализирован.")
        return 'OK', 200
    except Exception as e:
        logger.error(f"Критическая ошибка в webhook_handler: {e}", exc_info=True)
        return 'OK', 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)