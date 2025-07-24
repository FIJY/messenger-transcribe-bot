# services/insight_service.py
import os
import logging
from openai import OpenAI
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class InsightService:
    def __init__(self):
        self.api_key = os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            logger.warning("OPENAI_API_KEY is not set. Insight services will be disabled.")
            self.client = None
        else:
            self.client = OpenAI(api_key=self.api_key)

        # Ваша существующая функция для отчетов
        self.REPORT_PROMPTS: Dict[str, Dict[str, str]] = {
            "MEETING_SUMMARY": {
                "name": "Meeting Summary",
                "prompt": "Based on the following meeting transcript, generate a concise summary that includes the main topics discussed, key decisions made, and action items assigned to individuals."
            },
            "CONTENT_IDEAS": {
                "name": "Content Ideas",
                "prompt": "Analyze the following text and brainstorm 5 creative content ideas (like blog posts, social media updates, or video scripts) based on the core themes and topics."
            }
            # ... другие шаблоны отчетов
        }

    # Ваша существующая функция для простого саммари (без изменений)
    def get_summary(self, text: str) -> Optional[str]:
        if not self.client:
            return "Summary service is unavailable."
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system",
                     "content": "You are an expert summarizer. Create a concise summary of the following text."},
                    {"role": "user", "content": text}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error getting summary from OpenAI: {e}")
            return None

    # Ваша существующая функция для создания отчетов (без изменений)
    def create_report(self, text: str, template_key: str) -> Optional[str]:
        if not self.client:
            return "Report service is unavailable."

        template = self.REPORT_PROMPTS.get(template_key)
        if not template:
            logger.warning(f"Invalid report template key: {template_key}")
            return "Invalid report template selected."

        try:
            response = self.client.chat.completions.create(
                model="gpt-4-turbo",  # Используем более мощную модель для отчетов
                messages=[
                    {"role": "system", "content": template["prompt"]},
                    {"role": "user", "content": text}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error creating report from OpenAI: {e}")
            return None

    # ИСПРАВЛЕННАЯ функция для ответов на вопросы
    def get_answer_from_text(self, context: str, question: str) -> Optional[str]:
        """
        Отвечает на вопрос пользователя, основываясь на предоставленном тексте.
        """
        if not self.client:
            return "Sorry, the question answering service is currently unavailable."

        try:
            logger.info(f"Requesting answer from OpenAI. Question: {question[:50]}...")

            # Новый, более "умный" промпт
            system_prompt = (
                "You are a helpful and intelligent assistant. Your task is to answer the user's question based on the provided text. "
                "Be comprehensive and use all relevant information from the text. "
                "If the text lists items, try to extract all of them. "
                "Answer in the same language as the user's question."
            )
            user_prompt = f"Context:\n---\n{context}\n---\n\nQuestion: {question}"

            response = self.client.chat.completions.create(
                model="gpt-4-turbo", # Используем более умную модель для ответов на вопросы
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
            )

            answer = response.choices[0].message.content
            logger.info("Successfully received answer from OpenAI.")
            return answer

        except Exception as e:
            logger.error(f"Error getting answer from OpenAI: {e}", exc_info=True)
            return "An error occurred while trying to answer your question. Please try again later."
