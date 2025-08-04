# telegram_handler.py (в корне проекта)
import logging

# Правильные импорты из наших пакетов
from services.telegram_service import TelegramService
from services.database import Database
from utils.message_formatter import create_options_keyboard
from config import START_MESSAGE, HELP_MESSAGE, PROCESSING_MESSAGE, FILE_READY_MESSAGE
# from celery_worker import process_media_task # Пока закомментируем

class TelegramHandler:
    def __init__(self, telegram_service: TelegramService, db_service: Database):
        self.telegram_service = telegram_service
        self.db = db_service
        logging.info("Telegram Handler initialized.")

    async def handle_update(self, update: dict):
        if "message" in update:
            await self.handle_message(update["message"])

    async def handle_message(self, message: dict):
        chat_id = message["chat"]["id"]
        if "text" in message and message["text"] == "/start":
            await self.telegram_service.send_message(chat_id, START_MESSAGE)