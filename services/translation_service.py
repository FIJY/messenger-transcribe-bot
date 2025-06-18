import logging
from deep_translator import GoogleTranslator
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class TranslationService:
    def __init__(self):
        """Инициализация сервиса перевода"""
        # deep-translator не требует специальной инициализации
        self.supported_languages = self._get_supported_languages()
        logger.info("TranslationService успешно инициализирован")

    async def translate_text(self, text: str, target_language: str, source_language: Optional[str] = None) -> Dict[
        str, Any]:
        """
        Перевод текста на указанный язык

        Args:
            text: Текст для перевода
            target_language: Целевой язык (код ISO 639-1)
            source_language: Исходный язык (опционально, автоопределение)

        Returns:
            Dict с результатом перевода
        """
        try:
            if not text or not text.strip():
                return {
                    "success": False,
                    "error": "Пустой текст для перевода"
                }

            # Проверяем поддержку целевого языка
            if target_language not in self.supported_languages:
                return {
                    "success": False,
                    "error": f"Язык '{target_language}' не поддерживается"
                }

            # Если исходный язык не указан, используем автоопределение
            if source_language:
                if source_language not in self.supported_languages:
                    source_language = 'auto'
            else:
                source_language = 'auto'

            logger.info(f"Переводим с '{source_language}' на '{target_language}'")

            # Выполняем перевод
            translator = GoogleTranslator(source=source_language, target=target_language)
            translated_text = translator.translate(text)

            if not translated_text:
                return {
                    "success": False,
                    "error": "Не удалось выполнить перевод"
                }

            logger.info("Перевод успешно выполнен")

            return {
                "success": True,
                "original_text": text,
                "translated_text": translated_text,
                "source_language": source_language,
                "target_language": target_language
            }

        except Exception as e:
            logger.error(f"Ошибка при переводе: {e}")
            return {
                "success": False,
                "error": f"Ошибка перевода: {str(e)}",
                "original_text": text
            }

    def translate_sync(self, text: str, target_language: str, source_language: Optional[str] = None) -> str:
        """
        Синхронный перевод текста (для обратной совместимости)

        Args:
            text: Текст для перевода
            target_language: Целевой язык
            source_language: Исходный язык (опционально)

        Returns:
            Переведенный текст или исходный текст при ошибке
        """
        try:
            translator = GoogleTranslator(
                source=source_language or 'auto',
                target=target_language
            )
            result = translator.translate(text)
            return result if result else text

        except Exception as e:
            logger.error(f"Ошибка синхронного перевода: {e}")
            return text

    def detect_language(self, text: str) -> Optional[str]:
        """
        Определение языка текста

        Args:
            text: Текст для анализа

        Returns:
            Код языка или None при ошибке
        """
        try:
            # Используем Google Translator для определения языка
            translator = GoogleTranslator(source='auto', target='en')
            # Попробуем перевести короткий фрагмент для определения языка
            test_text = text[:100] if len(text) > 100 else text

            # В deep-translator нет прямого метода определения языка,
            # но мы можем использовать наш LanguageDetector
            from services.language_detector import LanguageDetector
            detector = LanguageDetector()
            result = detector.analyze_language(test_text)

            return result.get('language', 'en')

        except Exception as e:
            logger.error(f"Ошибка определения языка: {e}")
            return None

    def _get_supported_languages(self) -> Dict[str, str]:
        """Получение списка поддерживаемых языков"""
        # Основные языки, поддерживаемые Google Translate
        return {
            'af': 'Afrikaans',
            'sq': 'Albanian',
            'am': 'Amharic',
            'ar': 'Arabic',
            'hy': 'Armenian',
            'az': 'Azerbaijani',
            'eu': 'Basque',
            'be': 'Belarusian',
            'bn': 'Bengali',
            'bs': 'Bosnian',
            'bg': 'Bulgarian',
            'ca': 'Catalan',
            'ceb': 'Cebuano',
            'zh': 'Chinese',
            'zh-cn': 'Chinese (Simplified)',
            'zh-tw': 'Chinese (Traditional)',
            'co': 'Corsican',
            'hr': 'Croatian',
            'cs': 'Czech',
            'da': 'Danish',
            'nl': 'Dutch',
            'en': 'English',
            'eo': 'Esperanto',
            'et': 'Estonian',
            'tl': 'Filipino',
            'fi': 'Finnish',
            'fr': 'French',
            'fy': 'Frisian',
            'gl': 'Galician',
            'ka': 'Georgian',
            'de': 'German',
            'el': 'Greek',
            'gu': 'Gujarati',
            'ht': 'Haitian Creole',
            'ha': 'Hausa',
            'haw': 'Hawaiian',
            'he': 'Hebrew',
            'hi': 'Hindi',
            'hmn': 'Hmong',
            'hu': 'Hungarian',
            'is': 'Icelandic',
            'ig': 'Igbo',
            'id': 'Indonesian',
            'ga': 'Irish',
            'it': 'Italian',
            'ja': 'Japanese',
            'jw': 'Javanese',
            'kn': 'Kannada',
            'kk': 'Kazakh',
            'km': 'Khmer',
            'rw': 'Kinyarwanda',
            'ko': 'Korean',
            'ku': 'Kurdish',
            'ky': 'Kyrgyz',
            'lo': 'Lao',
            'la': 'Latin',
            'lv': 'Latvian',
            'lt': 'Lithuanian',
            'lb': 'Luxembourgish',
            'mk': 'Macedonian',
            'mg': 'Malagasy',
            'ms': 'Malay',
            'ml': 'Malayalam',
            'mt': 'Maltese',
            'mi': 'Maori',
            'mr': 'Marathi',
            'mn': 'Mongolian',
            'my': 'Myanmar (Burmese)',
            'ne': 'Nepali',
            'no': 'Norwegian',
            'ny': 'Nyanja (Chichewa)',
            'or': 'Odia (Oriya)',
            'ps': 'Pashto',
            'fa': 'Persian',
            'pl': 'Polish',
            'pt': 'Portuguese',
            'pa': 'Punjabi',
            'ro': 'Romanian',
            'ru': 'Russian',
            'sm': 'Samoan',
            'gd': 'Scots Gaelic',
            'sr': 'Serbian',
            'st': 'Sesotho',
            'sn': 'Shona',
            'sd': 'Sindhi',
            'si': 'Sinhala (Sinhalese)',
            'sk': 'Slovak',
            'sl': 'Slovenian',
            'so': 'Somali',
            'es': 'Spanish',
            'su': 'Sundanese',
            'sw': 'Swahili',
            'sv': 'Swedish',
            'tg': 'Tajik',
            'ta': 'Tamil',
            'tt': 'Tatar',
            'te': 'Telugu',
            'th': 'Thai',
            'tr': 'Turkish',
            'tk': 'Turkmen',
            'uk': 'Ukrainian',
            'ur': 'Urdu',
            'ug': 'Uyghur',
            'uz': 'Uzbek',
            'vi': 'Vietnamese',
            'cy': 'Welsh',
            'xh': 'Xhosa',
            'yi': 'Yiddish',
            'yo': 'Yoruba',
            'zu': 'Zulu'
        }

    def get_language_name(self, language_code: str) -> str:
        """Получение названия языка по коду"""
        return self.supported_languages.get(language_code, f"Unknown ({language_code})")

    def is_language_supported(self, language_code: str) -> bool:
        """Проверка поддержки языка"""
        return language_code in self.supported_languages