# services/celery_client.py
import os
from celery import Celery

_celery_app_client = None

def get_celery_app_client():
    """Создает и возвращает синглтон-клиент Celery."""
    global _celery_app_client
    if _celery_app_client is None:
        redis_url = os.getenv('REDIS_URL')
        if redis_url:
            _celery_app_client = Celery('tasks_client', broker=redis_url)
    return _celery_app_client