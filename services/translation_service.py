# services/translation_service.py
import os
import logging
import openai
from typing import Dict

logger = logging.getLogger(__name__)

# Карта для более понятных названий языков в промптах для GPT
LANGUAGE_FULL_NAMES = {
    'en': 'English',
    'ru': 'Russian',
    'km': 'Khmer',
    'de': 'German',
    'es': 'Spanish',
    'fr': 'French',
    'it': 'Italian',
    'uk': 'Ukrainian',
    'zh': 'Chinese',
    'ja': 'Japanese'
}


class TranslationService:
    def __init__(self):
        """Инициализирует сервис перевода, используя клиент OpenAI."""
        self.logger = logging.getLogger(__name__)
        try:
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                raise ValueError("OPENAI_API_KEY is not set in environment variables.")

            self.client = openai.OpenAI(api_key=api_key)
            logger.info("OpenAI client for TranslationService initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client for TranslationService: {e}", exc_info=True)
            self.client = None

    def translate_text(self, text: str, target_language: str, source_language: str = 'auto') -> Dict:
        """
        Переводит текст с помощью модели GPT-4o от OpenAI.
        """
        if not self.client:
            return {'success': False, 'error': 'Translation service is not configured.'}
        if not text or not text.strip():
            return {'success': False, 'error': 'Empty text provided for translation'}

        target_language_name = LANGUAGE_FULL_NAMES.get(target_language, target_language.capitalize())

        if source_language == 'auto':
            user_prompt = f"Translate the following text to {target_language_name}:\n\n---\n\n{text}"
        else:
            source_language_name = LANGUAGE_FULL_NAMES.get(source_language, source_language.capitalize())
            user_prompt = f"Translate the following text from {source_language_name} to {target_language_name}:\n\n---\n\n{text}"

        system_prompt = "You are an expert translator. Your task is to accurately translate the user's text. Provide only the translated text as a direct response, without any additional comments, explanations, or conversational phrases."

        try:
            self.logger.info(f"Translating text to '{target_language}' using GPT-4o.")

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                max_tokens=2048
            )

            translated_text = response.choices[0].message.content.strip()

            return {
                'success': True,
                'translated_text': translated_text,
                'source_language': source_language,
                'target_language': target_language,
                'original_text': text
            }

        except Exception as e:
            self.logger.error(f"Translation error with OpenAI API: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': f'OpenAI API error: {str(e)}',
                'original_text': text
            }