import re
import logging

logger = logging.getLogger(__name__)


class LanguageDetector:
    """Сервис для определения языка текста"""

    def __init__(self):
        self.supported_languages = {
            'km': 'ខ្មែរ (Кхмерский)',
            'en': 'English (Английский)',
            'ru': 'Русский',
            'zh': '中文 (Китайский)',
            'th': 'ไทย (Тайский)',
            'vi': 'Tiếng Việt (Вьетнамский)',
            'fr': 'Français (Французский)',
            'es': 'Español (Испанский)',
            'ja': '日本語 (Японский)',
            'ko': '한국어 (Корейский)',
            'de': 'Deutsch (Немецкий)',
            'it': 'Italiano (Итальянский)',
            'pt': 'Português (Португальский)',
            'ar': 'العربية (Арабский)',
            'hi': 'हिन्दी (Хинди)',
            'tr': 'Türkçe (Турецкий)',
            'pl': 'Polski (Польский)',
            'nl': 'Nederlands (Голландский)',
            'sv': 'Svenska (Шведский)',
            'da': 'Dansk (Датский)',
            'no': 'Norsk (Норвежский)',
            'fi': 'Suomi (Финский)'
        }

        # Unicode диапазоны для основных скриптов
        self.script_patterns = {
            'khmer': r'[\u1780-\u17FF]',
            'thai': r'[\u0E00-\u0E7F]',
            'chinese': r'[\u4E00-\u9FFF]',
            'cyrillic': r'[\u0400-\u04FF]',
            'arabic': r'[\u0600-\u06FF]',
            'devanagari': r'[\u0900-\u097F]',  # Hindi
            'latin': r'[A-Za-z]',
        }

    def detect_language_from_api(self, api_language_code, text):
        """Обработка результата API определения языка"""
        # Если API определил язык корректно
        if api_language_code and api_language_code != 'unknown':
            language_name = self.supported_languages.get(
                api_language_code,
                api_language_code.upper()
            )

            # Дополнительная проверка по тексту
            script_detected = self.detect_script_from_text(text)
            if script_detected:
                # Если скрипт не соответствует API результату, доверяем скрипту
                corrected_lang = self._script_to_language(script_detected)
                if corrected_lang and corrected_lang != api_language_code:
                    logger.info(f"Corrected language from {api_language_code} to {corrected_lang} based on script")
                    return self.supported_languages.get(corrected_lang, corrected_lang.upper())

            return language_name

        # Если API не определил, пытаемся по тексту
        return self.detect_language_from_text(text)

    def detect_language_from_text(self, text):
        """Определение языка по тексту"""
        if not text or len(text.strip()) < 2:
            return 'Неизвестный'

        script = self.detect_script_from_text(text)
        if script:
            language_code = self._script_to_language(script)
            if language_code:
                return self.supported_languages.get(language_code, 'Автоопределение')

        return 'Автоопределение'

    def detect_script_from_text(self, text):
        """Определение скрипта по тексту"""
        script_scores = {}

        for script_name, pattern in self.script_patterns.items():
            matches = len(re.findall(pattern, text))
            if matches > 0:
                # Вычисляем процент символов данного скрипта
                total_chars = len(re.findall(r'\S', text))  # Все не-пробельные символы
                if total_chars > 0:
                    script_scores[script_name] = matches / total_chars

        if not script_scores:
            return None

        # Возвращаем скрипт с наибольшим процентом
        dominant_script = max(script_scores, key=script_scores.get)

        # Требуем минимум 30% символов для уверенного определения
        if script_scores[dominant_script] >= 0.3:
            logger.info(f"Detected script: {dominant_script} ({script_scores[dominant_script]:.2%})")
            return dominant_script

        return None

    def _script_to_language(self, script):
        """Маппинг скрипта на язык"""
        mapping = {
            'khmer': 'km',
            'thai': 'th',
            'chinese': 'zh',
            'cyrillic': 'ru',
            'arabic': 'ar',
            'devanagari': 'hi',
            'latin': 'en'  # По умолчанию для латиницы
        }
        return mapping.get(script)

    def get_language_name(self, language_code):
        """Получить красивое название языка"""
        return self.supported_languages.get(language_code, language_code.upper())

    def is_supported(self, language_code):
        """Проверить поддерживается ли язык"""
        return language_code in self.supported_languages

    def get_all_languages(self):
        """Получить все поддерживаемые языки"""
        return self.supported_languages.copy()

    def analyze_text_language(self, text, api_language=None):
        """Полный анализ языка текста"""
        result = {
            'api_detected': api_language,
            'script_detected': self.detect_script_from_text(text),
            'final_language': None,
            'confidence': 'low'
        }

        # Определяем финальный язык
        if api_language and api_language != 'unknown':
            # Если API определил - проверяем по скрипту
            script = result['script_detected']
            if script:
                script_lang = self._script_to_language(script)
                if script_lang == api_language:
                    result['confidence'] = 'high'
                    result['final_language'] = api_language
                else:
                    result['confidence'] = 'medium'
                    result['final_language'] = script_lang or api_language
            else:
                result['confidence'] = 'medium'
                result['final_language'] = api_language
        else:
            # API не определил - используем скрипт
            script = result['script_detected']
            if script:
                result['final_language'] = self._script_to_language(script)
                result['confidence'] = 'medium'
            else:
                result['final_language'] = 'en'  # По умолчанию
                result['confidence'] = 'low'

        logger.info(f"Language analysis: {result}")
        return result