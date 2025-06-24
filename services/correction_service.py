# services/correction_service.py - ВЕРСИЯ С ДОПОЛНИТЕЛЬНОЙ ПОСТ-ОБРАБОТКОЙ
import openai
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class CorrectionService:
    def __init__(self):
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY не найден в переменных окружения")
        try:
            self.client = openai.OpenAI(api_key=api_key)
            logger.info("CorrectionService: OpenAI клиент успешно инициализирован")
        except Exception as e:
            logger.error(f"CorrectionService: Ошибка инициализации OpenAI: {e}")
            raise

    def correct_khmer_transliteration(self, latin_text: str) -> Optional[str]:
        """
        Использует GPT для исправления латинской транслитерации на нативный кхмерский скрипт.
        """
        if not latin_text:
            return None

        logger.info(f"Запускаем коррекцию транслитерации для: {latin_text[:100]}...")
        system_prompt = (
            "You are a professional Khmer editor and proofreader. Your task is to take raw, transcribed spoken Khmer text and refine it into clean, grammatically correct, and formal written Khmer. "
            "You must perform the following actions:\n"
            "1. Remove filler words, stutters, and verbal tics (e.g., 'អឺ', 'បាទ', repeated words).\n"
            "2. Correct grammatical errors and fix sentence structure.\n"
            "3. Add appropriate punctuation.\n"
            "4. Rephrase colloquialisms and slang into their formal equivalents.\n"
            "5. **Crucially, correct words that are phonetically similar but misspelled.** For example, if you see 'សូសាយ បុង' (sawsay bong), you must correct it to 'សួស្តីបង' (suosdey bong). If you see 'មាសិន រោដ' (meason rod), correct it to 'ម៉ាស៊ីនរត់' (masin rot).\n"
            "6. Do NOT change the core meaning or add new information.\n"
            "Return ONLY the cleaned, final Khmer text and nothing else."
        )
        try:
            corrected_text = self._call_gpt(system_prompt, latin_text)
            # ===> ИСПРАВЛЕНИЕ: Логируем успех только если есть результат <===
            if corrected_text:
                logger.info(f"Транслитерация успешно скорректирована.")
            return corrected_text
        except Exception as e:
            logger.error(f"Ошибка при коррекции транслитерации: {e}", exc_info=True)
            return None

    def post_process_khmer_text(self, raw_text: str) -> Optional[str]:
        """
        Использует GPT для очистки и форматирования сырого транскрибированного кхмерского текста.
        Убирает слова-паразиты, исправляет грамматику, делает текст литературным.
        """
        if not raw_text:
            return None

        logger.info(f"Запускаем пост-обработку кхмерского текста: {raw_text[:100]}...")
        system_prompt = (
            "You are a professional Khmer editor. Your task is to take raw, transcribed spoken text and refine it into clean, "
            "grammatically correct, and formal written Khmer suitable for official documents and translation. "
            "You must perform the following actions:\n"
            "1. Remove filler words, stutters, and verbal tics (e.g., 'អឺ', 'បាទ', repeated words).\n"
            "2. Correct grammatical errors and fix sentence structure.\n"
            "3. Add appropriate punctuation.\n"
            "4. Rephrase colloquialisms and slang into their formal equivalents.\n"
            "5. Do NOT change the core meaning or add new information.\n"
            "Return ONLY the cleaned, final Khmer text and nothing else."
        )
        try:
            processed_text = self._call_gpt(system_prompt, raw_text)
            # ===> ИСПРАВЛЕНИЕ: Логируем успех только если есть результат <===
            if processed_text:
                logger.info(f"Текст успешно прошел пост-обработку.")
            return processed_text
        except Exception as e:
            logger.error(f"Ошибка при пост-обработке текста: {e}", exc_info=True)
            return None

    def _call_gpt(self, system_prompt: str, user_content: str) -> Optional[str]:
        """Универсальный метод для вызова Chat API."""
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo-0125",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.2,
                max_tokens=1500,
            )
            return response.choices[0].message.content
        except openai.NotFoundError as e:
            logger.error(f"Ошибка OpenAI (404 Not Found): Модель не найдена. Проверьте правильность названия модели. {e}")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка при вызове GPT: {e}")
            return None