# app.py
import os
import logging
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

from services.message_handler import MessageHandler
from services.database import Database

app = Flask(__name__)

# --- Инициализация ---
# Эта секция кода выполняется один раз при запуске каждого воркера Gunicorn
try:
    logger.info("Инициализация сервисов для веб-процесса...")
    database = Database()
    message_handler = MessageHandler(database=database)
    logger.info("✅ Веб-сервисы успешно инициализированы.")
except Exception as e:
    logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА ИНИЦИАЛИЗАЦИИ: {e}", exc_info=True)
    message_handler = None # Явно указываем, что инициализация провалена
# --- Конец инициализации ---

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
                logger.error("MessageHandler не был инициализирован из-за ошибки при запуске.")
        return 'OK', 200
    except Exception as e:
        logger.error(f"Критическая ошибка в webhook_handler: {e}", exc_info=True)
        return 'OK', 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)