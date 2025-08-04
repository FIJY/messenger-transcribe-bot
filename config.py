# config.py
from pydantic import BaseSettings

class Settings(BaseSettings):
    TELEGRAM_TOKEN: str = "ЗАГЛУШКА"
    ADMIN_TELEGRAM_ID: int = 12345
    MONGODB_URI: str = "mongodb://localhost:27017/mydatabase"
    OPENAI_API_KEY: str = "ЗАГЛУШКА"
    R2_ENDPOINT_URL: str = "ЗАГЛУШКА"
    R2_ACCESS_KEY_ID: str = "ЗАГЛУШКА"
    R2_SECRET_ACCESS_KEY: str = "ЗАГЛУШКА"
    R2_BUCKET_NAME: str = "ЗАГЛУШКА"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()