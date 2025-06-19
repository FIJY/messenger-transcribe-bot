# app.py - ИСПРАВЛЕННАЯ ВЕРСИЯ
import os
import logging
from flask import Flask, request, jsonify
import hmac
import hashlib
from datetime import datetime

# Загружаем переменные окружения из .env файла
try:
    from dotenv import load_dotenv

    load_dotenv()
    logging.info("✅ Переменные окружения загружены из .env файла")
except ImportError:
    logging.warning("⚠️ python-dotenv не установлен, используем системные переменные")
except Exception as e:
    logging.warning(f"⚠️ Не удалось загрузить .env файл: {e}")

# Импорты сервисов
from services.transcription_service import TranscriptionService
from services.translation_service import TranslationService
from services.media_handler import MediaHandler
from services.message_handler import MessageHandler
from services.database import Database

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создание Flask приложения
app = Flask(__name__)

# Инициализация сервисов при запуске
transcription_service = None
translation_service = None
media_handler = None
message_handler = None
database = None


def init_services():
    """Инициализация всех сервисов"""
    global transcription_service, translation_service, media_handler, message_handler, database

    try:
        # Инициализация сервисов в правильном порядке
        logger.info("Инициализируем сервисы...")

        transcription_service = TranscriptionService()
        translation_service = TranslationService()
        database = Database()

        # MediaHandler требует transcription_service и translation_service
        media_handler = MediaHandler(transcription_service, translation_service)

        # MessageHandler требует media_handler, database и translation_service
        message_handler = MessageHandler(media_handler, database, translation_service)

        logger.info("✅ Все сервисы успешно инициализированы")

    except Exception as e:
        logger.error(f"❌ Ошибка инициализации сервисов: {e}")
        raise


# Инициализируем сервисы при запуске
init_services()


@app.route('/', methods=['GET'])
def health_check():
    """Проверка здоровья приложения"""
    return jsonify({
        'status': 'Bot is running',
        'message': 'Messenger Transcribe Bot is active',
        'version': '1.0.0',
        'endpoints': {
            'health': '/api/health',
            'webhook': '/webhook'
        }
    })


@app.route('/api/health', methods=['GET'])
def api_health():
    """API для проверки здоровья"""
    try:
        # Проверяем подключение к базе данных
        if database:
            database.client.admin.command('ping')
            db_status = "connected"
        else:
            db_status = "not_initialized"

        return jsonify({
            'status': 'healthy',
            'database': db_status,
            'services': {
                'transcription': transcription_service is not None,
                'translation': translation_service is not None,
                'media_handler': media_handler is not None,
                'message_handler': message_handler is not None
            }
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500


@app.route('/webhook', methods=['GET'])
def webhook_verify():
    """Верификация webhook для Facebook"""
    try:
        verify_token = os.getenv('VERIFY_TOKEN', '12345')

        if request.args.get('hub.verify_token') == verify_token:
            logger.info("Webhook успешно верифицирован")
            return request.args.get('hub.challenge', '')
        else:
            logger.error("Неверный verify token")
            return 'Verification failed', 403

    except Exception as e:
        logger.error(f"Ошибка верификации webhook: {e}")
        return 'Verification error', 500


@app.route('/webhook', methods=['POST'])
def webhook_handler():
    """Обработчик webhook сообщений от Facebook"""
    try:
        data = request.get_json()
        if not verify_webhook_signature(request):
            logger.warning("Неверная подпись webhook")
            return 'Invalid signature', 403

        if data.get('object') == 'page':
            for entry in data.get('entry', []):
                for messaging_event in entry.get('messaging', []):
                    if message_handler:
                        # Обрабатываем сообщение
                        message_handler.handle_message(messaging_event)
                    else:
                        logger.error("MessageHandler не инициализирован, не могу обработать событие.")

        return 'OK', 200

    except Exception as e:
        # 🔧 ГЛАВНОЕ ИЗМЕНЕНИЕ:
        # exc_info=True добавит в лог полную трассировку ошибки.
        # Это именно то, что нам нужно для диагностики.
        logger.error(f"Критическая ошибка в webhook_handler: {e}", exc_info=True)
        return 'OK', 200 # Возвращаем 200, чтобы Facebook не повторял запросы


def verify_webhook_signature(request):
    """Проверяет подпись webhook от Facebook"""
    try:
        app_secret = os.getenv('APP_SECRET')
        if not app_secret:
            logger.warning("APP_SECRET не установлен, пропускаем проверку подписи")
            return True

        signature = request.headers.get('X-Hub-Signature-256', '')
        if not signature:
            logger.warning("Отсутствует подпись в заголовках")
            return True

        # Удаляем префикс 'sha256='
        signature = signature.replace('sha256=', '')

        # Вычисляем ожидаемую подпись
        expected_signature = hmac.new(
            app_secret.encode('utf-8'),
            request.get_data(),
            hashlib.sha256
        ).hexdigest()

        # Сравниваем подписи
        return hmac.compare_digest(signature, expected_signature)

    except Exception as e:
        logger.error(f"Ошибка проверки подписи: {e}")
        return False


@app.route('/test', methods=['GET'])
def test_services():
    """Тестирование сервисов"""
    try:
        results = {}

        # Тест TranscriptionService
        if transcription_service:
            supported_langs = transcription_service.get_supported_languages()
            results['transcription'] = {
                'status': 'ok',
                'supported_languages_count': len(supported_langs)
            }
        else:
            results['transcription'] = {'status': 'not_initialized'}

        # Тест TranslationService
        if translation_service:
            test_translation = translation_service.translate_text("Hello", "ru", "en")
            results['translation'] = {
                'status': 'ok' if test_translation.get('success') else 'error',
                'test_result': test_translation
            }
        else:
            results['translation'] = {'status': 'not_initialized'}

        # Тест Database
        if database:
            try:
                stats = database.get_global_stats()
                results['database'] = {
                    'status': 'ok',
                    'global_stats': stats
                }
            except Exception as e:
                results['database'] = {
                    'status': 'error',
                    'error': str(e)
                }
        else:
            results['database'] = {'status': 'not_initialized'}

        return jsonify({
            'test_results': results,
            'timestamp': str(datetime.utcnow())
        })

    except Exception as e:
        logger.error(f"Ошибка тестирования: {e}")
        return jsonify({
            'error': str(e),
            'timestamp': str(datetime.utcnow())
        }), 500


if __name__ == '__main__':
    # Проверяем переменные окружения
    required_env_vars = [
        'OPENAI_API_KEY',
        'MONGODB_URI',
        'PAGE_ACCESS_TOKEN',
        'VERIFY_TOKEN'
    ]

    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        logger.error(f"Отсутствуют переменные окружения: {missing_vars}")
        exit(1)

    # Запускаем приложение
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'

    logger.info(f"🚀 Запускаем бот на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)