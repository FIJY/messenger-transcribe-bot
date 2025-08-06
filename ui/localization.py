# ui/localization.py - Сервис локализации
import logging
from typing import Dict, Any
from config_del import SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)


class LocalizationService:
    """Сервис для мультиязычной поддержки"""

    def __init__(self):
        self.translations = self._load_translations()
        logger.info("🌍 Localization Service инициализирован")

    def _load_translations(self) -> Dict[str, Dict[str, str]]:
        """Загружает переводы для разных языков"""

        # Русский (базовый)
        ru_translations = {
            "welcome_message": """👋 **Добро пожаловать!**

🎯 Что я умею:
• Транскрибация аудио/видео в текст
• Перевод на 20+ языков  
• Создание саммари и конспектов
• Подготовка контента для соцсетей
• Протоколы встреч и отчеты

📊 Ваш тариф: **{plan_name}**
🌍 Язык: {language_name}

Просто отправьте мне файл или голосовое сообщение!""",

            "file_received": "✅ Файл получен: {duration}, {size}\n🔄 Загружаю на сервер...",
            "file_downloading": "🔄 Загрузка файла...",
            "transcription_started": "🎤 Начинаю транскрипцию...",
            "ai_processing_started": "🤖 Обрабатываю {options_count} опций...",
            "processing_completed": "🎉 Обработка завершена! Что делаем дальше?",
            "processing_failed": "❌ Произошла ошибка при обработке. Попробуйте позже.",

            "processing_menu": """🎯 **Выберите опции обработки**

📋 Тариф: **{plan_name}**
📊 Лимит опций: {processing_limit}
✅ Выбрано: {selected_count}

Выберите что нужно сделать с транскрипцией:""",

            "transcription_completed": """📝 **Транскрипция завершена**

📊 Слов: {word_count}
🌍 Язык: {language}

Транскрипция:""",

            "settings_message": """⚙️ **Настройки**

🌍 Текущий язык: {current_language}
🔑 Тарифный план: {plan_name}""",

            "select_language": "🌍 **Выберите язык интерфейса:**",
            "language_changed": "✅ Язык интерфейса изменен на {language_name}",

            "balance_message": """💰 **Ваш баланс**

🔑 План: **{plan_name}**
📊 Использовано: {used_minutes} из {total_minutes} минут
⏱️ Остаток: {remaining_hours}ч {remaining_minutes}м
📈 Использование: {usage_percent}%""",

            "subscription_message": """🔑 **Управление подпиской**

Текущий план: **{plan_name}**

Возможности:
{features}""",

            "help_message": """❓ **Помощь**

🎯 **Как пользоваться:**
1. Отправьте аудио/видео файл или голосовое сообщение
2. Выберите нужные опции обработки
3. Получите результат в текстовом виде + файлы

📱 **Поддерживаемые форматы:**
• Аудио: MP3, WAV, OGG, M4A, AAC, FLAC
• Видео: MP4, AVI, MOV, MKV, WEBM

⚙️ **Команды:**
/start - Главное меню
/settings - Настройки
/balance - Проверить баланс
/help - Эта справка""",

            "unsupported_message_type": "❌ Этот тип сообщения не поддерживается. Отправьте аудио, видео файл или голосовое сообщение.",
            "file_validation_error": "❌ Ошибка файла: {error}",
            "insufficient_balance": "❌ Недостаточно баланса для обработки этого файла.",
            "upload_error": "❌ Ошибка загрузки файла. Попробуйте еще раз.",
            "processing_error": "❌ Ошибка обработки файла. Попробуйте позже.",
            "callback_error": "❌ Произошла ошибка. Попробуйте еще раз.",
            "no_options_selected": "❌ Выберите хотя бы одну опцию для обработки.",
            "processing_started": "🚀 Начинаю обработку {options_count} опций...",
            "unknown_command": "❓ Неизвестная команда. Используйте /help для справки.",
            "url_not_supported": "❌ Обработка ссылок пока не поддерживается. Отправьте файл.",
            "topup_options": """💎 **Пополнение баланса**

Выберите пакет минут:""",
        }

        # Английский
        en_translations = {
            "welcome_message": """👋 **Welcome!**

🎯 What I can do:
• Transcribe audio/video to text
• Translate to 20+ languages  
• Create summaries and notes
• Prepare content for social media
• Meeting protocols and reports

📊 Your plan: **{plan_name}**
🌍 Language: {language_name}

Just send me a file or voice message!""",

            "file_received": "✅ File received: {duration}, {size}\n🔄 Uploading to server...",
            "processing_completed": "🎉 Processing completed! What's next?",
            "settings_message": """⚙️ **Settings**

🌍 Current language: {current_language}
🔑 Plan: {plan_name}""",

            "select_language": "🌍 **Select interface language:**",
            "language_changed": "✅ Interface language changed to {language_name}",
            "help_message": """❓ **Help**

🎯 **How to use:**
1. Send audio/video file or voice message
2. Select processing options
3. Get results as text + files

📱 **Supported formats:**
• Audio: MP3, WAV, OGG, M4A, AAC, FLAC
• Video: MP4, AVI, MOV, MKV, WEBM""",
        }

        return {
            "ru": ru_translations,
            "en": en_translations
        }

    def get_text(self, key: str, language: str = "ru", **kwargs) -> str:
        """Получает переведенный текст"""
        # Используем русский как fallback
        translations = self.translations.get(language, self.translations["ru"])

        # Получаем текст
        text = translations.get(key, key)

        # Форматируем с параметрами
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError) as e:
            logger.warning(f"Ошибка форматирования строки '{key}': {e}")
            return text

    def get_language_name(self, language_code: str) -> str:
        """Возвращает название языка"""
        lang_info = SUPPORTED_LANGUAGES.get(language_code, {})
        return lang_info.get('native', language_code.upper())

    def get_processing_option_name(self, option_code: str, language: str = "ru") -> str:
        """Возвращает название опции обработки"""

        option_names = {
            "ru": {
                "summary": "📝 Краткое содержание",
                "keypoints": "🔑 Ключевые моменты",
                "translate_en": "🌍 Перевод на английский",
                "translate_zh": "🌍 Перевод на китайский",
                "meeting_protocol": "💼 Протокол совещания",
                "action_items": "✅ Action Items",
                "instagram_post": "📱 Instagram Post",
                "shorts_clips": "🎬 Shorts Clips",
                "lecture_notes": "🎓 Lecture Notes",
                "exam_questions": "📚 Exam Questions",
            }
        }

        names = option_names.get(language, option_names["ru"])
        return names.get(option_code, option_code)