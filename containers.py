# containers.py
from dependency_injector import containers, providers

# Правильные импорты из файлов и пакетов
from config import settings
from services.database import Database
from services.telegram_service import TelegramService
from telegram_handler import TelegramHandler


class Container(containers.DeclarativeContainer):
    """Контейнер зависимостей."""

    # Чтобы IDE понимала типы, добавим type_hint
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
        telegram_service=telegram_service,
        db_service=db_service,
    )