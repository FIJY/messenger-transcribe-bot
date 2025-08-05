# config.py - Минимальная конфигурация для запуска
import os
from pydantic import BaseSettings


class Settings(BaseSettings):
    """Минимальные настройки для запуска бота"""

    # Обязательные для работы
    TELEGRAM_TOKEN: str
    OPENAI_API_KEY: str = ""

    # Опциональные (с дефолтными значениями)
    WEBHOOK_URL: str = "https://your-app.onrender.com"
    DEBUG: bool = False

    # База данных (опционально)
    MONGODB_URI: str = "mongodb://localhost:27017/transcribe_bot"
    DATABASE_NAME: str = "transcribe_bot"

    # S3 Storage (опционально)
    S3_ENDPOINT_URL: str = ""
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    S3_BUCKET_NAME: str = ""

    # Redis (опционально)
    REDIS_URL: str = "redis://localhost:6379/0"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Создаем экземпляр настроек
settings = Settings()

# Дополнительные константы (пока заглушки)
PLANS = {
    "free": {
        "name": "Бесплатный",
        "minutes_limit": 60,
        "processing_options": 1,
        "features": ["Транскрипция до 5 минут"]
    }
}

SUPPORTED_LANGUAGES = {
    "ru": {"name": "Russian", "flag": "🇷🇺", "native": "Русский"},
    "en": {"name": "English", "flag": "🇺🇸", "native": "English"}
}

FILE_LIMITS = {
    "free": {
        "max_size_mb": 25,
        "max_duration_minutes": 5,
        "supported_formats": ["mp3", "wav", "ogg", "m4a"]
    }
}