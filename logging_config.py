# logging_config.py
import logging
import logging.handlers
import os
from datetime import datetime


def setup_logging():
    """Настройка логирования для всего приложения"""

    # Создаем директорию для логов
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    # Основной logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Форматтер
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )

    # Консольный handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Файловый handler с ротацией
    file_handler = logging.handlers.RotatingFileHandler(
        f"{log_dir}/transcribe_bot.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Отдельный handler для ошибок
    error_handler = logging.handlers.RotatingFileHandler(
        f"{log_dir}/errors.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=3
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)

    # Отдельный logger для Celery
    celery_logger = logging.getLogger('celery')
    celery_file_handler = logging.handlers.RotatingFileHandler(
        f"{log_dir}/celery.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=3
    )
    celery_file_handler.setFormatter(formatter)
    celery_logger.addHandler(celery_file_handler)

    logging.info("✅ Логирование настроено")