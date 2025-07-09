# services/insight_service.py
import os
import logging
import json
from openai import OpenAI
from typing import List, Optional

logger = logging.getLogger(__name__)


class InsightService:
    # Промпты для генерации отчетов по шаблонам
    REPORT_PROMPTS = {
        "MEETING": {
            "name": "Протокол встречи",
            "prompt": """Проанализируй следующий текст транскрипции совещания. Структурируй его в четкий протокол встречи в формате Markdown.
Включи следующие разделы:
1.  **Повестка дня**: (Основные обсуждавшиеся темы в виде списка)
2.  **Ключевые решения**: (Список принятых решений)
3.  **Задачи и следующие шаги (Action Items)**: (Список задач с указанием ответственных, если это возможно)

Текст транскрипции:
---
{text}"""
        },
        "PODCAST": {
            "name": "Шоу-ноуты для подкаста",
            "prompt": """Проанализируй транскрипцию эпизода подкаста. Создай подробные "шоу-ноуты" в формате Markdown.
Включи следующие разделы:
1.  **Краткое описание эпизода (Summary)**: (2-4 цепляющих предложения)
2.  **Таймкоды (Оглавление)**: (Список ключевых тем с указанием примерного времени начала)
3.  **Ключевые цитаты (Quotes)**: (Выбери 3-5 ярких и интересных цитат для соцсетей)
4.  **Упомянутые ресурсы**: (Книги, ссылки, инструменты, упомянутые в выпуске)

Текст транскрипции:
---
{text}"""
        },
        "COACHING": {
            "name": "Отчет по коуч-сессии",
            "prompt": """Проанализируй транскрипцию коуч-сессии. Подготовь структурированный отчет для клиента в формате Markdown.
Включи следующие разделы:
1.  **Основной запрос сессии**: (Главная тема или проблема, с которой пришел клиент)
2.  **Ключевые инсайты клиента**: (Важные моменты и осознания, озвученные клиентом)
3.  **Action Plan (Следующие шаги)**: (Конкретные шаги и упражнения для клиента после сессии)

Текст транскрипции:
---
{text}"""
        },
        "BRIEFING": {
            "name": "Выжимка из брифинга с клиентом",
            "prompt": """Проанализируй транскрипцию брифинга с клиентом. Сделай структурированную выжимку для исполнителя (например, копирайтера) в формате Markdown.
Включи следующие разделы:
1.  **Цель проекта**: (Что клиент хочет достичь в итоге?)
2.  **Целевая аудитория**: (К кому мы обращаемся?)
3.  **Ключевые сообщения (Key Messages)**: (Какие основные идеи нужно донести?)
4.  **Ограничения и требования**: (Что нельзя делать? Какие есть обязательные условия?)
5.  **Следующие шаги**: (Что требуется от исполнителя и от клиента?)

Текст транскрипции:
---
{text}"""
        }
    }

    def __init__(self):
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set. InsightService cannot function.")
        self.client = OpenAI(api_key=api_key)
        logger.info("InsightService initialized successfully.")

    def _get_completion(self, prompt: str, model: str = "gpt-4o", max_tokens: int = 1500) -> Optional[str]:
        """Приватный метод для вызова OpenAI API."""
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}", exc_info=True)
            return None

    def create_report(self, text: str, template_key: str) -> Optional[str]:
        """Генерирует структурированный отчет на основе выбранного шаблона."""
        if not text or not text.strip() or template_key not in self.REPORT_PROMPTS:
            return None

        prompt_template = self.REPORT_PROMPTS[template_key]["prompt"]
        prompt = prompt_template.format(text=text)

        return self._get_completion(prompt, max_tokens=2048)

    def get_summary(self, text: str) -> Optional[str]:
        """Генерирует простое саммари для текста."""
        if not text or not text.strip(): return None
        prompt = f"Summarize the key points of the following text concisely, in the same language as the original text:\n\n---\n\n{text}"
        return self._get_completion(prompt)

    def get_keywords(self, text: str) -> List[str]:
        """Извлекает ключевые слова из текста."""
        if not text or not text.strip(): return []
        prompt = f"Extract the 3-5 most important keywords from the following text. Return them as a JSON array of strings, like [\"keyword1\", \"keyword2\"]. Provide only the JSON array.\n\n---\n\n{text}"
        response_str = self._get_completion(prompt, max_tokens=200)

        if not response_str:
            return []

        try:
            keywords = json.loads(response_str)
            if isinstance(keywords, list):
                return [str(kw).strip() for kw in keywords]
        except json.JSONDecodeError:
            logger.warning(
                f"Failed to decode JSON from keywords response. Falling back to comma-separated parsing. Response: {response_str}")
            response_str = response_str.replace('"', '').replace("'", "").strip("[]")
            return [keyword.strip() for keyword in response_str.split(',')]

        return []