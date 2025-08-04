# celery_worker.py
import os
import sys
import logging
import asyncio
from celery import Celery

# ---------------------------------------------------------------------------
# РЕШЕНИЕ ПРОБЛЕМЫ С ИМПОРТАМИ НА RENDER
# Эта строка добавляет корневую папку проекта ('/opt/render/project/src/')
# в пути поиска Python. Теперь воркер сможет найти папки 'config' и 'services'.
# Это обязательная строка для работы на Render.
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
# ---------------------------------------------------------------------------

# Теперь, когда путь исправлен, мы можем безопасно импортировать наши модули
from config import settings

# from services.database import Database  # Раскомментируйте, когда будете добавлять логику
# from services.s3_service import S3Service # Раскомментируйте, когда будете добавлять логику
# ... и другие ваши сервисы

# Инициализация Celery с настройками из нашего центрального конфига
# Render автоматически подставит правильный REDIS_URL в переменные окружения,
# а наш settings-объект его прочитает.
celery_app = Celery(
    "worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

# Дополнительная конфигурация Celery
celery_app.conf.update(
    task_track_started=True,
    # Указываем Celery, что наши задачи находятся в этом файле
    imports=('celery_worker',)
)

# Настройка логирования для воркера
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


@celery_app.task(name='process_media')
def process_media_task(note_id: str, chat_id: int, message_id: int, processing_options: list):
    """
    Главная фоновая задача для полной обработки медиафайла.

    В будущем мы разобьем эту задачу на несколько шагов (цепочку).
    """
    logging.info(f"Начало обработки задачи для note_id: {note_id}")

    try:
        # Здесь будет ваша основная логика:
        # 1. Инициализировать сервисы (позже мы заменим это на DI)
        #    db = Database()
        #    s3 = S3Service()

        # 2. Получить 'note' из базы данных
        #    note = db.get_note(note_id)

        # 3. Скачать файл, загрузить в S3, транскрибировать...

        # 4. Сгенерировать инсайты (summary, keywords)

        # 5. Отправить результат пользователю через TelegramService
        logging.info(f"Задача для note_id: {note_id} условно выполнена.")

    except Exception as e:
        logging.error(f"Ошибка при обработке note_id {note_id}: {e}", exc_info=True)
        # Здесь также нужно будет отправить сообщение об ошибке пользователю

    return f"Обработка для {note_id} завершена."