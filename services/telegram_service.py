# services/telegram_service.py
import httpx
import logging
from quart import json
from telegram_bot_sdk.telegram_objects.inline_keyboard import InlineKeyboardMarkup


class TelegramService:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.client = httpx.AsyncClient(timeout=60.0)
        logging.info("Telegram Service initialized.")

    # ... остальной код класса без изменений ...
    async def send_message(self, chat_id, text, reply_markup=None):
        url = f"{self.base_url}/sendMessage"
        payload = {"chat_id": str(chat_id), "text": text, "parse_mode": "Markdown"}
        if reply_markup and isinstance(reply_markup, InlineKeyboardMarkup):
            payload["reply_markup"] = json.loads(reply_markup.json())

        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logging.error(f"Error sending message: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            logging.error(f"An unexpected error occurred while sending message: {e}")

    async def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        url = f"{self.base_url}/editMessageText"
        payload = {"chat_id": str(chat_id), "message_id": message_id, "text": text, "parse_mode": "Markdown"}
        if reply_markup and isinstance(reply_markup, InlineKeyboardMarkup):
            payload["reply_markup"] = json.loads(reply_markup.json())

        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if "message is not modified" not in e.response.text:
                logging.error(f"Error editing message: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            logging.error(f"An unexpected error occurred while editing message: {e}")

    async def get_file_path(self, file_id: str) -> str | None:
        url = f"{self.base_url}/getFile"
        payload = {"file_id": file_id}
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            return response.json()["result"]["file_path"]
        except httpx.HTTPStatusError as e:
            logging.error(f"Error getting file path: {e.response.status_code} - {e.response.text}")
            return None

    async def download_file(self, file_path: str, destination: str):
        url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
        try:
            async with self.client.stream("GET", url) as response:
                response.raise_for_status()
                with open(destination, "wb") as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)
        except Exception as e:
            logging.error(f"An unexpected error occurred while downloading file: {e}")
            raise