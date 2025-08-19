# services/telegram_client.py - ИСПРАВЛЕННАЯ версия
import logging
import httpx
import os
import tempfile
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class TelegramClient:
    """Асинхронный клиент для Telegram Bot API на основе httpx."""

    def __init__(self, token: str):
        if not token:
            raise ValueError("Необходимо указать токен Telegram бота.")
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Закрывает сессию httpx клиента."""
        await self.client.aclose()

    async def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None,
                            params: Optional[Dict] = None) -> Optional[Dict]:
        """Универсальный метод для выполнения запросов к API."""
        try:
            url = f"{self.base_url}/{endpoint}"
            response = await self.client.request(method, url, json=data, params=params)
            response.raise_for_status()  # Вызовет исключение для статусов 4xx/5xx
            result = response.json()
            if result.get("ok"):
                return result.get("result")
            else:
                logger.error(f"Ошибка API Telegram: {result.get('description')}")
                return None
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP ошибка при запросе к {e.request.url}: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            logger.error(f"Неожиданная ошибка при запросе к Telegram API: {e}", exc_info=True)
        return None

    async def get_me(self) -> Optional[Dict]:
        """Получение информации о боте."""
        return await self._make_request("GET", "getMe")

    async def send_message(self, chat_id: int, text: str, reply_markup: Optional[Dict] = None,
                           parse_mode: Optional[str] = None) -> Optional[Dict]:
        """ИСПРАВЛЕННАЯ отправка текстового сообщения БЕЗ форматирования по умолчанию."""
        payload = {
            "chat_id": chat_id,
            "text": text[:4096],  # Лимит Telegram
        }

        # Добавляем parse_mode только если он явно указан и не None
        if parse_mode:
            payload["parse_mode"] = parse_mode

        if reply_markup:
            payload["reply_markup"] = reply_markup

        return await self._make_request("POST", "sendMessage", data=payload)

    async def edit_message_text(self, chat_id: int, message_id: int, text: str,
                                reply_markup: Optional[Dict] = None, parse_mode: Optional[str] = None) -> Optional[
        Dict]:
        """ИСПРАВЛЕННОЕ редактирование текстового сообщения."""
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text[:4096],
        }

        # Добавляем parse_mode только если он явно указан и не None
        if parse_mode:
            payload["parse_mode"] = parse_mode

        if reply_markup:
            payload["reply_markup"] = reply_markup

        return await self._make_request("POST", "editMessageText", data=payload)

    async def set_webhook(self, url: str) -> bool:
        """Установка webhook."""
        result = await self._make_request("POST", "setWebhook", data={"url": url})
        return result is not None

    async def delete_webhook(self) -> bool:
        """Удаление webhook."""
        result = await self._make_request("POST", "deleteWebhook")
        return result is not None

    async def get_updates(self, offset: int = 0, timeout: int = 20) -> List[Dict]:
        """Получение обновлений (для long polling)."""
        params = {"offset": offset, "timeout": timeout}
        updates = await self._make_request("GET", "getUpdates", params=params)
        return updates or []

    async def set_my_commands(self, commands: List[Dict[str, str]]) -> bool:
        """Установка команд бота."""
        result = await self._make_request("POST", "setMyCommands", data={"commands": commands})
        return result is not None

    async def download_file(self, file_id: str) -> Optional[str]:
        """Скачивает файл от Telegram и возвращает путь к временному файлу."""
        try:
            file_info = await self._make_request("GET", "getFile", params={"file_id": file_id})
            if not file_info or 'file_path' not in file_info:
                logger.error("Не удалось получить информацию о файле.")
                return None

            file_path_on_tg = file_info['file_path']
            file_url = f"https://api.telegram.org/file/bot{self.token}/{file_path_on_tg}"

            async with self.client.stream("GET", file_url) as response:
                response.raise_for_status()

                # ИСПРАВЛЕНИЕ: Создаем временный файл в /tmp директории с правильными правами
                file_extension = os.path.splitext(file_path_on_tg)[1] or '.tmp'

                # Создаем временный файл в /tmp с явным указанием директории
                temp_dir = "/tmp"
                os.makedirs(temp_dir, exist_ok=True)

                with tempfile.NamedTemporaryFile(
                        delete=False,
                        suffix=file_extension,
                        dir=temp_dir,
                        prefix="tg_file_"
                ) as tmp_file:
                    async for chunk in response.aiter_bytes():
                        tmp_file.write(chunk)

                    # Устанавливаем права на чтение для всех
                    os.chmod(tmp_file.name, 0o644)

                    logger.info(f"Файл {file_id} успешно скачан в {tmp_file.name}")
                    return tmp_file.name

        except Exception as e:
            logger.error(f"❌ Ошибка скачивания файла {file_id}: {e}")
            return None