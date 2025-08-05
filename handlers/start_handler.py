# handlers/start_handler.py - Обработчик стартового экрана и команд
import logging
from typing import Dict, Any

from services.telegram_client import TelegramClient
from services.database import DatabaseService
from ui.localization import LocalizationService
from ui.keyboards import create_main_menu_keyboard, create_language_selection_keyboard, create_subscription_keyboard
from config import PLANS

logger = logging.getLogger(__name__)


class StartHandler:
    """Обработчик команд бота и стартового экрана"""

    def __init__(self, telegram: TelegramClient, db: DatabaseService, localization: LocalizationService):
        self.telegram = telegram
        self.db = db
        self.localization = localization

    async def handle_command(self, message_data: Dict[str, Any], user: Dict[str, Any]):
        """Обработка команд бота"""
        text = message_data['text']
        chat_id = message_data['chat']['id']
        command = text.split(' ')[0]

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
        else:
            await self._handle_unknown_command(chat_id, user)

    async def _handle_start_command(self, chat_id: int, user: Dict[str, Any]):
        """Обработка команды /start - главный экран"""
        lang = user['language']

        # Получаем информацию о тарифе пользователя
        plan_info = PLANS.get(user['plan'], PLANS['free'])

        # Форматируем приветственное сообщение
        welcome_text = self.localization.get_text("welcome_message", lang).format(
            username=user.get('username', 'Пользователь'),
            plan_name=plan_info['name'],
            balance_hours=user['balance_minutes'] // 60,
            balance_minutes=user['balance_minutes'] % 60,
            language_name=self.localization.get_language_name(lang)
        )

        # Создаем главное меню
        keyboard = create_main_menu_keyboard(lang)

        await self.telegram.send_message(
            chat_id=chat_id,
            text=welcome_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

        logger.info(f"👋 Отправлен стартовый экран пользователю {user['telegram_id']}")

    async def _handle_help_command(self, chat_id: int, user: Dict[str, Any]):
        """Обработка команды /help"""
        lang = user['language']

        help_text = self.localization.get_text("help_message", lang)

        await self.telegram.send_message(
            chat_id=chat_id,
            text=help_text,
            parse_mode="Markdown"
        )

    async def _handle_settings_command(self, chat_id: int, user: Dict[str, Any]):
        """Обработка команды /settings"""
        lang = user['language']

        settings_text = self.localization.get_text("settings_message", lang).format(
            current_language=self.localization.get_language_name(lang),
            plan_name=PLANS[user['plan']]['name']
        )

        # Кнопки настроек
        keyboard = {
            "inline_keyboard": [
                [{"text": "🌍 Сменить язык", "callback_data": "settings:language"}],
                [{"text": "🔑 Управление подпиской", "callback_data": "settings:subscription"}],
                [{"text": "🔔 Уведомления", "callback_data": "settings:notifications"}],
                [{"text": "🔙 Назад", "callback_data": "main_menu"}]
            ]
        }

        await self.telegram.send_message(
            chat_id=chat_id,
            text=settings_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

    async def _handle_balance_command(self, chat_id: int, user: Dict[str, Any]):
        """Обработка команды /balance"""
        lang = user['language']
        plan_info = PLANS[user['plan']]

        # Подсчитываем использованные минуты за текущий месяц
        used_minutes = await self.db.get_user_usage_current_month(user['telegram_id'])
        remaining_minutes = max(0, plan_info['minutes_limit'] - used_minutes)

        balance_text = self.localization.get_text("balance_message", lang).format(
            plan_name=plan_info['name'],
            used_minutes=used_minutes,
            total_minutes=plan_info['minutes_limit'],
            remaining_hours=remaining_minutes // 60,
            remaining_minutes=remaining_minutes % 60,
            usage_percent=int((used_minutes / plan_info['minutes_limit']) * 100)
        )

        # Кнопки для управления балансом
        keyboard = {
            "inline_keyboard": [
                [{"text": "💎 Пополнить баланс", "callback_data": "balance:topup"}],
                [{"text": "📊 История использования", "callback_data": "balance:history"}],
                [{"text": "🔙 Назад", "callback_data": "main_menu"}]
            ]
        }

        await self.telegram.send_message(
            chat_id=chat_id,
            text=balance_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

    async def _handle_subscription_command(self, chat_id: int, user: Dict[str, Any]):
        """Обработка команды /subscription"""
        lang = user['language']
        current_plan = user['plan']

        subscription_text = self.localization.get_text("subscription_message", lang).format(
            current_plan=PLANS[current_plan]['name'],
            features="\n".join([f"• {feature}" for feature in PLANS[current_plan]['features']])
        )

        keyboard = create_subscription_keyboard(lang, current_plan)

        await self.telegram.send_message(
            chat_id=chat_id,
            text=subscription_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

    async def _handle_unknown_command(self, chat_id: int, user: Dict[str, Any]):
        """Обработка неизвестной команды"""
        lang = user['language']

        unknown_text = self.localization.get_text("unknown_command", lang)

        await self.telegram.send_message(
            chat_id=chat_id,
            text=unknown_text
        )

    async def handle_language_selection(self, callback_data: Dict[str, Any], user: Dict[str, Any]):
        """Обработка выбора языка"""
        chat_id = callback_data['message']['chat']['id']
        message_id = callback_data['message']['message_id']

        # Показываем меню выбора языка
        keyboard = create_language_selection_keyboard()

        language_text = self.localization.get_text("select_language", user['language'])

        await self.telegram.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=language_text,
            reply_markup=keyboard
        )

    async def handle_language_change(self, callback_data: Dict[str, Any], user: Dict[str, Any], new_language: str):
        """Обработка смены языка"""
        chat_id = callback_data['message']['chat']['id']
        message_id = callback_data['message']['message_id']

        # Обновляем язык пользователя в БД
        await self.db.update_user(user['telegram_id'], {'language': new_language})
        user['language'] = new_language

        # Подтверждение смены языка
        success_text = self.localization.get_text("language_changed", new_language).format(
            language_name=self.localization.get_language_name(new_language)
        )

        keyboard = {
            "inline_keyboard": [
                [{"text": "🔙 " + self.localization.get_text("back_to_settings", new_language),
                  "callback_data": "settings:main"}]
            ]
        }

        await self.telegram.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=success_text,
            reply_markup=keyboard
        )

        logger.info(f"🌍 Пользователь {user['telegram_id']} сменил язык на {new_language}")