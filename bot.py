# bot.py - Главный класс Telegram бота
import logging
from typing import Dict, Any, Optional
import httpx

from config_del import settings
from services.database import DatabaseService
from services.telegram_client import TelegramClient
from handlers.start_handler import StartHandler
from handlers.media_handler import MediaHandler
from handlers.callback_handler import CallbackHandler
from handlers.chat_handler import ChatHandler
from ui.localization import LocalizationService

logger = logging.getLogger(__name__)


class TranscribeBot:
    """Главный класс Telegram бота для транскрипции"""

    def __init__(self):
        self.token = settings.TELEGRAM_TOKEN
        self.telegram = TelegramClient(self.token)
        self.db = DatabaseService()
        self.localization = LocalizationService()

        # Инициализация обработчиков
        self.start_handler = StartHandler(self.telegram, self.db, self.localization)
        self.media_handler = MediaHandler(self.telegram, self.db, self.localization)
        self.callback_handler = CallbackHandler(self.telegram, self.db, self.localization)
        self.chat_handler = ChatHandler(self.telegram, self.db, self.localization)

        logger.info("🤖 TranscribeBot инициализирован")

    async def initialize(self):
        """Инициализация бота и зависимостей"""
        try:
            # Инициализация базы данных
            await self.db.initialize()

            # Установка webhook
            webhook_url = f"{settings.WEBHOOK_URL}/webhook/{self.token}"
            await self.telegram.set_webhook(webhook_url)

            # Установка команд бота
            await self._setup_bot_commands()

            logger.info("✅ Бот успешно инициализирован")

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации бота: {e}", exc_info=True)
            raise

    async def shutdown(self):
        """Корректное завершение работы бота"""
        try:
            await self.db.close()
            await self.telegram.close()
            logger.info("✅ Бот корректно завершил работу")
        except Exception as e:
            logger.error(f"❌ Ошибка при завершении работы: {e}")

    async def process_update(self, update_data: Dict[str, Any]):
        """Обработка входящего update от Telegram"""
        try:
            update_id = update_data.get('update_id')
            logger.info(f"🔄 Обработка update {update_id}")

            # Определяем тип update и маршрутизируем к соответствующему обработчику
            if 'message' in update_data:
                await self._handle_message(update_data['message'])

            elif 'callback_query' in update_data:
                await self._handle_callback_query(update_data['callback_query'])

            else:
                logger.warning(f"⚠️ Неизвестный тип update: {list(update_data.keys())}")

        except Exception as e:
            logger.error(f"❌ Ошибка обработки update: {e}", exc_info=True)

    async def _handle_message(self, message_data: Dict[str, Any]):
        """Обработка входящих сообщений"""
        user_id = message_data['from']['id']
        chat_id = message_data['chat']['id']

        # Получаем или создаем пользователя
        user = await self.db.get_or_create_user(
            telegram_id=user_id,
            username=message_data['from'].get('username'),
            language_code=message_data['from'].get('language_code', 'en')
        )

        # Определяем тип сообщения и маршрутизируем
        if 'text' in message_data:
            text = message_data['text']

            if text.startswith('/'):
                # Команды бота
                await self.start_handler.handle_command(message_data, user)
            else:
                # Обычные текстовые сообщения (вопросы к контенту)
                await self.chat_handler.handle_text_message(message_data, user)

        elif any(key in message_data for key in ['audio', 'voice', 'video', 'video_note', 'document']):
            # Медиа файлы
            await self.media_handler.handle_media_message(message_data, user)

        else:
            # Неподдерживаемый тип сообщения
            await self.telegram.send_message(
                chat_id=chat_id,
                text=self.localization.get_text("unsupported_message_type", user['language'])
            )

    async def _handle_callback_query(self, callback_data: Dict[str, Any]):
        """Обработка нажатий на inline кнопки"""
        user_id = callback_data['from']['id']

        # Получаем пользователя
        user = await self.db.get_user_by_telegram_id(user_id)
        if not user:
            logger.warning(f"⚠️ Пользователь {user_id} не найден для callback")
            return

        await self.callback_handler.handle_callback(callback_data, user)

    async def _setup_bot_commands(self):
        """Настройка команд бота"""
        commands = [
            {"command": "start", "description": "🚀 Начать работу с ботом"},
            {"command": "help", "description": "❓ Помощь и инструкции"},
            {"command": "settings", "description": "⚙️ Настройки бота"},
            {"command": "balance", "description": "💰 Проверить баланс"},
            {"command": "subscription", "description": "🔑 Управление подпиской"},
        ]

        await self.telegram.set_my_commands(commands)
        logger.info("✅ Команды бота установлены")


# Вспомогательные функции
async def send_typing_action(telegram_client: TelegramClient, chat_id: int):
    """Отправка индикатора печати"""
    await telegram_client.send_chat_action(chat_id, "typing")


async def send_upload_document_action(telegram_client: TelegramClient, chat_id: int):
    """Отправка индикатора загрузки документа"""
    await telegram_client.send_chat_action(chat_id, "upload_document")