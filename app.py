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

        # Сначала проверим OpenAI отдельно
        logger.info("Проверяем OpenAI...")
        try:
            import openai
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                raise ValueError("OPENAI_API_KEY не установлен")

            logger.info(f"OpenAI версия: {openai.__version__}")
            logger.info(f"API Key: {api_key[:10]}...")

            # Создаем клиент с абсолютным минимумом параметров
            client = openai.OpenAI(api_key=api_key)
            logger.info("✅ OpenAI клиент создан успешно")

        except Exception as e:
            logger.error(f"❌ Ошибка OpenAI: {e}")
            raise e

        # Импорты сервисов
        from services.database import Database
        logger.info("✅ Database импортирован")

        from services.language_detector import LanguageDetector
        logger.info("✅ LanguageDetector импортирован")

        from services.translation_service import TranslationService
        logger.info("✅ TranslationService импортирован")

        from services.audio_processor import AudioProcessor
        logger.info("✅ AudioProcessor импортирован")

        # Инициализация базы данных
        database = Database()
        logger.info("✅ Database инициализирован")

        # Инициализируем другие сервисы без TranscriptionService пока
        language_detector = LanguageDetector()
        logger.info("✅ LanguageDetector инициализирован")

        translation_service = TranslationService()
        logger.info("✅ TranslationService инициализирован")

        audio_processor = AudioProcessor()
        logger.info("✅ AudioProcessor инициализирован")

        # Попробуем создать TranscriptionService отдельно
        try:
            from services.transcription_service import TranscriptionService
            logger.info("TranscriptionService импортирован, создаем экземпляр...")
            transcription_service = TranscriptionService()
            logger.info("✅ TranscriptionService инициализирован")
        except Exception as e:
            logger.error(f"❌ Ошибка TranscriptionService: {e}")
            # Создаем заглушку
            transcription_service = None
            logger.info("⚠️ TranscriptionService отключен, используем заглушку")

        # Создаем остальные сервисы
        from services.media_handler import MediaHandler
        from services.message_handler import MessageHandler

        media_handler = MediaHandler(
            transcription_service=transcription_service,
            language_detector=language_detector,
            translation_service=translation_service,
            audio_processor=audio_processor,
            database=database
        )
        logger.info("✅ MediaHandler инициализирован")

        message_handler = MessageHandler(
            media_handler=media_handler,
            database=database
        )
        logger.info("✅ MessageHandler инициализирован")

        logger.info("🎉 Все сервисы успешно инициализированы")

    except Exception as e:
        logger.error(f"❌ Ошибка при инициализации сервисов: {e}")
        import traceback
        traceback.print_exc()
        raise e

    @app.route('/', methods=['GET'])
    def index():
        """Главная страница"""
        return jsonify({
            "status": "Bot is running",
            "message": "Messenger Transcribe Bot is active (Debug Mode)",
            "version": "1.0.0-debug",
            "transcription_available": transcription_service is not None,
            "endpoints": {
                "webhook": "/webhook",
                "health": "/api/health",
                "test": "/api/test"
            }
        })

    @app.route('/api/test', methods=['GET'])
    def test_services():
        """Тестирование сервисов"""
        results = {}

        try:
            # Тест OpenAI
            if transcription_service:
                results["transcription_service"] = "✅ Available"
            else:
                results["transcription_service"] = "❌ Not available"

            # Тест других сервисов
            results["language_detector"] = "✅ Available" if language_detector else "❌ Not available"
            results["translation_service"] = "✅ Available" if translation_service else "❌ Not available"
            results["database"] = "✅ Available" if database else "❌ Not available"

            return jsonify({
                "status": "test_complete",
                "services": results,
                "timestamp": "2025-06-18T13:30:00Z"
            })

        except Exception as e:
            return jsonify({
                "status": "test_failed",
                "error": str(e)
            }), 500

    @app.route('/api/health', methods=['GET'])
    def health_check():
        """Проверка здоровья приложения"""
        return jsonify({
            "status": "healthy",
            "message": "Debug mode active",
            "transcription": "available" if transcription_service else "disabled"
        })

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
    def webhook_handler():
        """Обработка webhook сообщений от Facebook"""
        try:
            data = request.get_json()
            logger.info(f"Получен webhook: {data}")

            if not transcription_service:
                logger.warning("TranscriptionService недоступен, отвечаем заглушкой")
                # Здесь можно отправить сообщение пользователю о временной недоступности

            return jsonify({"status": "ok"}), 200

        except Exception as e:
            logger.error(f"Ошибка при обработке webhook: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500

    return app


# Создаем приложение
app = create_app()

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    logger.info(f"Запуск отладочной версии на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=True)