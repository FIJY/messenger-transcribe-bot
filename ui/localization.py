# ui/localization.py - ИСПРАВЛЕННАЯ версия с правильным форматированием
import logging
from typing import Dict
from config import SUPPORTED_LANGUAGES, PROCESSING_TYPES

logger = logging.getLogger(__name__)


class LocalizationService:
    """Сервис для мультиязычной поддержки"""

    def __init__(self):
        self.translations = self._load_translations()
        logger.info("🌍 Localization Service инициализирован")

    def _load_translations(self) -> Dict[str, Dict[str, str]]:
        """Загружает переводы для разных языков"""

        ru_buttons = {
            "btn_subscription": "🔑 Подписка",
            "btn_settings": "⚙️ Настройки",
            "btn_help": "❓ Помощь",
            "btn_balance": "💰 Баланс",
            "btn_back": "🔙 Назад",
            "btn_change_lang": "🌍 Сменить язык",
            "btn_manage_subscription": "🔑 Управление подпиской",
            "btn_notifications": "🔔 Уведомления",
            "btn_top_up_balance": "💎 Пополнить баланс",
            "btn_usage_history": "📊 История использования",
            "btn_reset": "🔄 Сброс",
            "btn_process": "🚀 Обработать",
        }

        en_buttons = {
            "btn_subscription": "🔑 Subscription",
            "btn_settings": "⚙️ Settings",
            "btn_help": "❓ Help",
            "btn_balance": "💰 Balance",
            "btn_back": "🔙 Back",
            "btn_change_lang": "🌍 Change Language",
            "btn_manage_subscription": "🔑 Manage Subscription",
            "btn_notifications": "🔔 Notifications",
            "btn_top_up_balance": "💎 Top Up Balance",
            "btn_usage_history": "📊 Usage History",
            "btn_reset": "🔄 Reset",
            "btn_process": "🚀 Process",
        }

        ru_translations = {
            "welcome_message": """👋 *Добро пожаловать, {username}\\!*

🎯 Я помогу вам превратить любую речь в текст и проанализировать его\\.

📊 Ваш тариф: *{plan_name}*
🌍 Язык: {language_name}

Просто отправьте мне файл или голосовое сообщение\\!""",

            "help_message": """❓ *Справка*

🎯 *Как пользоваться:*
1\\. Отправьте аудио/видео файл или голосовое сообщение\\.
2\\. Выберите нужные опции обработки\\.
3\\. Получите результат в текстовом виде и файлах\\.

📱 *Поддерживаемые форматы:*
• Аудио: MP3, WAV, OGG, M4A, AAC, FLAC
• Видео: MP4, AVI, MOV, MKV, WEBM

⚙️ *Команды:*
/start \\- Главное меню
/settings \\- Настройки
/balance \\- Проверить баланс
/help \\- Эта справка""",

            "settings_message": """⚙️ *Настройки*

🌍 Текущий язык: {current_language}
🔑 Тарифный план: {plan_name}""",

            "subscription_message": """🔑 *Подписка*

📊 Ваш план: *{plan_name}*

*Возможности:*
{features}""",

            "select_language": "🌍 *Выберите язык интерфейса:*",

            "language_changed": "✅ Язык интерфейса изменен на {language_name}",

            "balance_message": """💰 *Ваш баланс*

🔑 План: *{plan_name}*
📊 Использовано в этом месяце: {used_minutes} из {total_minutes} минут\\.
📈 Использование: {usage_percent}%""",

            "unsupported_message_type": "❌ Этот тип сообщения не поддерживается\\. Отправьте аудио, видео файл или голосовое сообщение\\.",

            "file_received": "✅ Файл получен\\. Начинаю обработку\\.\\.\\.",

            "transcription_ready": """✅ *Транскрипция готова\\!*

🌍 Язык: {language}
📊 Слов: {words}

📝 *Текст:*
{text}""",

            "choose_processing": """🎯 *Что делаем с транскрипцией?*

Выберите AI обработку:""",

            "processing_result": """🤖 *Результат обработки «{processing_name}»*:

{result}""",

            "error_generic": "❌ Произошла ошибка\\. Пожалуйста, попробуйте позже\\.",
            "error_openai_not_configured": "❌ Сервис AI временно недоступен\\. Пожалуйста, попробуйте позже\\.",
        }
        ru_translations.update(ru_buttons)

        en_translations = {
            "welcome_message": """👋 *Welcome, {username}\\!*

🎯 I will help you turn any speech into text and analyze it\\.

📊 Your plan: *{plan_name}*
🌍 Language: {language_name}

Just send me a file or voice message\\!""",

            "help_message": """❓ *Help*

🎯 *How to use:*
1\\. Send audio/video file or voice message\\.
2\\. Select processing options\\.
3\\. Get results in text and files\\.

📱 *Supported formats:*
• Audio: MP3, WAV, OGG, M4A, AAC, FLAC
• Video: MP4, AVI, MOV, MKV, WEBM

⚙️ *Commands:*
/start \\- Main menu
/settings \\- Settings
/balance \\- Check balance
/help \\- This help""",

            "settings_message": """⚙️ *Settings*

🌍 Current language: {current_language}
🔑 Plan: {plan_name}""",

            "subscription_message": """🔑 *Subscription*

📊 Your plan: *{plan_name}*

*Features:*
{features}""",

            "select_language": "🌍 *Select interface language:*",
            "language_changed": "✅ Interface language changed to {language_name}",

            "balance_message": """💰 *Your Balance*

🔑 Plan: *{plan_name}*
📊 Used this month: {used_minutes} of {total_minutes} minutes\\.
📈 Usage: {usage_percent}%""",

            "unsupported_message_type": "❌ This message type is not supported\\. Please send an audio, video, or voice message\\.",
            "file_received": "✅ File received\\. Starting processing\\.\\.\\.",

            "transcription_ready": """✅ *Transcription is ready\\!*

🌍 Language: {language}
📊 Words: {words}

📝 *Text:*
{text}""",

            "choose_processing": """🎯 *What to do with the transcription?*

Select AI processing:""",

            "processing_result": """🤖 *Result for «{processing_name}»*:

{result}""",

            "error_generic": "❌ An error occurred\\. Please try again later\\.",
            "error_openai_not_configured": "❌ AI service is temporarily unavailable\\. Please try again later\\.",
        }
        en_translations.update(en_buttons)

        return {"ru": ru_translations, "en": en_translations}

    def get_text(self, key: str, language: str = "ru", **kwargs) -> str:
        """Получает переведенный текст с безопасным форматированием"""
        translations = self.translations.get(language, self.translations["ru"])
        text = translations.get(key, f"_{key}_")

        try:
            # Безопасное форматирование - экранируем специальные символы в параметрах
            safe_kwargs = {}
            for k, v in kwargs.items():
                if isinstance(v, str):
                    # Экранируем специальные символы Markdown v2
                    safe_v = str(v).replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']',
                                                                                                        '\\]').replace(
                        '(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>',
                                                                                                        '\\>').replace(
                        '#', '\\#').replace('+', '\\+').replace('-', '\\-').replace('=', '\\=').replace('|',
                                                                                                        '\\|').replace(
                        '{', '\\{').replace('}', '\\}').replace('.', '\\.').replace('!', '\\!')
                    safe_kwargs[k] = safe_v
                else:
                    safe_kwargs[k] = v

            return text.format(**safe_kwargs)
        except (KeyError, ValueError) as e:
            logger.warning(f"Ошибка форматирования строки '{key}': {e}")
            return text

    def get_language_name(self, language_code: str) -> str:
        """Возвращает нативное название языка"""
        lang_info = SUPPORTED_LANGUAGES.get(language_code, {})
        name = lang_info.get('native', language_code.upper())
        # Экранируем специальные символы
        return name.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('!', '\\!')

    def get_processing_name(self, p_code: str, lang: str = "ru") -> str:
        """Возвращает название опции обработки на нужном языке."""
        name = PROCESSING_TYPES.get(p_code, {}).get("name", p_code)
        # Экранируем специальные символы
        return name.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('!', '\\!')