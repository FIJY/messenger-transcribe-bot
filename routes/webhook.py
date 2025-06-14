import os
import logging
from flask import Blueprint, request, current_app
from services.message_handler import MessageHandler

webhook_bp = Blueprint('webhook', __name__)
logger = logging.getLogger(__name__)

# Конфигурация
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN')


@webhook_bp.route('', methods=['GET'])
def verify_webhook():
    """Верификация webhook для Facebook"""
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    logger.info(f"Webhook verification request with token: {token}")

    if token == VERIFY_TOKEN:
        logger.info('Webhook verified successfully')
        return challenge

    logger.warning('Invalid verification token')
    return 'Invalid token', 403


@webhook_bp.route('', methods=['POST'])
def handle_webhook():
    """Обработка входящих сообщений"""
    try:
        data = request.json
        logger.info(f"Received webhook data: {data}")

        if data.get('object') == 'page':
            handler = MessageHandler(
                db=current_app.db,
                transcriber=current_app.transcriber,
                payment=current_app.payment
            )

            for entry in data['entry']:
                for messaging_event in entry['messaging']:
                    handler.handle_messaging_event(messaging_event)

        return 'OK', 200

    except Exception as e:
        logger.error(f"Error handling webhook: {e}")
        return 'Error', 500