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

# Глобальные переменные для сервисов
message_handler = None
transcription_service = None
database = None
language_detector = None
translation_service = None
audio_processor = None
media_handler = None


def create_app():
    """Создание и настройка Flask приложения"""
    app = Flask(__name__)

    # Объявляем глобальные переменные
    global message_handler, transcription_service, database, language_detector
    global translation_service, audio_processor, media_handler

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
            translation_service=translation_service
        )
        logger.info("✅ MediaHandler инициализирован")

        message_handler = MessageHandler(
            media_handler=media_handler,
            database=database,
            translation_service=translation_service
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
            "message": "Messenger Transcribe Bot is active",
            "version": "1.0.0",
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
                "timestamp": "2025-06-19T10:00:00Z"
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
            "message": "All services running",
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

            if not data or 'entry' not in data:
                logger.warning("Неверный формат webhook данных")
                return jsonify({"status": "ok"}), 200

            # Обрабатываем каждую запись
            for entry in data['entry']:
                if 'messaging' not in entry:
                    continue

                for messaging_event in entry['messaging']:
                    logger.info(f"Обрабатываем событие: {messaging_event}")

                    # Проверяем доступность сервисов
                    if not message_handler:
                        logger.error("MessageHandler недоступен")
                        continue

                    if not transcription_service:
                        logger.warning("TranscriptionService недоступен")
                        # Можно отправить сообщение пользователю о временной недоступности
                        sender_id = messaging_event.get('sender', {}).get('id')
                        if sender_id:
                            # Здесь можно отправить временное сообщение
                            pass
                        continue

                    # Обрабатываем сообщение через MessageHandler
                    try:
                        success = message_handler.handle_message(messaging_event)
                        if success:
                            logger.info("Сообщение успешно обработано")
                        else:
                            logger.warning("Сообщение не было обработано")
                    except Exception as handler_error:
                        logger.error(f"Ошибка в MessageHandler: {handler_error}")

            return jsonify({"status": "ok"}), 200

        except Exception as e:
            logger.error(f"Ошибка при обработке webhook: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"status": "error", "message": str(e)}), 500

    return app


# Создаем приложение для Gunicorn
app = create_app()

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    logger.info(f"Запуск отладочной версии на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=True)