import os
import logging
from flask import Flask, request, jsonify
from services.database import Database
from services.transcription_service import TranscriptionService
from services.translation_service import TranslationService
from services.media_handler import MediaHandler
from services.message_handler import MessageHandler
from services.payment import PaymentService

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_app():
    """Создает и настраивает Flask приложение"""
    app = Flask(__name__)

    # Проверяем обязательные переменные окружения
    required_env_vars = ['OPENAI_API_KEY', 'MONGODB_URI', 'VERIFY_TOKEN', 'PAGE_ACCESS_TOKEN']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]

    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        raise ValueError(f"Missing required environment variables: {missing_vars}")

    try:
        # Инициализируем сервисы
        logger.info("Initializing services...")

        # База данных
        db = Database()

        # Основные сервисы
        transcription_service = TranscriptionService()
        translation_service = TranslationService()

        # Медиа обработчик
        media_handler = MediaHandler(transcription_service, translation_service)

        # Обработчик сообщений (правильный порядок параметров!)
        message_handler = MessageHandler(media_handler, db, translation_service)

        # Платежный сервис (создаем но не используем в MessageHandler)
        payment_service = PaymentService()

        logger.info("All services initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise

    @app.route('/', methods=['GET'])
    def home():
        """Главная страница для проверки работы сервиса"""
        return jsonify({
            'status': 'active',
            'service': 'Messenger Transcribe Bot',
            'version': '1.0.0',
            'endpoints': {
                'webhook': '/webhook',
                'health': '/health'
            }
        })

    @app.route('/health', methods=['GET'])
    def health():
        """Endpoint для проверки здоровья сервиса"""
        try:
            # Проверяем подключение к базе данных
            db.client.admin.command('ping')

            return jsonify({
                'status': 'healthy',
                'database': 'connected',
                'services': 'operational'
            })
        except Exception as health_error:
            logger.error(f"Health check failed: {health_error}")
            return jsonify({
                'status': 'unhealthy',
                'error': str(health_error)
            }), 500

    @app.route('/webhook', methods=['GET', 'POST'])
    def webhook():
        """Webhook для Facebook Messenger"""
        if request.method == 'GET':
            return verify_webhook()
        elif request.method == 'POST':
            return handle_webhook()

    def verify_webhook():
        """Верификация webhook для Facebook"""
        try:
            verify_token = request.args.get('hub.verify_token')
            challenge = request.args.get('hub.challenge')

            expected_token = os.getenv('VERIFY_TOKEN')

            if verify_token == expected_token:
                logger.info("Webhook verified successfully")
                return challenge
            else:
                logger.warning(f"Invalid verify token: {verify_token}")
                return 'Invalid verify token', 403

        except Exception as verify_error:
            logger.error(f"Error in webhook verification: {verify_error}")
            return 'Error', 500

    def handle_webhook():
        """Обработка входящих сообщений от Facebook"""
        try:
            data = request.get_json()

            if not data:
                logger.warning("Received empty webhook data")
                return 'No data', 400

            logger.info(f"Received webhook data: {data}")

            # Обрабатываем каждое входящее сообщение
            if data.get('object') == 'page':
                for entry in data.get('entry', []):
                    for messaging_event in entry.get('messaging', []):
                        try:
                            # Игнорируем эхо сообщения (отправленные ботом)
                            if messaging_event.get('message', {}).get('is_echo'):
                                continue

                            # Обрабатываем сообщение
                            success = message_handler.handle_message(messaging_event)

                            if not success:
                                logger.warning(f"Failed to handle message: {messaging_event}")

                        except Exception as msg_error:
                            logger.error(f"Error handling individual message: {msg_error}")
                            continue

            return 'OK', 200

        except Exception as webhook_error:
            logger.error(f"Error handling webhook: {webhook_error}")
            return 'Error', 500

    @app.route('/stats', methods=['GET'])
    def get_stats():
        """Endpoint для получения статистики (для разработки)"""
        try:
            stats = db.get_global_stats()
            return jsonify(stats)
        except Exception as stats_error:
            logger.error(f"Error getting stats: {stats_error}")
            return jsonify({'error': str(stats_error)}), 500

    @app.errorhandler(404)
    def not_found(_):
        """Обработчик 404 ошибок"""
        return jsonify({'error': 'Endpoint not found'}), 404

    @app.errorhandler(500)
    def internal_error(_):
        """Обработчик 500 ошибок"""
        return jsonify({'error': 'Internal server error'}), 500

    # Добавляем middleware для логирования запросов
    @app.before_request
    def log_request_info():
        logger.debug(f"Request: {request.method} {request.url}")

    @app.after_request
    def log_response_info(response):
        logger.debug(f"Response: {response.status_code}")
        return response

    return app


# Создаем приложение
app = create_app()

if __name__ == '__main__':
    # Запуск для разработки
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)