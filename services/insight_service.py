# services/insight_service.py
import os
import logging
from openai import OpenAI
from typing import List, Optional

logger = logging.getLogger(__name__)

PROMPTS = {
    "summarize": "You are a helpful assistant. Summarize the key points of the following text concisely, in the same language as the original text:\n\n---\n\n{text}",
    "find_keywords": "You are a helpful assistant. Extract the 3-5 most important keywords or key phrases from the following text. The keywords should be in the original language of the text. Return them as a comma-separated list:\n\n---\n\n{text}"
}

class InsightService:
    def __init__(self):
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set. InsightService cannot function.")
        self.client = OpenAI(api_key=api_key)
        logger.info("InsightService initialized successfully.")

    def _get_completion(self, prompt: str, model: str = "gpt-4o") -> Optional[str]:
        """Приватный метод для вызова OpenAI API."""
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=1000
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}", exc_info=True)
            return None

    def get_summary(self, text: str) -> Optional[str]:
        """Генерирует саммари для текста."""
        if not text or not text.strip(): return None
        prompt = PROMPTS["summarize"].format(text=text)
        return self._get_completion(prompt)

    def get_keywords(self, text: str) -> List[str]:
        """Извлекает ключевые слова из текста."""
        if not text or not text.strip(): return []
        prompt = PROMPTS["find_keywords"].format(text=text)
        keywords_str = self._get_completion(prompt)
        if keywords_str:
            return [keyword.strip() for keyword in keywords_str.split(',')]
        return []