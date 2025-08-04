# services/telegram_service.py
import httpx
import logging
import json


class TelegramService:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.client = httpx.AsyncClient(timeout=60.0)
        logging.info("Telegram Service initialized.")

    async def send_message(self, chat_id, text, reply_markup_json: str = None):
        url = f"{self.base_url}/sendMessage"
        payload = {"chat_id": str(chat_id), "text": text, "parse_mode": "Markdown"}
        if reply_markup_json:
            # Просто передаем готовую JSON-строку
            payload["reply_markup"] = json.loads(reply_markup_json)

        try:
            async with self.client as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
        except Exception as e:
            logging.error(f"Error sending message: {e}")

    async def edit_message_text(self, chat_id, message_id, text, reply_markup_json: str = None):
        url = f"{self.base_url}/editMessageText"
        payload = {"chat_id": str(chat_id), "message_id": message_id, "text": text, "parse_mode": "Markdown"}
        if reply_markup_json:
            payload["reply_markup"] = json.loads(reply_markup_json)

        try:
            async with self.client as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if "message is not modified" not in e.response.text:
                logging.error(f"Error editing message: {e.response.status_code} - {e.response.text}")