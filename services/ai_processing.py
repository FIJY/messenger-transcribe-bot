# services/ai_processing.py - Сервис AI обработки контента
import logging
from typing import Dict, Any, List, Optional
import openai
from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)


class AIProcessingService:
    """Сервис для обработки контента с помощью AI (GPT)"""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = "gpt-4o-mini"  # Более дешевая модель для большинства задач
        self.model_advanced = "gpt-4o"  # Более мощная модель для сложных задач

        logger.info("🤖 AI Processing Service инициализирован")

    async def create_summary(self, text: str, language: str = "ru") -> str:
        """Создает краткое содержание текста"""
        system_prompt = self._get_system_prompt("summary", language)

        return await self._process_with_gpt(
            system_prompt=system_prompt,
            user_text=text,
            max_tokens=800
        )

    async def extract_key_points(self, text: str, language: str = "ru") -> str:
        """Извлекает ключевые моменты с таймкодами"""
        system_prompt = self._get_system_prompt("keypoints", language)

        return await self._process_with_gpt(
            system_prompt=system_prompt,
            user_text=text,
            max_tokens=1000
        )

    async def translate_text(self, text: str, target_language: str) -> str:
        """Переводит текст на указанный язык"""
        language_names = {
            "en": "English", "zh": "Chinese", "es": "Spanish", "fr": "French",
            "de": "German", "ja": "Japanese", "ko": "Korean", "ar": "Arabic"
        }

        target_lang_name = language_names.get(target_language, target_language)

        system_prompt = f"""You are a professional translator. Translate the following text to {target_lang_name}.
Maintain the original tone, style, and meaning. If there are technical terms, provide accurate translations.
Provide only the translation without any additional comments."""

        return await self._process_with_gpt(
            system_prompt=system_prompt,
            user_text=text,
            max_tokens=len(text.split()) * 2 + 200,
            model=self.model_advanced  # Используем более мощную модель для переводов
        )

    async def create_meeting_protocol(self, text: str, language: str = "ru") -> str:
        """Создает протокол совещания"""
        system_prompt = self._get_system_prompt("meeting_protocol", language)

        return await self._process_with_gpt(
            system_prompt=system_prompt,
            user_text=text,
            max_tokens=1200,
            model=self.model_advanced
        )

    async def extract_action_items(self, text: str, language: str = "ru") -> str:
        """Извлекает задачи и действия с ответственными"""
        system_prompt = self._get_system_prompt("action_items", language)

        return await self._process_with_gpt(
            system_prompt=system_prompt,
            user_text=text,
            max_tokens=800
        )

    async def create_instagram_post(self, text: str, language: str = "ru") -> str:
        """Создает пост для Instagram с хештегами"""
        system_prompt = self._get_system_prompt("instagram_post", language)

        return await self._process_with_gpt(
            system_prompt=system_prompt,
            user_text=text,
            max_tokens=400
        )

    async def extract_shorts_clips(self, text: str, language: str = "ru") -> str:
        """Извлекает яркие моменты для коротких видео"""
        system_prompt = self._get_system_prompt("shorts_clips", language)

        return await self._process_with_gpt(
            system_prompt=system_prompt,
            user_text=text,
            max_tokens=600
        )

    async def create_lecture_notes(self, text: str, language: str = "ru") -> str:
        """Создает структурированный конспект лекции"""
        system_prompt = self._get_system_prompt("lecture_notes", language)

        return await self._process_with_gpt(
            system_prompt=system_prompt,
            user_text=text,
            max_tokens=1000,
            model=self.model_advanced
        )

    async def generate_exam_questions(self, text: str, language: str = "ru") -> str:
        """Генерирует вопросы для экзамена"""
        system_prompt = self._get_system_prompt("exam_questions", language)

        return await self._process_with_gpt(
            system_prompt=system_prompt,
            user_text=text,
            max_tokens=800
        )

    async def create_executive_report(self, text: str, language: str = "ru") -> str:
        """Создает отчет для руководства"""
        system_prompt = self._get_system_prompt("executive_report", language)

        return await self._process_with_gpt(
            system_prompt=system_prompt,
            user_text=text,
            max_tokens=600,
            model=self.model_advanced
        )

    async def analyze_content_safety(self, text: str, language: str = "ru") -> str:
        """Анализирует безопасность контента для детей"""
        system_prompt = self._get_system_prompt("content_safety", language)

        return await self._process_with_gpt(
            system_prompt=system_prompt,
            user_text=text,
            max_tokens=500,
            model=self.model_advanced
        )

    async def answer_question(self, context: str, question: str, language: str = "ru") -> str:
        """Отвечает на вопрос по контексту"""
        system_prompt = f"""You are a helpful AI assistant. Answer the user's question based on the provided context.
Be comprehensive and accurate. If the context doesn't contain enough information to answer the question, say so.
Respond in the same language as the question: {"Russian" if language == "ru" else "English"}."""

        user_prompt = f"Context:\n---\n{context}\n---\n\nQuestion: {question}"

        return await self._process_with_gpt(
            system_prompt=system_prompt,
            user_text=user_prompt,
            max_tokens=800,
            model=self.model_advanced
        )

    def _get_system_prompt(self, task_type: str, language: str) -> str:
        """Возвращает системный промпт для конкретной задачи"""

        lang_instruction = "Отвечай на русском языке." if language == "ru" else "Respond in English."

        prompts = {
            "summary": f"""Ты эксперт по созданию кратких содержаний. Создай структурированное краткое содержание текста.
Включи:
- Основные темы и идеи
- Ключевые выводы
- Важные факты и цифры

Используй четкую структуру с заголовками. {lang_instruction}""",

            "keypoints": f"""Ты эксперт по извлечению ключевой информации. Извлеки самые важные моменты из текста.
Для каждого ключевого момента укажи:
- Краткое описание (1-2 предложения)
- Временную метку, если можешь определить (формат ММ:СС)
- Важность (высокая/средняя)

Отсортируй по важности. {lang_instruction}""",

            "meeting_protocol": f"""Ты секретарь, создающий протоколы совещаний. Создай структурированный протокол на основе записи встречи.
Включи:
- Участники (если упоминаются)
- Обсуждаемые вопросы
- Принятые решения
- Поставленные задачи с ответственными
- Следующие шаги

Используй профессиональный деловой стиль. {lang_instruction}""",

            "action_items": f"""Ты менеджер проектов. Извлеки из текста все задачи и действия.
Для каждой задачи укажи:
- Описание задачи
- Ответственный (если упоминается)
- Срок выполнения (если указан)
- Приоритет

Отформатируй как четкий список действий. {lang_instruction}""",

            "instagram_post": f"""Ты SMM-специалист. Создай увлекательный пост для Instagram на основе этого контента.
Включи:
- Цепляющий заголовок
- Основной текст (до 150 слов)
- 10-15 релевантных хештегов
- Призыв к действию

Используй современный, живой стиль. {lang_instruction}""",

            "shorts_clips": f"""Ты видеоредактор. Найди 3-5 самых ярких и интересных моментов для коротких видео.
Для каждого момента опиши:
- Краткое описание (что происходит)
- Почему это интересно зрителям
- Предполагаемую длительность клипа (15-60 сек)
- Временную метку в оригинале

Выбирай самые эмоциональные и вирусные моменты. {lang_instruction}""",

            "lecture_notes": f"""Ты студент, создающий конспект лекции. Структурируй материал для удобного изучения.
Создай:
- Основные разделы и подразделы
- Определения ключевых терминов
- Важные формулы или концепции
- Примеры для лучшего понимания

Используй четкую иерархическую структуру. {lang_instruction}""",

            "exam_questions": f"""Ты преподаватель, составляющий экзаменационные вопросы. Создай 8-10 вопросов разных типов.
Включи:
- 3-4 теоретических вопроса
- 2-3 практических задания
- 2-3 вопроса на анализ и синтез

Вопросы должны покрывать основные темы материала. {lang_instruction}""",

            "executive_report": f"""Ты аналитик, готовящий отчет для топ-менеджмента. Создай краткий исполнительный отчет.
Включи:
- Краткое резюме (2-3 предложения)
- Ключевые выводы
- Рекомендации к действию
- Риски и возможности

Используй деловой стиль, будь конкретен и ориентирован на результат. {lang_instruction}""",

            "content_safety": f"""Ты эксперт по детской безопасности в интернете. Проанализируй контент на предмет безопасности для детей.
Оцени:
- Возрастную категорию (0+, 6+, 12+, 16+, 18+)
- Потенциально опасный контент
- Образовательную ценность
- Рекомендации для родителей

Будь объективен и конструктивен. {lang_instruction}"""
        }

        return prompts.get(task_type, f"Обработай следующий текст. {lang_instruction}")

    async def _process_with_gpt(self, system_prompt: str, user_text: str,
                                max_tokens: int = 800, model: Optional[str] = None) -> str:
        """Базовый метод для обработки текста через GPT"""

        if model is None:
            model = self.model

        try:
            logger.info(f"🤖 Обработка через {model}, макс. токенов: {max_tokens}")

            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text}
                ],
                max_tokens=max_tokens,
                temperature=0.3,  # Немного креативности, но в основном точность
                top_p=0.9
            )

            result = response.choices[0].message.content.strip()

            logger.info(f"✅ GPT обработка завершена, получено {len(result)} символов")
            return result

        except openai.RateLimitError as e:
            logger.error(f"❌ Превышен лимит API OpenAI: {e}")
            return "Извините, превышен лимит обращений к AI. Попробуйте позже."

        except openai.APIError as e:
            logger.error(f"❌ Ошибка API OpenAI: {e}")
            return "Произошла ошибка при обработке текста. Попробуйте еще раз."

        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при обработке через GPT: {e}", exc_info=True)
            return "Не удалось обработать текст. Попробуйте позже."

    async def get_text_statistics(self, text: str) -> Dict[str, Any]:
        """Возвращает статистику по тексту"""
        words = text.split()
        sentences = text.count('.') + text.count('!') + text.count('?')

        # Приблизительное время чтения (200 слов в минуту)
        reading_time = len(words) / 200

        return {
            "characters": len(text),
            "words": len(words),
            "sentences": sentences,
            "paragraphs": text.count('\n\n') + 1,
            "reading_time_minutes": round(reading_time, 1)
        }