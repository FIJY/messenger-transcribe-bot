import os
import logging
from flask import Flask
from dotenv import load_dotenv

# Импорт модулей приложения
from routes.webhook import webhook_bp
from routes.api import api_bp
from services.database import Database
from services.transcribe import TranscribeService
from services.payment import PaymentService

# Загрузка переменных окружения
load_dotenv()


def create_app():
    """Фабрика приложений Flask"""
    app = Flask(__name__)

    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Конфигурация приложения
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
    app.config['DEBUG'] = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

    # Инициализация сервисов
    init_services(app)

    # Регистрация blueprints
    app.register_blueprint(webhook_bp, url_prefix='/webhook')
    app.register_blueprint(api_bp, url_prefix='/api')

    # Главная страница
    @app.route('/')
    def home():
        return {
            "status": "Bot is running",
            "message": "Messenger Transcribe Bot is active",
            "version": "1.0.0",
            "endpoints": {
                "webhook": "/webhook",
                "health": "/api/health"
            }
        }

    return app


def init_services(app):
    """Инициализация сервисов приложения"""
    try:
        # Инициализация базы данных
        db = Database()
        app.db = db
        logging.info("Database service initialized")

        # Инициализация транскрипции
        transcriber = TranscribeService()
        app.transcriber = transcriber
        logging.info("Transcription service initialized")

        # Инициализация платежей
        payment = PaymentService()
        app.payment = payment
        logging.info("Payment service initialized")

    except Exception as e:
        logging.error(f"Failed to initialize services: {e}")
        raise


# Создание экземпляра приложения для Gunicorn
app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))

    logging.info(f"Starting Messenger Transcribe Bot on port {port}")
    app.run(
        host='0.0.0.0',
        port=port,
        debug=app.config['DEBUG']
    )