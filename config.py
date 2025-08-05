# config.py - Простейшая конфигурация без pydantic
import os
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()


class Settings:
    """Простые настройки без pydantic"""

    def __init__(self):
        # Обязательные переменные
        self.TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
        self.OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

        # Опциональные
        self.WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://your-app.onrender.com')
        self.DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'

        # База данных
        self.MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/transcribe_bot')
        self.DATABASE_NAME = os.getenv('DATABASE_NAME', 'transcribe_bot')

        # S3 Storage
        self.S3_ENDPOINT_URL = os.getenv('S3_ENDPOINT_URL', '')
        self.S3_ACCESS_KEY_ID = os.getenv('S3_ACCESS_KEY_ID', '')
        self.S3_SECRET_ACCESS_KEY = os.getenv('S3_SECRET_ACCESS_KEY', '')
        self.S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME', '')

        # Redis
        self.REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')


# Создаем экземпляр настроек
settings = Settings()

# Проверяем обязательные переменные
if not settings.TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не установлен! Создайте .env файл с токеном бота.")

print(f"✅ Конфигурация загружена. Токен бота: {'*' * 10 + settings.TELEGRAM_TOKEN[-10:]}")

# Дополнительные константы
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