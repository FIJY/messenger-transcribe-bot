import re
import logging

logger = logging.getLogger(__name__)


class LanguageDetector:
    """Сервис для определения языка текста"""

    def __init__(self):
        self.supported_languages = {
            'km': 'ខ្មែរ (Кхмерский)',
            'en': 'English',
            'ru': 'Русский',
            'es': 'Español',
            'fr': 'Français',
            'de': 'Deutsch',
            'it': 'Italiano',
            'pt': 'Português',
            'nl': 'Nederlands',
            'pl': 'Polski',
            'ja': '日本語',
            'ko': '한국어',
            'zh': '中文',
            'ar': 'العربية',
            'hi': 'हिन्दी',
            'th': 'ไทย',
            'vi': 'Tiếng Việt',
            'id': 'Bahasa Indonesia',
            'tr': 'Türkçe',
            'he': 'עברית',
            'sv': 'Svenska',
            'da': 'Dansk',
            'no': 'Norsk',
            'fi': 'Suomi',
            'el': 'Ελληνικά',
            'cs': 'Čeština',
            'hu': 'Magyar',
            'ro': 'Română',
            'uk': 'Українська',
            'bg': 'Български',
            'hr': 'Hrvatski',
            'sr': 'Српски',
            'sl': 'Slovenščina',
            'sk': 'Slovenčina',
            'et': 'Eesti',
            'lv': 'Latviešu',
            'lt': 'Lietuvių',
            'fa': 'فارسی',
            'ms': 'Bahasa Melayu',
            'tl': 'Tagalog',
            'is': 'Íslenska',
            'ka': 'ქართული',
            'am': 'አማርኛ',
            'sw': 'Kiswahili',
            'cy': 'Cymraeg',
            'eu': 'Euskara',
            'ca': 'Català',
            'gl': 'Galego',
            'unknown': 'Unknown'
        }

        # Паттерны для определения скриптов
        self.script_patterns = {
            'khmer': re.compile(r'[\u1780-\u17FF]'),
            'thai': re.compile(r'[\u0E00-\u0E7F]'),
            'arabic': re.compile(r'[\u0600-\u06FF\u0750-\u077F]'),
            'chinese': re.compile(r'[\u4E00-\u9FFF]'),
            'japanese': re.compile(r'[\u3040-\u309F\u30A0-\u30FF]'),
            'korean': re.compile(r'[\uAC00-\uD7AF]'),
            'cyrillic': re.compile(r'[\u0400-\u04FF]'),
            'hebrew': re.compile(r'[\u0590-\u05FF]'),
            'devanagari': re.compile(r'[\u0900-\u097F]'),
            'latin': re.compile(r'[a-zA-Z]')
        }

        # Маппинг скриптов на языки
        self.script_to_language = {
            'khmer': 'km',
            'thai': 'th',
            'arabic': 'ar',
            'chinese': 'zh',
            'japanese': 'ja',
            'korean': 'ko',
            'hebrew': 'he',
            'devanagari': 'hi'
        }

    def detect_script(self, text):
        """
        Определение системы письма в тексте

        Args:
            text: Текст для анализа

        Returns:
            tuple: (script_name, confidence)
        """
        if not text:
            return ('unknown', 0)

        script_counts = {}
        total_chars = 0

        for char in text:
            if char.isspace():
                continue

            total_chars += 1

            for script_name, pattern in self.script_patterns.items():
                if pattern.match(char):
                    script_counts[script_name] = script_counts.get(script_name, 0) + 1
                    break

        if not script_counts or total_chars == 0:
            return ('unknown', 0)

        # Находим доминирующий скрипт
        dominant_script = max(script_counts.items(), key=lambda x: x[1])
        confidence = dominant_script[1] / total_chars * 100

        logger.info(f"Detected script: {dominant_script[0]} ({confidence:.2f}%)")

        return (dominant_script[0], confidence)

    def analyze_language(self, text, api_detected_language='unknown'):
        """
        Анализ языка с учетом API и контента

        Args:
            text: Транскрибированный текст
            api_detected_language: Язык, определенный API

        Returns:
            dict: Информация о языке
        """
        # Нормализуем язык от API
        api_lang = api_detected_language.lower() if api_detected_language else 'unknown'

        # Определяем скрипт
        script, confidence = self.detect_script(text)

        # Определяем финальный язык
        final_language = api_lang

        # Если API не определил язык, используем скрипт
        if api_lang == 'unknown' and script != 'unknown':
            if script in self.script_to_language:
                final_language = self.script_to_language[script]
            elif script == 'latin':
                final_language = 'en'  # По умолчанию английский для латиницы
            elif script == 'cyrillic':
                final_language = 'ru'  # По умолчанию русский для кириллицы

        # Проверяем соответствие скрипта и языка
        if script == 'khmer' and api_lang not in ['km', 'unknown']:
            logger.warning(f"Script mismatch: detected {script} but API returned {api_lang}")
            # Доверяем скрипту для кхмерского
            final_language = 'km'

        # Получаем название языка для отображения
        display_name = self.supported_languages.get(
            final_language,
            f'Detected: {final_language}'
        )

        result = {
            'api_detected': api_lang,
            'script_detected': script,
            'final_language': final_language,
            'display_name': display_name,
            'confidence': 'high' if confidence > 80 else 'medium' if confidence > 50 else 'low'
        }

        logger.info(f"Language analysis: {result}")

        return result

    def get_language_name(self, language_code):
        """
        Получить название языка по коду

        Args:
            language_code: Код языка (например, 'en', 'km')

        Returns:
            str: Название языка
        """
        return self.supported_languages.get(
            language_code.lower() if language_code else 'unknown',
            f'Language: {language_code}'
        )