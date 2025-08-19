# handlers/start_handler.py - ОБНОВЛЕННАЯ версия с поддержкой /video команды
import logging
from typing import Dict, Any

from services.telegram_client import TelegramClient
from services.database import DatabaseService
from ui.localization import LocalizationService
from ui.keyboards import (
    create_main_menu_keyboard, create_settings_keyboard,
    create_balance_keyboard, create_subscription_keyboard
)
from config import SUBSCRIPTION_PLANS
from services.promo_service import PromoCodeService

logger = logging.getLogger(__name__)


class StartHandler:
    """Обработчик команд бота и стартового экрана."""

    def __init__(self, telegram: TelegramClient, db: DatabaseService, localization: LocalizationService):
        self.telegram = telegram
        self.db = db
        self.localization = localization
        self.promo_service = PromoCodeService(db)

    async def handle_command(self, message_data: Dict[str, Any], user: Dict[str, Any]):
        """Обработка команд бота."""
        text = message_data['text']
        chat_id = message_data['chat']['id']
        command = text.split(' ')[0]

        # Маршрутизация команд
        if command == '/start':
            await self._handle_start_command(chat_id, user)
        elif command == '/help':
            await self._handle_help_command(chat_id, user)
        elif command == '/settings':
            await self._handle_settings_command(chat_id, user)
        elif command == '/balance':
            await self._handle_balance_command(chat_id, user)
        elif command == '/subscription':
            await self._handle_subscription_command(chat_id, user)
        elif command == '/promo':
            await self._handle_promo_command(chat_id, user, text)
        elif command == '/video':  # НОВАЯ КОМАНДА
            await self._handle_video_command(chat_id, user)
        else:
            # Проверяем, может это промокод без команды /promo
            potential_code = text.strip()
            if len(potential_code) >= 3 and potential_code.replace('_', '').replace('-', '').isalnum():
                await self._try_promo_code(chat_id, user, potential_code)
            else:
                await self.telegram.send_message(chat_id,
                                                 "❓ Неизвестная команда.\n\n💡 Отправьте промокод или используйте /help")

    async def _handle_video_command(self, chat_id: int, user: dict):
        """НОВАЯ команда: Информация о работе с видеоссылками"""

        # Проверяем доступность видеосервиса
        try:
            from services.smart_video_service import SmartVideoService
            temp_service = SmartVideoService()
            video_service_available = True
            capabilities = temp_service.get_capabilities()
        except Exception:
            video_service_available = False
            capabilities = {}

        if not video_service_available:
            message = """📹 Работа с видеоссылками

❌ Функция временно недоступна
🔧 Администратор должен установить зависимости:
```
pip install youtube-transcript-api yt-dlp
```

📱 Пока что отправляйте аудиофайлы напрямую!"""

            await self.telegram.send_message(chat_id, message)
            return

        # Формируем сообщение о возможностях
        subtitles_status = "✅ Доступны" if capabilities.get('subtitles') else "❌ Недоступны"
        download_status = "✅ Доступна" if capabilities.get('audio_download') else "❌ Недоступна"

        message = f"""📹 Работа с видеоссылками

🎯 **Поддерживаемые платформы:**
• YouTube (youtube.com, youtu.be)

🔧 **Возможности:**
• 📄 Субтитры: {subtitles_status}
• 🎵 Загрузка аудио: {download_status}

📝 **Как использовать:**
1. Отправьте ссылку на YouTube видео
2. Бот сначала попробует получить субтитры (бесплатно!)
3. Если субтитров нет - загрузит аудио (платно)
4. Обработает текст в нужных форматах

💰 **Тарификация:**
• Субтитры YouTube = 0 мин (бесплатно!)
• Транскрипция аудио = обычная цена
• Обработка текста = всегда бесплатно

🎬 **Попробуйте прямо сейчас:**
Отправьте любую ссылку на YouTube видео!

💡 **Примеры:**
• https://www.youtube.com/watch?v=example
• https://youtu.be/example"""

        await self.telegram.send_message(chat_id, message)

    async def _handle_start_command(self, chat_id: int, user: Dict[str, Any]):
        """Обработка команды /start - главный экран."""
        lang = user.get('language', 'ru')
        plan_info = SUBSCRIPTION_PLANS.get(user.get('plan', 'trial'), SUBSCRIPTION_PLANS['trial'])
        username = user.get('username') or 'Пользователь'
        current_balance = user.get('balance_minutes', 0)

        welcome_text = f"""👋 **Добро пожаловать, {username}!**

🎯 Я помогу превратить любую речь в текст и проанализировать его.

📊 **Ваш статус:**
• План: **{plan_info['name']}**
• Баланс транскрипции: **{current_balance} мин**
• Язык: Русский

✨ **Обработка текста всегда бесплатна!**
🎬 **YouTube субтитры = БЕСПЛАТНО!**

🚀 Отправьте аудио/видео файл, YouTube ссылку или попробуйте промокод!"""

        keyboard = create_main_menu_keyboard(self.localization, lang)
        await self.telegram.send_message(chat_id, welcome_text, reply_markup=keyboard)
        logger.info(f"👋 Отправлен стартовый экран пользователю {user['telegram_id']}")

    async def _handle_help_command(self, chat_id: int, user: Dict[str, Any]):
        """Обработка команды /help."""
        help_text = """❓ **Справка**

🎯 **Как пользоваться:**
1. Отправьте аудио/видео файл, голосовое сообщение или YouTube ссылку
2. Выберите нужные опции обработки
3. Получите результат в текстовом виде

📱 **Поддерживаемые форматы:**
• Аудио: MP3, WAV, OGG, M4A, AAC, FLAC
• Видео: MP4, AVI, MOV, MKV, WEBM
• YouTube ссылки (субтитры = бесплатно!)

💰 **Оплата:**
• YouTube субтитры: БЕСПЛАТНО!
• Транскрипция аудио: по секундам
• Обработка текста: всегда бесплатна!

🎫 **Промокоды:**
• Отправьте код прямо в чат
• Или используйте `/promo КОД`
• Например: `YOUTUBE` (30 мин для тестов)

⚙️ **Команды:**
/start - Главное меню
/video - Информация о YouTube
/balance - Проверить баланс
/promo - Активировать промокод
/help - Эта справка"""

        await self.telegram.send_message(chat_id, help_text)

    async def _handle_settings_command(self, chat_id: int, user: Dict[str, Any]):
        """Обработка команды /settings."""
        lang = user.get('language', 'ru')
        plan_info = SUBSCRIPTION_PLANS.get(user.get('plan', 'trial'), SUBSCRIPTION_PLANS['trial'])

        settings_text = f"""⚙️ **Настройки**

🌍 Текущий язык: Русский
🔑 Тарифный план: **{plan_info['name']}**
💰 Баланс: **{user.get('balance_minutes', 0)} мин**

✨ Обработка текста всегда бесплатна!
🎬 YouTube субтитры = БЕСПЛАТНО!"""

        keyboard = create_settings_keyboard(self.localization, lang)
        await self.telegram.send_message(chat_id, settings_text, reply_markup=keyboard)

    async def _handle_balance_command(self, chat_id: int, user: Dict[str, Any]):
        """Обработка команды /balance."""
        plan_info = SUBSCRIPTION_PLANS.get(user.get('plan', 'trial'), SUBSCRIPTION_PLANS['trial'])
        current_balance = user.get('balance_minutes', 0)
        total_used = user.get('total_used_minutes', 0)

        balance_text = f"""💰 **Ваш баланс**

📋 План: **{plan_info['name']}**
💳 Баланс транскрипции: **{current_balance} мин**
📊 Всего использовано: **{total_used} мин**

✨ **Обработка текста всегда бесплатна!**
🎬 **YouTube субтитры = БЕСПЛАТНО!**

💡 **Нужно больше минут?**
• Отправьте промокод (например: `YOUTUBE`)
• Или купите подписку"""

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🎫 Ввести промокод", "callback_data": "promo:help"},
                    {"text": "💎 Подписка", "callback_data": "subscription:main"}
                ],
                [
                    {"text": "🎬 YouTube инфо", "callback_data": "video:info"},
                    {"text": "🔙 Назад", "callback_data": "start"}
                ]
            ]
        }

        await self.telegram.send_message(chat_id, balance_text, reply_markup=keyboard)

    async def _handle_subscription_command(self, chat_id: int, user: Dict[str, Any]):
        """Обработка команды /subscription."""
        lang = user.get('language', 'ru')
        current_plan_code = user.get('plan', 'trial')
        plan_info = SUBSCRIPTION_PLANS.get(current_plan_code, SUBSCRIPTION_PLANS['trial'])
        current_balance = user.get('balance_minutes', 0)

        subscription_text = f"""🔑 **Подписка**

📊 Ваш план: **{plan_info['name']}**
💰 Текущий баланс: **{current_balance} мин**

**Возможности:**
• {plan_info['description']}
• Цена: {plan_info['price_rub']}₽

✨ **Обработка текста всегда бесплатна!**
🎬 **YouTube субтитры = БЕСПЛАТНО!**
💰 Платите только за транскрипцию аудио."""

        keyboard = create_subscription_keyboard(current_plan_code, current_balance)
        await self.telegram.send_message(chat_id, subscription_text, reply_markup=keyboard)

    async def _handle_promo_command(self, chat_id: int, user: Dict[str, Any], text: str):
        """Обработка команды /promo или промокода"""
        parts = text.split()

        if len(parts) < 2:
            help_text = """🎫 **Промокоды**

📝 **Как использовать:**
• `/promo ВАШ_КОД` - активировать промокод
• Или просто отправьте код без команды

💡 **Примеры кодов:**
• `ADMIN500` - 500 минут PRO плана
• `WELCOME100` - 100 минут стартового плана  
• `TEST50` - 50 минут для тестирования
• `YOUTUBE` - 30 минут для YouTube тестов

🎯 Отправьте код и получите минуты транскрипции!
🎬 YouTube субтитры всегда бесплатны!"""

            await self.telegram.send_message(chat_id, help_text)
            return

        promo_code = parts[1].strip()
        await self._try_promo_code(chat_id, user, promo_code)

    async def _try_promo_code(self, chat_id: int, user: Dict[str, Any], code: str):
        """Попытка активации промокода"""
        await self.telegram.send_message(chat_id, "🔄 Проверяю промокод...")

        result = await self.promo_service.use_promo_code(user['telegram_id'], code)

        if result["success"]:
            details = result["details"]

            success_message = f"""🎉 **Промокод активирован!**

✅ **{result['message']}**

💰 Добавлено: **{details['minutes_added']} минут**
💳 Новый баланс: **{details['new_balance']} минут**  
📋 План: **{details['plan']}**

{details.get('description', '')}

🚀 Теперь можете отправлять аудио/видео файлы!
🎬 YouTube субтитры всегда бесплатны!"""

            # Добавляем кнопку для начала использования
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🎯 Главное меню", "callback_data": "start"}],
                    [
                        {"text": "💰 Мой баланс", "callback_data": "balance:main"},
                        {"text": "🎬 YouTube инфо", "callback_data": "video:info"}
                    ]
                ]
            }

            await self.telegram.send_message(chat_id, success_message, reply_markup=keyboard)

        else:
            await self.telegram.send_message(chat_id, result["error"])