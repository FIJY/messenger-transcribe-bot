# services/translation_service.py
import os
import logging
from openai import OpenAI
import pycountry
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class TranslationService:
    def __init__(self):
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set. TranslationService cannot function.")
        self.client = OpenAI(api_key=api_key)
        logger.info("TranslationService initialized successfully.")

    def _get_language_name(self, lang_code: str) -> str:
        """Получает полное английское название языка по его ISO 639-1 коду."""
        try:
            language = pycountry.languages.get(alpha_2=lang_code)
            return language.name if language else lang_code.capitalize()
        except Exception:
            return lang_code.capitalize()

    def translate_text(self, text: str, target_language: str, source_language: Optional[str] = None) -> Dict[str, str]:
        """Переводит текст с помощью OpenAI API."""
        if not text or not text.strip():
            return {'success': False, 'error': 'Empty text provided for translation.'}

        target_lang_name = self._get_language_name(target_language)
        source_lang_name = self._get_language_name(source_language) if source_language else None

        source_prompt_part = f" from {source_lang_name}" if source_lang_name else ""

        system_prompt = (
            f"You are an expert translator. Your task is to accurately translate the user's text{source_prompt_part} to {target_lang_name}. "
            "Provide only the translated text as a direct response, without any additional comments, explanations, or conversational phrases."
        )

        try:
            logger.info(f"Translating text to '{target_lang_name}' using GPT-4o.")

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.1,
                max_tokens=int(len(text.split()) * 2.5) + 50
            )

            translated_text = response.choices[0].message.content.strip()
            return {'success': True, 'translated_text': translated_text}

        except Exception as e:
            logger.error(f"Error during translation to {target_language}: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}