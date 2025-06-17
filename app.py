import os
import logging
from flask import Flask
from dotenv import load_dotenv

# Импорт модулей приложения
from routes.webhook import webhook_bp
from routes.api import api_bp
from services.database import Database
from services.payment import PaymentService
from services.message_handler import MessageHandler

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def create_app():
    """Фабрика приложений Flask"""
    app = Flask(__name__)

    # Конфигурация приложения
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')

    # Инициализация сервисов
    db = Database()
    logger.info("Database service initialized")

    payment = PaymentService()
    logger.info("Payment service initialized")

    # Инициализация обработчика сообщений
    message_handler = MessageHandler(db, payment)

    # Сохраняем обработчик в конфигурации для доступа из blueprint
    app.config['message_handler'] = message_handler

    # Регистрация blueprints
    app.register_blueprint(webhook_bp)
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

    logger.info(f"Starting Messenger Transcribe Bot on port {os.getenv('PORT', 5000)}")

    return app


# Создаем экземпляр приложения
app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)