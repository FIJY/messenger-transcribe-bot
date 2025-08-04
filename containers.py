# containers.py
from dependency_injector import containers, providers

# Импортируем все необходимое
from config import settings
from services.database import Database
from services.telegram_service import TelegramService
from telegram_handler import TelegramHandler  # <-- Вот этот импорт

class Container(containers.DeclarativeContainer):
    """Контейнер зависимостей."""

    config = providers.Object(settings)

    db_service = providers.Singleton(
        Database,
        mongo_uri=config.provided.MONGODB_URI,
    )

    telegram_service = providers.Singleton(
        TelegramService,
        token=config.provided.TELEGRAM_TOKEN
    )

    telegram_handler = providers.Factory(
        TelegramHandler,
        db_service=db_service,
        telegram_service=telegram_service,
    )