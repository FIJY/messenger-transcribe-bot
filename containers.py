# containers.py
from dependency_injector import containers, providers
from openai import OpenAI

from config import settings
from services.database import Database
from services.s3_service import S3Service
from services.telegram_service import TelegramService
from services.transcription_service import TranscriptionService
from services.insight_service import InsightService
from services.payment_service import PaymentService
from telegram_handler import TelegramHandler


# ... и другие ваши сервисы, если они есть

class Container(containers.DeclarativeContainer):
    """
    Главный контейнер зависимостей для всего приложения.
    Он создает и управляет жизненным циклом всех сервисов.
    """
    # 1. Конфигурация
    # Предоставляем доступ к объекту настроек для всех сервисов
    config = providers.Object(settings)

    # 2. Клиенты внешних сервисов (Singleton - один экземпляр на все приложение)
    openai_client = providers.Singleton(
        OpenAI,
        api_key=config.openai.openai_api_key
    )

    # 3. Основные сервисы
    db_service = providers.Singleton(
        Database,
        mongo_uri=config.mongo.mongodb_uri,
        db_name=config.mongo.db_name
    )

    s3_service = providers.Singleton(
        S3Service,
        endpoint_url=config.s3.r2_endpoint_url,
        access_key_id=config.s3.r2_access_key_id,
        secret_access_key=config.s3.r2_secret_access_key,
        bucket_name=config.s3.r2_bucket_name
    )

    telegram_service = providers.Singleton(
        TelegramService,
        token=config.bot.telegram_token
    )

    transcription_service = providers.Singleton(
        TranscriptionService,
        openai_client=openai_client
    )

    insight_service = providers.Singleton(
        InsightService,
        openai_client=openai_client
    )

    payment_service = providers.Factory(  # Factory - новый экземпляр при каждом запросе
        PaymentService
    )

    # 4. Главный обработчик, который зависит от других сервисов
    # Контейнер автоматически подставит сюда созданные выше экземпляры
    telegram_handler = providers.Factory(
        TelegramHandler,
        telegram_service=telegram_service,
        db_service=db_service,
        payment_service=payment_service,
    )