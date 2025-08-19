# services/ai_processing.py - Сервис AI обработки текста через GPT
import logging
from typing import Dict, Any
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class AIProcessingService:
    """Сервис для AI обработки текста через GPT"""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("OpenAI API key is required")

        self.client = AsyncOpenAI(api_key=api_key)
        self.model = "gpt-4o-mini"  # Быстрая и дешевая модель
        logger.info("🤖 AIProcessingService инициализирован")

    async def create_summary(self, text: str, language: str = "auto") -> str:
        """
        Создает краткое содержание текста

        Args:
            text: Исходный текст
            language: Язык ответа ("auto" для автоопределения)

        Returns:
            str: Краткое содержание
        """
        try:
            logger.info("📝 Создаю краткое содержание...")

            system_prompt = """Создай структурированное краткое содержание текста. 
Отвечай на том же языке, что и исходный текст. 
Используй маркированные списки и заголовки для лучшей читаемости.
Выдели самые важные моменты."""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                max_tokens=800,
                temperature=0.3
            )

            result = response.choices[0].message.content.strip()
            logger.info("✅ Краткое содержание готово")
            return result

        except Exception as e:
            logger.error(f"❌ Ошибка создания содержания: {e}")
            return f"Ошибка создания краткого содержания: {str(e)}"

    async def translate_text(self, text: str, target_language: str) -> str:
        """
        Переводит текст на указанный язык

        Args:
            text: Исходный текст
            target_language: Целевой язык ('en', 'es', 'fr', 'de', etc.)

        Returns:
            str: Переведенный текст
        """
        try:
            language_names = {
                'en': 'английский',
                'es': 'испанский',
                'fr': 'французский',
                'de': 'немецкий',
                'zh': 'китайский',
                'ja': 'японский',
                'ko': 'корейский'
            }

            target_name = language_names.get(target_language, target_language)
            logger.info(f"🌍 Перевожу на {target_name}...")

            system_prompt = f"""Переведи следующий текст на {target_name} язык. 
Сохраняй структуру и стиль оригинала. 
Делай качественный литературный перевод."""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                max_tokens=len(text.split()) * 2 + 200,
                temperature=0.2
            )

            result = response.choices[0].message.content.strip()
            logger.info("✅ Перевод готов")
            return result

        except Exception as e:
            logger.error(f"❌ Ошибка перевода: {e}")
            return f"Ошибка перевода: {str(e)}"

    async def extract_keypoints(self, text: str) -> str:
        """
        Извлекает ключевые моменты из текста

        Args:
            text: Исходный текст

        Returns:
            str: Ключевые моменты
        """
        try:
            logger.info("🔑 Выделяю ключевые моменты...")

            system_prompt = """Выдели основные ключевые моменты из текста. 
Отвечай на том же языке. 
Структурируй в виде нумерованного списка с краткими пояснениями.
Фокусируйся на самом важном и действенном."""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                max_tokens=600,
                temperature=0.3
            )

            result = response.choices[0].message.content.strip()
            logger.info("✅ Ключевые моменты готовы")
            return result

        except Exception as e:
            logger.error(f"❌ Ошибка выделения ключевых моментов: {e}")
            return f"Ошибка выделения ключевых моментов: {str(e)}"

    async def create_business_summary(self, text: str) -> str:
        """
        Создает деловое резюме для работы

        Args:
            text: Исходный текст

        Returns:
            str: Деловое резюме
        """
        try:
            logger.info("💼 Создаю деловое резюме...")

            system_prompt = """Создай деловое резюме из текста в формате:

**Основные решения:**
- [список принятых решений]

**Задачи и ответственные:**
- [задача] - [ответственный] - [срок]

**Следующие шаги:**
- [что нужно сделать дальше]

Используй деловой стиль. Отвечай на том же языке."""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                max_tokens=700,
                temperature=0.2
            )

            result = response.choices[0].message.content.strip()
            logger.info("✅ Деловое резюме готово")
            return result

        except Exception as e:
            logger.error(f"❌ Ошибка создания делового резюме: {e}")
            return f"Ошибка создания делового резюме: {str(e)}"

    async def process_custom_request(self, text: str, request: str) -> str:
        """
        Обрабатывает кастомный запрос пользователя

        Args:
            text: Исходный текст
            request: Запрос пользователя

        Returns:
            str: Результат обработки
        """
        try:
            logger.info(f"🎯 Обрабатываю кастомный запрос: {request[:50]}...")

            system_prompt = f"""Выполни следующий запрос пользователя по тексту: {request}
Отвечай на том же языке, что и исходный текст.
Будь точным и полезным."""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                max_tokens=800,
                temperature=0.4
            )

            result = response.choices[0].message.content.strip()
            logger.info("✅ Кастомный запрос обработан")
            return result

        except Exception as e:
            logger.error(f"❌ Ошибка обработки запроса: {e}")
            return f"Ошибка обработки запроса: {str(e)}"

    async def get_available_models(self) -> Dict[str, Any]:
        """Получает список доступных моделей OpenAI"""
        try:
            models = await self.client.models.list()
            return {
                "success": True,
                "models": [model.id for model in models.data if "gpt" in model.id]
            }
        except Exception as e:
            logger.error(f"❌ Ошибка получения моделей: {e}")
            return {"success": False, "error": str(e)}