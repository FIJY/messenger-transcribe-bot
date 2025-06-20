# services/correction_service.py
import openai
import os
import logging

logger = logging.getLogger(__name__)


class CorrectionService:
    def __init__(self):
        # Используем тот же API ключ, что и для Whisper
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

        logger.info(f"Запускаем коррекцию для кхмерского текста: {latin_text[:100]}...")

        try:
            # Системная инструкция, которая объясняет модели ее задачу
            system_prompt = (
                "You are an expert linguist specializing in Khmer. "
                "Your task is to convert Romanized (Latin) Khmer transliterations into the standard native Khmer script. "
                "Do not translate. Only transliterate. Preserve the meaning and structure. "
                "If the input is already in Khmer script or is nonsensical, return it as is."
            )

            # Вызов Chat API
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",  # Дешевая и быстрая модель для этой задачи
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": latin_text}
                ],
                temperature=0.1,  # Низкая температура для более предсказуемого и точного результата
                max_tokens=1000,  # Лимит токенов на ответ
            )

            corrected_text = response.choices[0].message.content
            logger.info(f"Текст успешно скорректирован. Результат: {corrected_text[:100]}...")
            return corrected_text

        except Exception as e:
            logger.error(f"Ошибка при коррекции текста через GPT: {e}", exc_info=True)
            return None