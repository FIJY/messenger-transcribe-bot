# services/format_processor.py
import logging
from typing import Dict, Callable, Awaitable, Optional
from abc import ABC, abstractmethod

from services.ai_processing import AIProcessingService
from config import PROCESSING_CATEGORIES, QUICK_FORMATS

logger = logging.getLogger(__name__)


class FormatProcessorError(Exception):
    """Базовое исключение для ошибок обработки форматов"""
    pass


class UnknownFormatError(FormatProcessorError):
    """Исключение для неизвестных форматов"""
    pass


class ProcessingTimeoutError(FormatProcessorError):
    """Исключение для таймаута обработки"""
    pass


class BaseFormatProcessor(ABC):
    """Базовый класс для процессоров форматов"""

    def __init__(self, ai_service: AIProcessingService):
        self.ai_service = ai_service

    @abstractmethod
    async def process(self, text: str) -> str:
        """Обработать текст в соответствии с форматом"""
        pass

    @property
    @abstractmethod
    def format_key(self) -> str:
        """Ключ формата"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Описание формата"""
        pass


class ProtocolProcessor(BaseFormatProcessor):
    """Процессор для создания протоколов совещаний"""

    format_key = "protocol"
    description = "Протокол совещания с основными решениями"

    async def process(self, text: str) -> str:
        return await self.ai_service.create_business_summary(text)


class InstagramProcessor(BaseFormatProcessor):
    """Процессор для создания Instagram постов"""

    format_key = "instagram"
    description = "Пост для Instagram с хештегами"

    async def process(self, text: str) -> str:
        prompt = f"""Создай Instagram пост на основе этого текста:

{text}

Формат ответа:
- Цепляющий заголовок
- Основной текст (2-3 абзаца)
- 5-10 релевантных хештегов
- Призыв к действию

Пиши живо и вовлекающе."""

        return await self.ai_service.process_custom_request(text, prompt)


class SummaryProcessor(BaseFormatProcessor):
    """Процессор для создания кратких изложений"""

    format_key = "summary"
    description = "Краткое изложение основных моментов"

    async def process(self, text: str) -> str:
        return await self.ai_service.create_summary(text)


class LectureNotesProcessor(BaseFormatProcessor):
    """Процессор для создания конспектов лекций"""

    format_key = "lecture_notes"
    description = "Структурированный конспект лекции"

    async def process(self, text: str) -> str:
        return await self.ai_service.create_summary(text)


class ActionItemsProcessor(BaseFormatProcessor):
    """Процессор для извлечения задач"""

    format_key = "action_items"
    description = "Список задач и поручений"

    async def process(self, text: str) -> str:
        prompt = f"""Извлеки из текста все задачи и поручения в формате:

📋 ЗАДАЧИ:

✅ [Задача 1] - [Ответственный] - [Срок]
✅ [Задача 2] - [Ответственный] - [Срок]

Если срок или ответственный не указан, напиши "не указан".

Текст: {text}"""

        return await self.ai_service.process_custom_request(text, prompt)


class ReportProcessor(BaseFormatProcessor):
    """Процессор для создания отчетов"""

    format_key = "report"
    description = "Деловой отчет с ключевыми выводами"

    async def process(self, text: str) -> str:
        return await self.ai_service.create_business_summary(text)


class InsightsProcessor(BaseFormatProcessor):
    """Процессор для извлечения ключевых моментов"""

    format_key = "insights"
    description = "Ключевые инсайты и выводы"

    async def process(self, text: str) -> str:
        return await self.ai_service.extract_keypoints(text)


class ExamQuestionsProcessor(BaseFormatProcessor):
    """Процессор для создания экзаменационных вопросов"""

    format_key = "exam_questions"
    description = "Вопросы для экзамена или самопроверки"

    async def process(self, text: str) -> str:
        prompt = f"""Создай 10-15 экзаменационных вопросов по этому материалу:

{text}

Включи:
- 5 вопросов на знание фактов
- 5 вопросов на понимание
- 3-5 вопросов на анализ и применение

Формат: 
❓ Вопрос 1: ...
❓ Вопрос 2: ..."""

        return await self.ai_service.process_custom_request(text, prompt)


class GlossaryProcessor(BaseFormatProcessor):
    """Процессор для создания глоссария"""

    format_key = "glossary"
    description = "Глоссарий ключевых терминов"

    async def process(self, text: str) -> str:
        prompt = f"""Создай глоссарий ключевых терминов и понятий из текста:

{text}

Формат:
📚 ГЛОССАРИЙ

🔹 Термин 1 - краткое определение
🔹 Термин 2 - краткое определение

Включи 8-12 самых важных терминов."""

        return await self.ai_service.process_custom_request(text, prompt)


