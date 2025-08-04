# telegram_handler.py
import logging

# Типы для подсказок IDE
from services.database import Database
from services.telegram_service import TelegramService

# Константы
from config import START_MESSAGE

class TelegramHandler:
    """
    Главный обработчик логики для Telegram.
    Получает зависимости через конструктор.
    """
    def __init__(self, db_service: Database, telegram_service: TelegramService):
        self.db = db_service
        self.telegram_service = telegram_service
        logging.info("Telegram Handler initialized.")

    async def handle_update(self, update: dict):
        """Обрабатывает входящие обновления."""
        if "message" in update and "text" in update["message"]:
            message = update["message"]
            chat_id = message["chat"]["id"]
            text = message["text"]

            if text == "/start":
                await self.telegram_service.send_message(chat_id, START_MESSAGE)