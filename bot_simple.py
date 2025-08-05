# bot_simple.py - Упрощенный обработчик бота для быстрого запуска
import logging
import asyncio
import httpx
from typing import Dict, Any

logger = logging.getLogger(__name__)


class SimpleBotHandler:
    """Упрощенный обработчик бота без сложных зависимостей"""

    def __init__(self):
        from config import settings
        self.token = settings.TELEGRAM_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.client = httpx.AsyncClient(timeout=30.0)

        logger.info("🤖 SimpleBotHandler инициализирован")

    async def initialize(self):
        """Простая инициализация без сложных зависимостей"""
        try:
            # Проверяем токен бота
            response = await self.client.get(f"{self.base_url}/getMe")
            if response.status_code == 200:
                bot_info = response.json()
                logger.info(f"✅ Бот подключен: @{bot_info['result']['username']}")
            else:
                logger.error(f"❌ Неверный токен бота: {response.status_code}")
                return False

            # Устанавливаем базовые команды
            await self._setup_commands()

            logger.info("✅ Простая инициализация завершена")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации: {e}", exc_info=True)
            return False

    async def shutdown(self):
        """Завершение работы"""
        try:
            await self.client.aclose()
            logger.info("✅ SimpleBotHandler завершил работу")
        except Exception as e:
            logger.error(f"Ошибка при завершении: {e}")

    async def process_update(self, update_data: Dict[str, Any]):
        """Простая обработка входящих обновлений"""
        try:
            if 'message' in update_data:
                await self._handle_message(update_data['message'])
            elif 'callback_query' in update_data:
                await self._handle_callback_query(update_data['callback_query'])
            else:
                logger.info(f"⚠️ Неизвестный тип update: {list(update_data.keys())}")

        except Exception as e:
            logger.error(f"❌ Ошибка обработки update: {e}", exc_info=True)

    async def _handle_message(self, message_data: Dict[str, Any]):
        """Простая обработка сообщений"""
        chat_id = message_data['chat']['id']
        user_name = message_data['from'].get('first_name', 'Пользователь')

        if 'text' in message_data:
            text = message_data['text']

            if text == '/start':
                welcome_text = f"""👋 Привет, {user_name}!

🎯 **Я TranscribeBot** - помогаю превращать аудио в текст!

**Что я умею:**
• 🎤 Транскрибация аудио и видео
• 🌍 Переводы на разные языки
• 📝 Создание саммари и конспектов
• 📱 Подготовка контента для соцсетей

**Как пользоваться:**
Просто отправьте мне аудио, видео файл или голосовое сообщение!

⚙️ Команды: /help - справка"""

                await self._send_message(chat_id, welcome_text)

            elif text == '/help':
                help_text = """❓ **Справка**

🎯 **Поддерживаемые форматы:**
• Аудио: MP3, WAV, OGG, M4A
• Видео: MP4, AVI, MOV
• Голосовые сообщения Telegram

📱 **Команды:**
/start - Главное меню
/help - Эта справка

💡 **Как использовать:**
1. Отправьте аудио/видео файл
2. Дождитесь обработки
3. Получите текст и выберите дополнительные опции

🔧 **Статус:** Бот работает в тестовом режиме"""

                await self._send_message(chat_id, help_text)

            else:
                await self._send_message(
                    chat_id,
                    "💬 Я получил ваше сообщение! Отправьте аудио или видео файл для транскрибации.\n\nИспользуйте /help для справки."
                )

        elif any(key in message_data for key in ['audio', 'voice', 'video', 'video_note', 'document']):
            # Обработка медиа файлов
            await self._handle_media_file(message_data, chat_id)

        else:
            await self._send_message(
                chat_id,
                "🤔 Этот тип сообщения пока не поддерживается. Отправьте аудио или видео файл."
            )

    async def _handle_media_file(self, message_data: Dict[str, Any], chat_id: int):
        """Простая обработка медиа файлов"""

        # Определяем тип файла
        file_info = None
        file_type = "unknown"

        for media_type in ['audio', 'voice', 'video', 'video_note', 'document']:
            if media_type in message_data:
                file_info = message_data[media_type]
                file_type = media_type
                break

        if not file_info:
            await self._send_message(chat_id, "❌ Не удалось определить тип файла.")
            return

        # Отправляем сообщение о получении
        duration = file_info.get('duration', 0)
        file_size = file_info.get('file_size', 0)

        duration_str = f"{duration // 60}:{duration % 60:02d}" if duration > 0 else "неизвестно"
        size_str = f"{file_size / (1024 * 1024):.1f}MB" if file_size > 0 else "неизвестно"

        status_text = f"""✅ **Файл получен!**

📁 Тип: {file_type.upper()}
⏱️ Длительность: {duration_str}
📦 Размер: {size_str}

🚀 **Статус:** Бот настраивается...

💡 В полной версии здесь будет:
• Транскрибация через OpenAI Whisper
• Обработка через GPT-4
• Множество опций для работы с текстом

🔧 **Пока что:** Отправка файлов работает, обработка добавляется!"""

        await self._send_message(chat_id, status_text)

        # Имитируем обработку
        await asyncio.sleep(2)

        demo_result = f"""📝 **Демо результат**

Здесь будет транскрипция вашего {file_type} файла.

В полной версии вы получите:
• ✅ Полный текст с временными метками
• 📄 Файлы TXT и DOCX
• 🌍 Переводы на разные языки  
• 📝 Саммари и ключевые моменты
• 📱 Готовый контент для соцсетей

🔧 **Статус разработки:** 
• ✅ Telegram интеграция
• ✅ Обработка файлов
• 🔄 AI обработка (добавляется)
• 🔄 База данных (добавляется)"""

        await self._send_message(chat_id, demo_result)

    async def _handle_callback_query(self, callback_data: Dict[str, Any]):
        """Простая обработка callback запросов"""
        query_id = callback_data['id']
        chat_id = callback_data['message']['chat']['id']

        # Подтверждаем callback
        await self._answer_callback_query(query_id, "Функция в разработке!")

        await self._send_message(chat_id, "🔧 Эта функция добавляется в полной версии бота!")

    async def _send_message(self, chat_id: int, text: str, reply_markup: Dict = None):
        """Отправка сообщения"""
        url = f"{self.base_url}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": text[:4096],  # Лимит Telegram
            "parse_mode": "Markdown"
        }

        if reply_markup:
            data["reply_markup"] = reply_markup

        try:
            response = await self.client.post(url, json=data)
            if response.status_code != 200:
                logger.error(f"Ошибка отправки сообщения: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки сообщения: {e}")

    async def _answer_callback_query(self, query_id: str, text: str = None):
        """Ответ на callback query"""
        url = f"{self.base_url}/answerCallbackQuery"
        data = {"callback_query_id": query_id}

        if text:
            data["text"] = text

        try:
            response = await self.client.post(url, json=data)
            if response.status_code != 200:
                logger.error(f"Ошибка ответа на callback: {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Ошибка ответа на callback: {e}")

    async def _setup_commands(self):
        """Установка команд бота"""
        commands = [
            {"command": "start", "description": "🚀 Начать работу с ботом"},
            {"command": "help", "description": "❓ Справка и инструкции"}
        ]

        url = f"{self.base_url}/setMyCommands"

        try:
            response = await self.client.post(url, json={"commands": commands})
            if response.status_code == 200:
                logger.info("✅ Команды бота установлены")
            else:
                logger.error(f"Ошибка установки команд: {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Ошибка установки команд: {e}")