class YouTubeProcessor(BaseFormatProcessor):
    """Процессор для создания описаний YouTube"""

    format_key = "youtube"
    description = "Описание для YouTube видео"

    async def process(self, text: str) -> str:
        prompt = f"""Создай описание для YouTube видео на основе контента:

{text}

Включи:
- Краткое описание (2-3 предложения)
- Временные метки (если возможно определить главы)
- Ключевые слова для SEO
- Призыв подписаться

Формат должен быть оптимизирован для YouTube."""

        return await self.ai_service.process_custom_request(text, prompt)


class ShortsProcessor(BaseFormatProcessor):
    """Процессор для создания нарезок Shorts"""

    format_key = "shorts"
    description = "Яркие моменты для YouTube Shorts"

    async def process(self, text: str) -> str:
        prompt = f"""Найди 3-5 самых ярких и цепляющих моментов из текста для YouTube Shorts:

{text}

Для каждого момента укажи:
🎬 Короткое описание (что происходит)
⏰ Примерное время (если можешь определить)
🔥 Почему это зацепит зрителей

Каждый момент должен быть самодостаточным и интересным."""

        return await self.ai_service.process_custom_request(text, prompt)


class TikTokProcessor(BaseFormatProcessor):
    """Процессор для создания хуков TikTok"""

    format_key = "tiktok"
    description = "Цепляющие хуки для TikTok"

    async def process(self, text: str) -> str:
        prompt = f"""Создай 5-7 цепляющих хуков для TikTok на основе этого контента:

{text}

Каждый хук должен:
- Быть очень коротким (1-2 предложения)
- Вызывать эмоции или любопытство
- Подходить для TikTok аудитории

Формат:
🎵 Хук 1: "..."
🎵 Хук 2: "..."
"""

        return await self.ai_service.process_custom_request(text, prompt)


class SafetyCheckProcessor(BaseFormatProcessor):
    """Процессор для анализа безопасности контента"""

    format_key = "safety_check"
    description = "Анализ безопасности для детей"

    async def process(self, text: str) -> str:
        prompt = f"""Проанализируй этот контент на предмет безопасности для детей:

{text}

Оцени:
🔍 Возрастные ограничения (с какого возраста подходит)
⚠️ Потенциально проблемные моменты
✅ Положительные аспекты
🛡️ Рекомендации для родителей

Будь объективным и конструктивным."""

        return await self.ai_service.process_custom_request(text, prompt)


class EducationalValueProcessor(BaseFormatProcessor):
    """Процессор для анализа образовательной ценности"""

    format_key = "educational_value"
    description = "Оценка образовательной ценности"

    async def process(self, text: str) -> str:
        prompt = f"""Оцени образовательную ценность этого контента:

{text}

Проанализируй:
🎓 Какие знания и навыки развивает
📚 Связь с школьной программой
💡 Практическая применимость
🌟 Рекомендации по использованию

Ответ должен помочь родителям понять пользу контента."""

        return await self.ai_service.process_custom_request(text, prompt)


class ParentSummaryProcessor(BaseFormatProcessor):
    """Процессор для создания пересказа для родителей"""

    format_key = "parent_summary"
    description = "Краткий пересказ для родителей"

    async def process(self, text: str) -> str:
        prompt = f"""Создай краткий пересказ для родителей:

{text}

Ответь на вопросы:
📖 О чем этот контент? (2-3 предложения)
🎯 Главная мысль
⭐ Что полезного может извлечь ребенок
🕒 Сколько времени займет изучение

Пиши простым языком, как родитель родителю."""

        return await self.ai_service.process_custom_request(text, prompt)


class TranslationProcessor(BaseFormatProcessor):
    """Базовый процессор для переводов"""

    def __init__(self, ai_service: AIProcessingService, target_language: str):
        super().__init__(ai_service)
        self.target_language = target_language

    @property
    def format_key(self) -> str:
        return f"translate_{self.target_language}"

    @property
    def description(self) -> str:
        language_names = {
            'en': 'английский',
            'es': 'испанский',
            'fr': 'французский',
            'de': 'немецкий',
            'zh': 'китайский',
            'ja': 'японский'
        }
        return f"Перевод на {language_names.get(self.target_language, self.target_language)}"

    async def process(self, text: str) -> str:
        return await self.ai_service.translate_text(text, self.target_language)


