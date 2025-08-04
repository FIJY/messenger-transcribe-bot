# config/settings.py
from pydantic import BaseSettings

class Settings(BaseSettings):
    """
    Централизованные настройки приложения.
    Pydantic автоматически читает их из переменных окружения или .env файла.
    """
    TELEGRAM_TOKEN: str
    ADMIN_TELEGRAM_ID: int
    MONGODB_URI: str
    OPENAI_API_KEY: str
    R2_ENDPOINT_URL: str
    R2_ACCESS_KEY_ID: str
    R2_SECRET_ACCESS_KEY: str
    R2_BUCKET_NAME: str
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    class Config:
        # Указываем Pydantic искать файл .env в корне проекта
        env_file = ".env"
        env_file_encoding = "utf-8"

# Создаем единственный экземпляр настроек
settings = Settings()