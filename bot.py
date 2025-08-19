# bot.py - Координатор для Telegram бота с системой промокодов и YouTube
import logging
from typing import Dict, Any

from config import settings
from services.database import DatabaseService
from services.telegram_client import TelegramClient
from services.ai_processing import AIProcessingService
from services.transcription import TranscriptionService
from services.audio_processor import AudioProcessor
from ui.localization import LocalizationService
from handlers.start_handler import StartHandler
from handlers.media_handler import MediaHandler
from handlers.callback_handler import CallbackHandler

# НОВЫЙ ИМПОРТ для YouTube
try:
    from handlers.text_handler import TextHandler

    TEXT_HANDLER_AVAILABLE = True
except ImportError as e:
    TEXT_HANDLER_AVAILABLE = False
    TextHandler = None
    logging.warning(f"TextHandler недоступен: {e}")

logger = logging.getLogger(__name__)


class TranscribeBot:
    """
    Класс-координатор. Инициализирует все сервисы и маршрутизирует
    входящие обновления в соответствующие обработчики (хендлеры).
    """

    def __init__(self, settings_obj):
        self.settings = settings_obj
        # Сервисы
        self.telegram_client: TelegramClient | None = None
        self.db_service: DatabaseService | None = None
        self.localization_service: LocalizationService | None = None
        # Хендлеры
        self.start_handler: StartHandler | None = None
        self.media_handler: MediaHandler | None = None
        self.callback_handler: CallbackHandler | None = None
        self.text_handler: TextHandler | None = None  # НОВЫЙ ХЕНДЛЕР

        logger.info("🤖 TranscribeBot координатор создан")

    async def initialize(self):
        """Асинхронная инициализация всех компонентов бота."""
        try:
            self.telegram_client = TelegramClient(self.settings.TELEGRAM_TOKEN)
            bot_info = await self.telegram_client.get_me()
            if not bot_info:
                raise ConnectionError("Не удалось подключиться к Telegram API.")
            logger.info(f"✅ Telegram подключен: @{bot_info.get('username')}")

            self.db_service = DatabaseService()
            await self.db_service.initialize()

            # Инициализируем сервис промокодов
            if self.db_service:
                from services.promo_service import PromoCodeService
                promo_service = PromoCodeService(self.db_service)
                await promo_service.initialize()
                logger.info("🎫 Система промокодов инициализирована")

            self.localization_service = LocalizationService()

            # AI сервисы нужны только для callback_handler'а
            ai_processing_service = None
            if self.settings.OPENAI_API_KEY:
                ai_processing_service = AIProcessingService(self.settings.OPENAI_API_KEY)
                logger.info("🎤 AI сервисы инициализированы")
            else:
                logger.warning("⚠️ OpenAI API ключ не найден - AI функции недоступны")

            # Инициализация хендлеров
            self.start_handler = StartHandler(self.telegram_client, self.db_service, self.localization_service)

            # MediaHandler'у больше не нужны лишние сервисы, так как он использует Celery
            self.media_handler = MediaHandler(
                self.telegram_client, self.localization_service
            )

            self.callback_handler = CallbackHandler(
                self.telegram_client, self.db_service, self.localization_service,
                ai_processing_service, self.start_handler
            )

            # НОВЫЙ TextHandler для YouTube
            if TEXT_HANDLER_AVAILABLE:
                self.text_handler = TextHandler(
                    self.telegram_client, self.db_service, self.localization_service
                )
                logger.info("✅ TextHandler с YouTube поддержкой инициализирован")
            else:
                logger.warning("⚠️ TextHandler недоступен - YouTube функции отключены")

            await self._setup_commands()

            logger.info("✅ Bot инициализирован успешно")
            return True

        except Exception as e:
            logger.error(f"❌ Критическая ошибка инициализации бота: {e}", exc_info=True)
            return False

    async def shutdown(self):
        """Корректное завершение работы."""
        if self.db_service:
            await self.db_service.close()
        if self.telegram_client:
            await self.telegram_client.close()
        logger.info("✅ TranscribeBot остановлен")

    async def process_update(self, update_data: Dict[str, Any]):
        """Главная точка входа для обработки обновлений от Telegram."""
        try:
            if 'message' in update_data:
                await self._handle_message(update_data['message'])
            elif 'callback_query' in update_data:
                if self.callback_handler:
                    await self.callback_handler.handle(update_data['callback_query'])
        except Exception as e:
            logger.error(f"❌ Ошибка обработки update: {e}", exc_info=True)

    async def _handle_message(self, message: Dict[str, Any]):
        """ОБНОВЛЕННАЯ обработка входящих сообщений с поддержкой YouTube."""
        user_id = message['from']['id']
        user = await self.db_service.get_or_create_user(
            user_id, message['from'].get('first_name'), message['from'].get('language_code', 'ru')
        )

        # 1. Команды (начинаются с /)
        if 'text' in message and message['text'].startswith('/'):
            await self.start_handler.handle_command(message, user)
            return

        # 2. Медиафайлы (аудио, видео, голосовые)
        if any(key in message for key in ['audio', 'voice', 'video', 'video_note', 'document']):
            await self.media_handler.handle(message, user)
            return

        # 3. НОВАЯ ЛОГИКА: Текстовые сообщения (включая YouTube ссылки)
        if 'text' in message:
            text = message['text'].strip()

            # Сначала проверяем YouTube через TextHandler
            if self.text_handler:
                await self.text_handler.handle(message, user)
                return

            # Если TextHandler недоступен, проверяем промокоды
            if len(text) >= 3 and len(text) <= 20 and text.replace('_', '').replace('-', '').isalnum():
                await self.start_handler._try_promo_code(message['chat']['id'], user, text)
                return

            # Обычный текст - показываем справку
            youtube_status = "❌ YouTube недоступен (нет зависимостей)" if not TEXT_HANDLER_AVAILABLE else "✅ YouTube поддерживается"

            help_text = f"""❓ Не понимаю команду.

💡 **Что можете сделать:**
• Отправить аудио/видео файл для транскрипции
• {youtube_status}
• Ввести промокод (например: `YOUTUBE`)
• Использовать /help для справки"""

            await self.telegram_client.send_message(message['chat']['id'], help_text)
            return

        # 4. Неподдерживаемые типы сообщений
        lang = user.get('language', 'ru')
        default_text = self.localization_service.get_text("unsupported_message_type", lang)
        await self.telegram_client.send_message(message['chat']['id'], default_text)

    async def _setup_commands(self):
        """Установка списка команд бота в интерфейсе Telegram."""
        # ОБНОВЛЕННЫЙ список команд с YouTube
        commands = [
            {"command": "start", "description": "🚀 Главное меню"},
            {"command": "help", "description": "❓ Справка"},
            {"command": "video", "description": "🎬 YouTube поддержка"},
            {"command": "balance", "description": "💰 Мой баланс"},
            {"command": "promo", "description": "🎫 Промокод"},
            {"command": "settings", "description": "⚙️ Настройки"},
        ]
        await self.telegram_client.set_my_commands(commands)

    async def get_status(self) -> Dict[str, Any]:
        """Получить статус всех компонентов бота"""
        return {
            "telegram": self.telegram_client is not None,
            "database": self.db_service is not None,
            "handlers": {
                "start": self.start_handler is not None,
                "media": self.media_handler is not None,
                "callback": self.callback_handler is not None,
                "text": self.text_handler is not None,
                "youtube": TEXT_HANDLER_AVAILABLE
            }
        }