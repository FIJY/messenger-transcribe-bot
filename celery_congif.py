# celery_config.py - Отдельная конфигурация Celery
import os
from celery import Celery
from config import settings


def create_celery_app():
    """Создает и настраивает Celery приложение"""

    celery_app = Celery('transcription_tasks')

    # Основные настройки
    celery_app.conf.update(
        # Брокер и бэкенд
        broker_url=settings.REDIS_URL,
        result_backend=settings.REDIS_URL,

        # Импорты задач
        include=['services.transcription'],

        # Критические настройки для предотвращения OOM
        worker_max_tasks_per_child=20,  # Перезапуск после 20 задач
        worker_max_memory_per_child=400000,  # 400MB лимит на воркер
        worker_prefetch_multiplier=1,  # Одна задача на воркер

        # Таймауты
        task_soft_time_limit=300,  # 5 минут мягкий лимит
        task_time_limit=600,  # 10 минут жесткий лимит

        # Подтверждения
        task_acks_late=True,
        task_reject_on_worker_lost=True,

        # Сериализация
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',

        # Результаты
        result_expires=3600,  # 1 час
        task_ignore_result=False,
        task_track_started=True,

        # Логирование
        worker_hijack_root_logger=False,
        worker_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
        worker_task_log_format='[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s',

        # Настройки Redis
        broker_connection_retry_on_startup=True,
        broker_connection_retry=True,
        broker_connection_max_retries=10,

        # Мониторинг
        worker_send_task_events=True,
        task_send_sent_event=True,

        # Роутинг задач
        task_routes={
            'process_transcription_task': {'queue': 'transcription'},
        },

        # Настройки очереди по умолчанию
        task_default_queue='transcription',
        task_default_exchange_type='direct',
        task_default_routing_key='transcription',
    )

    return celery_app


# Создаем глобальный экземпляр
celery_app = create_celery_app()

# Автоматическое обнаружение задач
celery_app.autodiscover_tasks()