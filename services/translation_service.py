# services/translation_service.py
from deep_translator import GoogleTranslator
import logging


class TranslationService:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def translate_text(self, text, target_language='en', source_language='auto'):
        """
        Переводит текст с одного языка на другой

        Args:
            text (str): Текст для перевода
            target_language (str): Целевой язык (по умолчанию 'en')
            source_language (str): Исходный язык (по умолчанию 'auto')

        Returns:
            dict: Результат перевода
        """
        try:
            if not text or not text.strip():
                return {
                    'success': False,
                    'error': 'Пустой текст для перевода'
                }

            # Используем deep-translator вместо googletrans
            translator = GoogleTranslator(
                source=source_language,
                target=target_language
            )

            translated_text = translator.translate(text)

            return {
                'success': True,
                'translated_text': translated_text,
                'source_language': source_language,
                'target_language': target_language,
                'original_text': text
            }

        except Exception as e:
            self.logger.error(f"Ошибка перевода: {str(e)}")
            return {
                'success': False,
                'error': f'Ошибка перевода: {str(e)}',
                'original_text': text
            }

    def get_supported_languages(self):
        """Возвращает список поддерживаемых языков"""
        try:
            return GoogleTranslator().get_supported_languages()
        except Exception as e:
            self.logger.error(f"Ошибка получения списка языков: {str(e)}")
            return []

    def detect_language(self, text):
        """Определяет язык текста"""
        try:
            # deep-translator не имеет встроенного определения языка,
            # используем langdetect как fallback
            from langdetect import detect, detect_langs

            detected = detect(text)
            confidence = max([lang.prob for lang in detect_langs(text)])

            return {
                'success': True,
                'language': detected,
                'confidence': confidence
            }

        except Exception as e:
            self.logger.error(f"Ошибка определения языка: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }