import os
import logging
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import asyncio
from functools import wraps

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_app():
    """Создание и настройка Flask приложения"""
    app = Flask(__name__)

    # Глобальные переменные для сервисов
    global message_handler
    message_handler = None

    try:
        logger.info("Инициализация сервисов...")

        # Импорты сервисов
        from services.database import Database
        from services.transcription_service import TranscriptionService
        from services.language_detector import LanguageDetector
        from services.translation_service import TranslationService
        from services.audio_processor import AudioProcessor
        from services.media_handler import MediaHandler
        from services.message_handler import MessageHandler

        # Инициализация сервисов в правильном порядке
        database = Database()

        # Инициализируем остальные сервисы
        transcription_service = TranscriptionService()
        language_detector = LanguageDetector()
        translation_service = TranslationService()
        audio_processor = AudioProcessor()

        # Создаем MediaHandler
        media_handler = MediaHandler(
            transcription_service=transcription_service,
            language_detector=language_detector,
            translation_service=translation_service,
            audio_processor=audio_processor,
            database=database
        )

        # Создаем MessageHandler
        message_handler = MessageHandler(
            media_handler=media_handler,
            database=database
        )

        logger.info("Все сервисы успешно инициализированы")

    except Exception as e:
        logger.error(f"Ошибка при инициализации сервисов: {e}")
        raise e

    def async_route(f):
        """Декоратор для асинхронных маршрутов"""

        @wraps(f)
        def decorated_function(*args, **kwargs):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(f(*args, **kwargs))
            finally:
                loop.close()

        return decorated_function

    @app.route('/', methods=['GET'])
    def index():
        """Главная страница"""
        return jsonify({
            "status": "Bot is running",
            "message": "Messenger Transcribe Bot is active",
            "version": "1.0.0",
            "endpoints": {
                "webhook": "/webhook",
                "health": "/api/health"
            }
        })

    @app.route('/api/health', methods=['GET'])
    def health_check():
        """Проверка здоровья приложения"""
        try:
            # Проверяем подключение к базе данных
            if message_handler and message_handler.database:
                # Простая проверка подключения
                test_result = message_handler.database.db.command('ping')
                if test_result.get('ok') == 1.0:
                    return jsonify({
                        "status": "healthy",
                        "database": "connected",
                        "services": "operational",
                        "timestamp": "2025-06-18T13:16:18Z"
                    })

            return jsonify({
                "status": "partial",
                "database": "unknown",
                "services": "operational",
                "timestamp": "2025-06-18T13:16:18Z"
            }), 206

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return jsonify({
                "status": "unhealthy",
                "error": str(e),
                "timestamp": "2025-06-18T13:16:18Z"
            }), 500

    @app.route('/webhook', methods=['GET'])
    def webhook_verify():
        """Верификация webhook для Facebook"""
        verify_token = os.getenv('VERIFY_TOKEN', '12345')
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')

        if mode == 'subscribe' and token == verify_token:
            logger.info("Webhook успешно верифицирован")
            return challenge
        else:
            logger.warning("Неудачная попытка верификации webhook")
            return 'Forbidden', 403

    @app.route('/webhook', methods=['POST'])
    @async_route
    async def webhook_handler():
        """Обработка webhook сообщений от Facebook"""
        try:
            data = request.get_json()

            if not data:
                logger.warning("Получены пустые данные webhook")
                return jsonify({"status": "error", "message": "No data"}), 400

            logger.info(f"Получен webhook: {data}")

            # Проверяем, что это сообщение от Messenger
            if data.get('object') == 'page':
                entries = data.get('entry', [])

                for entry in entries:
                    messaging_events = entry.get('messaging', [])

                    for event in messaging_events:
                        if message_handler:
                            await message_handler.handle_message(event)
                        else:
                            logger.error("MessageHandler не инициализирован")

            return jsonify({"status": "ok"}), 200

        except Exception as e:
            logger.error(f"Ошибка при обработке webhook: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/api/stats', methods=['GET'])
    def get_stats():
        """Получение статистики бота"""
        try:
            if message_handler and message_handler.database:
                # Получаем основную статистику
                stats = {
                    "total_users": 0,
                    "total_transcriptions": 0,
                    "active_users_today": 0,
                    "status": "operational"
                }

                # Можно добавить реальные запросы к БД
                # stats = message_handler.database.get_stats()

                return jsonify(stats)
            else:
                return jsonify({"error": "Database not available"}), 503

        except Exception as e:
            logger.error(f"Ошибка при получении статистики: {e}")
            return jsonify({"error": str(e)}), 500

    @app.errorhandler(404)
    def not_found(error):
        """Обработчик 404 ошибки"""
        return jsonify({"error": "Endpoint not found"}), 404

    @app.errorhandler(500)
    def internal_error(error):
        """Обработчик 500 ошибки"""
        logger.error(f"Internal server error: {error}")
        return jsonify({"error": "Internal server error"}), 500

    return app


# Создаем приложение
app = create_app()

if __name__ == '__main__':
    # Запуск в режиме разработки
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

    logger.info(f"Запуск приложения на порту {port}, debug={debug}")
    app.run(host='0.0.0.0', port=port, debug=debug)