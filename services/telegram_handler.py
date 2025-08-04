# telegram_handler.py
import logging

# Импортируем типы, а не сами классы сервисов
from services.telegram_service import TelegramService
from services.database import Database
from services.payment_service import PaymentService
from utils.message_formatter import create_options_keyboard
from constants import START_MESSAGE, HELP_MESSAGE, PROCESSING_MESSAGE, FILE_READY_MESSAGE
from celery_worker import process_media_task


class TelegramHandler:
    # Получаем готовые сервисы в конструктор
    def __init__(self, telegram_service: TelegramService, db_service: Database, payment_service: PaymentService):
        self.telegram_service = telegram_service
        self.db = db_service
        self.payment_service = payment_service
        logging.info("Telegram Handler initialized with injected services.")

    # ... остальной код класса без изменений ...
    async def handle_update(self, update: dict):
        try:
            if "callback_query" in update:
                await self.handle_callback_query(update["callback_query"])
            elif "message" in update:
                await self.handle_message(update["message"])
        except Exception as e:
            logging.error(f"Error handling update: {e}", exc_info=True)

    async def handle_message(self, message: dict):
        chat_id = message["chat"]["id"]
        user_id = message["from"]["id"]
        username = message["from"].get("username", "N/A")

        self.db.get_or_create_user(user_id, username)

        if "text" in message:
            text = message["text"]
            if text == "/start":
                await self.telegram_service.send_message(chat_id, START_MESSAGE)
                return
            if text == "/help":
                await self.telegram_service.send_message(chat_id, HELP_MESSAGE)
                return

        media_type = None
        media_info = None

        if "voice" in message:
            media_type = "voice";
            media_info = message["voice"]
        elif "audio" in message:
            media_type = "audio";
            media_info = message["audio"]
        elif "video" in message:
            media_type = "video";
            media_info = message["video"]
        elif "video_note" in message:
            media_type = "video_note";
            media_info = message["video_note"]

        if media_type and media_info:
            file_id = media_info["file_id"]
            file_unique_id = media_info["file_unique_id"]
            duration = media_info["duration"]
            note_id = self.db.create_note(user_id, file_id, media_type, file_unique_id, duration)
            keyboard = create_options_keyboard(note_id)
            await self.telegram_service.send_message(chat_id, FILE_READY_MESSAGE, reply_markup=keyboard)

    async def handle_callback_query(self, callback_query: dict):
        chat_id = callback_query["message"]["chat"]["id"]
        message_id = callback_query["message"]["message_id"]
        data = callback_query["data"]

        parts = data.split(":")
        action = parts[0]
        note_id = parts[1]

        note = self.db.get_note(note_id)
        if not note:
            await self.telegram_service.edit_message_text(chat_id, message_id, "Ошибка: Запись не найдена.")
            return

        if action == "process":
            selected_options_str = parts[2] if len(parts) > 2 else ""
            selected_options = selected_options_str.split(',') if selected_options_str else []
            await self.telegram_service.edit_message_text(chat_id, message_id, PROCESSING_MESSAGE)
            process_media_task.delay(note_id, chat_id, message_id, selected_options)
        else:
            current_options_str = parts[2] if len(parts) > 2 else ""
            current_options = set(current_options_str.split(',')) if current_options_str else set()
            option_name = action
            if option_name in current_options:
                current_options.remove(option_name)
            else:
                current_options.add(option_name)
            new_keyboard = create_options_keyboard(note_id, current_options)
            await self.telegram_service.edit_message_text(chat_id, message_id, FILE_READY_MESSAGE,
                                                          reply_markup=new_keyboard)