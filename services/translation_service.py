import openai
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TranslationService:
    def __init__(self):
        """Инициализация сервиса перевода"""
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")

        self.client = openai.OpenAI(api_key=api_key)
        logger.info("TranslationService initialized with OpenAI API")

        # Маппинг языков для лучшего качества перевода
        self.language_names = {
            'km': 'Khmer (Cambodian)',
            'th': 'Thai',
            'vi': 'Vietnamese',
            'zh': 'Chinese',
            'ja': 'Japanese',
            'ko': 'Korean',
            'en': 'English',
            'ru': 'Russian',
            'fr': 'French',
            'es': 'Spanish',
            'de': 'German',
            'ar': 'Arabic',
            'he': 'Hebrew',
            'it': 'Italian',
            'pt': 'Portuguese',
            'nl': 'Dutch',
            'pl': 'Polish',
            'tr': 'Turkish',
            'sv': 'Swedish',
            'no': 'Norwegian',
            'da': 'Danish',
            'fi': 'Finnish',
            'cs': 'Czech',
            'sk': 'Slovak',
            'hu': 'Hungarian',
            'ro': 'Romanian',
            'bg': 'Bulgarian',
            'hr': 'Croatian',
            'sr': 'Serbian',
            'sl': 'Slovenian',
            'et': 'Estonian',
            'lv': 'Latvian',
            'lt': 'Lithuanian',
            'uk': 'Ukrainian',
            'be': 'Belarusian',
            'mk': 'Macedonian',
            'mt': 'Maltese',
            'is': 'Icelandic',
            'ga': 'Irish',
            'cy': 'Welsh',
            'eu': 'Basque',
            'ca': 'Catalan',
            'gl': 'Galician',
            'af': 'Afrikaans',
            'sw': 'Swahili',
            'am': 'Amharic',
            'hi': 'Hindi',
            'bn': 'Bengali',
            'ur': 'Urdu',
            'pa': 'Punjabi',
            'gu': 'Gujarati',
            'or': 'Odia',
            'ta': 'Tamil',
            'te': 'Telugu',
            'kn': 'Kannada',
            'ml': 'Malayalam',
            'si': 'Sinhala',
            'my': 'Myanmar (Burmese)',
            'lo': 'Lao',
            'ka': 'Georgian',
            'hy': 'Armenian',
            'az': 'Azerbaijani',
            'kk': 'Kazakh',
            'ky': 'Kyrgyz',
            'tg': 'Tajik',
            'uz': 'Uzbek',
            'mn': 'Mongolian',
            'ne': 'Nepali',
            'ms': 'Malay',
            'id': 'Indonesian',
            'tl': 'Filipino'
        }

    def translate_text(self, text: str, source_language: str, target_language: str) -> Optional[str]:
        """
        Переводит текст с одного языка на другой используя OpenAI API

        Args:
            text: текст для перевода
            source_language: исходный язык (код ISO 639-1)
            target_language: целевой язык (код ISO 639-1)

        Returns:
            Переведенный текст или None при ошибке
        """
        if not text or not text.strip():
            logger.warning("Пустой текст для перевода")
            return None

        if source_language == target_language:
            logger.info("Исходный и целевой языки одинаковые, возвращаем оригинальный текст")
            return text

        try:
            # Получаем названия языков
            source_name = self.language_names.get(source_language, source_language)
            target_name = self.language_names.get(target_language, target_language)

            # Создаем промпт для перевода
            system_prompt = f"""You are a professional translator. Translate the given text from {source_name} to {target_name}.

Rules:
1. Provide only the translation, no explanations
2. Maintain the original meaning and tone
3. Preserve formatting (line breaks, punctuation)
4. If the text contains names, places, or technical terms, keep them as appropriate
5. For languages with different scripts, use the correct script for the target language"""

            user_prompt = f"Translate this text from {source_name} to {target_name}:\n\n{text}"

            # Выполняем запрос к OpenAI
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,  # Низкая температура для более точных переводов
                max_tokens=2000
            )

            translation = response.choices[0].message.content.strip()

            if not translation:
                logger.error("Получен пустой перевод от OpenAI")
                return None

            logger.info(f"Успешный перевод с {source_language} на {target_language}")
            return translation

        except openai.OpenAIError as e:
            logger.error(f"Ошибка OpenAI API при переводе: {e}")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка при переводе: {e}")
            return None

    def get_language_name(self, language_code: str) -> str:
        """
        Получает полное название языка по коду

        Args:
            language_code: код языка ISO 639-1

        Returns:
            Полное название языка
        """
        return self.language_names.get(language_code, language_code.upper())