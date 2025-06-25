# services/translation_service.py
import os
import logging
from google.cloud import translate_v2 as translate

logger = logging.getLogger(__name__)


class TranslationService:
    def __init__(self):
        """
        Инициализирует сервис перевода, используя официальный клиент Google Cloud.
        Ключ GOOGLE_APPLICATION_CREDENTIALS должен быть установлен в окружении.
        """
        self.logger = logging.getLogger(__name__)
        try:
            self.client = translate.Client()
            project_id = os.getenv('GOOGLE_PROJECT_ID')
            if not project_id:
                raise ValueError("GOOGLE_PROJECT_ID environment variable is not set.")
            self.parent = f"projects/{project_id}/locations/global"
            logger.info("Google Cloud Translation client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Google Translation client: {e}", exc_info=True)
            self.client = None

    def translate_text(self, text: str, target_language: str, source_language: str = 'auto') -> dict:
        """
        Переводит текст с одного языка на другой с помощью Google Cloud Translation API.
        """
        if not self.client:
            return {'success': False, 'error': 'Translation service is not configured.'}
        if not text or not text.strip():
            return {'success': False, 'error': 'Empty text for translation'}

        try:
            self.logger.info(f"Translating text from '{source_language}' to '{target_language}'.")

            # Google API определяет исходный язык автоматически, если он не указан
            result = self.client.translate(
                text,
                target_language=target_language,
                source_language=source_language if source_language != 'auto' else None
            )

            translated_text = result['translatedText']
            detected_source_language = result.get('detectedSourceLanguage', source_language)

            return {
                'success': True,
                'translated_text': translated_text,
                'source_language': detected_source_language,
                'target_language': target_language,
                'original_text': text
            }

        except Exception as e:
            self.logger.error(f"Translation error: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': f'Translation API error: {str(e)}',
                'original_text': text
            }

    def get_supported_languages(self, display_language='en') -> list:
        """Возвращает список поддерживаемых языков от Google API."""
        if not self.client:
            return []
        try:
            results = self.client.get_supported_languages(target_language=display_language)
            return results
        except Exception as e:
            self.logger.error(f"Error getting list of languages: {str(e)}")
            return []