class FormatProcessorService:
    """Главный сервис для обработки всех форматов"""

    def __init__(self, ai_service: AIProcessingService):
        self.ai_service = ai_service
        self.processors: Dict[str, BaseFormatProcessor] = {}
        self._register_processors()

    def _register_processors(self):
        """Регистрация всех доступных процессоров"""

        # Базовые процессоры
        base_processors = [
            ProtocolProcessor(self.ai_service),
            InstagramProcessor(self.ai_service),
            SummaryProcessor(self.ai_service),
            LectureNotesProcessor(self.ai_service),
            ActionItemsProcessor(self.ai_service),
            ReportProcessor(self.ai_service),
            InsightsProcessor(self.ai_service),
            ExamQuestionsProcessor(self.ai_service),
            GlossaryProcessor(self.ai_service),
            YouTubeProcessor(self.ai_service),
            ShortsProcessor(self.ai_service),
            TikTokProcessor(self.ai_service),
            SafetyCheckProcessor(self.ai_service),
            EducationalValueProcessor(self.ai_service),
            ParentSummaryProcessor(self.ai_service),
        ]

        for processor in base_processors:
            self.processors[processor.format_key] = processor

        # Процессоры переводов
        translation_languages = ['en', 'es', 'fr', 'de', 'zh', 'ja']
        for lang in translation_languages:
            processor = TranslationProcessor(self.ai_service, lang)
            self.processors[processor.format_key] = processor

        logger.info(f"Зарегистрировано {len(self.processors)} процессоров форматов")

    def get_available_formats(self) -> Dict[str, str]:
        """Получить список доступных форматов с описаниями"""
        return {key: processor.description for key, processor in self.processors.items()}

    def is_format_supported(self, format_key: str) -> bool:
        """Проверить, поддерживается ли формат"""
        return format_key in self.processors

    def get_format_info(self, format_key: str) -> Optional[Dict[str, str]]:
        """Получить информацию о формате"""
        processor = self.processors.get(format_key)
        if not processor:
            return None

        return {
            'key': processor.format_key,
            'description': processor.description,
            'name': self._get_format_name(format_key)
        }

    def _get_format_name(self, format_key: str) -> str:
        """Получить название формата из конфигурации"""
        # Сначала ищем в QUICK_FORMATS
        if format_key in QUICK_FORMATS:
            return QUICK_FORMATS[format_key].get('name', format_key)

        # Затем ищем в категориях
        for category in PROCESSING_CATEGORIES.values():
            formats = category.get('formats', {})
            if format_key in formats:
                return formats[format_key].get('name', format_key)

        return format_key.replace('_', ' ').title()

    async def process_format(self, text: str, format_key: str) -> str:
        """
        Основной метод для обработки текста в указанном формате

        Args:
            text: Исходный текст для обработки
            format_key: Ключ формата (например, 'protocol', 'instagram')

        Returns:
            Обработанный текст

        Raises:
            UnknownFormatError: Если формат не поддерживается
            ProcessingTimeoutError: Если обработка превысила лимит времени
            FormatProcessorError: Для других ошибок обработки
        """

        if not text or not text.strip():
            raise FormatProcessorError("Пустой текст для обработки")

        processor = self.processors.get(format_key)
        if not processor:
            raise UnknownFormatError(f"Неизвестный формат: {format_key}")

        try:
            logger.info(f"Начинаю обработку формата '{format_key}' для текста длиной {len(text)} символов")

            result = await processor.process(text)

            if not result or not result.strip():
                raise FormatProcessorError(f"Процессор '{format_key}' вернул пустой результат")

            logger.info(f"Успешно обработан формат '{format_key}', результат: {len(result)} символов")
            return result.strip()

        except Exception as e:
            logger.error(f"Ошибка обработки формата '{format_key}': {e}", exc_info=True)

            if "timeout" in str(e).lower():
                raise ProcessingTimeoutError(f"Таймаут при обработке формата '{format_key}'")

            raise FormatProcessorError(f"Ошибка обработки формата '{format_key}': {str(e)}")

    def register_custom_processor(self, processor: BaseFormatProcessor):
        """Регистрация кастомного процессора"""
        self.processors[processor.format_key] = processor
        logger.info(f"Зарегистрирован кастомный процессор: {processor.format_key}")

    def unregister_processor(self, format_key: str):
        """Удаление процессора"""
        if format_key in self.processors:
            del self.processors[format_key]
            logger.info(f"Удален процессор: {format_key}")

    def get_processors_by_category(self, category_key: str) -> Dict[str, BaseFormatProcessor]:
        """Получить процессоры определенной категории"""
        category_info = PROCESSING_CATEGORIES.get(category_key, {})
        category_formats = category_info.get('formats', {})

        result = {}
        for format_key in category_formats.keys():
            if format_key in self.processors:
                result[format_key] = self.processors[format_key]

        return result