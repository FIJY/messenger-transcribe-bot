# config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Централизованные настройки приложения.
    Pydantic автоматически читает их из переменных окружения или .env файла.
    """
    # Telegram
    TELEGRAM_TOKEN: str
    ADMIN_TELEGRAM_ID: int

    # MongoDB
    MONGODB_URI: str

    # OpenAI
    OPENAI_API_KEY: str

    # Cloudflare R2 (S3)
    R2_ENDPOINT_URL: str
    R2_ACCESS_KEY_ID: str
    R2_SECRET_ACCESS_KEY: str
    R2_BUCKET_NAME: str

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    class Config:
        # Указываем Pydantic искать файл .env
        env_file = ".env"
        env_file_encoding = "utf-8"
        # Для вложенных настроек (если понадобятся)
        case_sensitive = False


# Создаем единственный экземпляр настроек для всего приложения
settings = Settings()