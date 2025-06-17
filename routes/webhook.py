import os
import logging
from flask import Blueprint, request, current_app
from services.message_handler import MessageHandler

webhook_bp = Blueprint('webhook', __name__)
logger = logging.getLogger(__name__)

# Конфигурация
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN', '12345')


@webhook_bp.route('/webhook', methods=['GET'])
def verify_webhook():
    """Верификация webhook от Facebook"""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode and token:
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            logger.info('Webhook verified')
            return challenge, 200
        else:
            logger.error('Webhook verification failed')
            return 'Forbidden', 403

    return 'Bad Request', 400


@webhook_bp.route('/webhook', methods=['POST'])
def handle_webhook():
    """Обработка входящих сообщений"""
    data = request.get_json()

    if data and data.get('object') == 'page':
        logger.info(f"Received webhook data: {data}")

        # Получаем обработчик сообщений из контекста приложения
        message_handler = current_app.config['message_handler']

        # Обрабатываем webhook
        message_handler.handle_webhook(data)

        return 'ok', 200

    return 'Bad Request', 400