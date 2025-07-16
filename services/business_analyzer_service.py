# services/business_analyzer_service.py
import os
import logging
import json
from openai import OpenAI
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)


class BusinessAnalyzerService:
    # ИСПРАВЛЕНИЕ: Все фигурные скобки в JSON-примере экранированы (удвоены)
    MASTER_PROMPT = """You are an expert business analyst. Analyze the following transcript of a business meeting or negotiation.
**RULE: You MUST generate the entire analysis in the exact same language as the original transcript.** Do not translate.

Your task is to produce a single, valid JSON object with the following structure. Fill in each key based on the transcript content.

{{
  "summary": "A concise summary of the entire discussion.",
  "keywords": ["keyword1", "keyword2", "keyword3"],
  "action_items": [
    {{"task": "The specific action to be taken", "assignee": "Person responsible, if mentioned", "deadline": "Deadline, if mentioned"}}
  ],
  "sentiment": {{
    "overall": "positive | negative | neutral",
    "key_emotions": ["emotion1", "emotion2"]
  }},
  "dynamics": {{
    "power_balance": "Description of who holds more leverage and why.",
    "trust_level": "Description of the level of trust or distrust observed.",
    "communication_style": "Description of the communication style (e.g., collaborative, confrontational)."
  }},
  "deal_terms": {{
    "financial": ["List of all financial figures, percentages, and monetary amounts discussed."],
    "legal_conditions": ["List of all legal conditions, responsibilities, or restrictions mentioned."]
  }},
  "risk_assessment": {{
    "key_risks": ["A list of the main risks or concerns raised by either party."],
    "deal_breakers": ["A list of potential deal-breakers or non-negotiable points."]
  }},
  "next_agenda": ["A list of suggested agenda items for the next meeting based on unresolved issues."]
}}

Transcript:
---
{text}
"""

    def __init__(self):
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set. BusinessAnalyzerService cannot function.")
        self.client = OpenAI(api_key=api_key)
        logger.info("BusinessAnalyzerService initialized successfully.")

    def _get_completion(self, prompt: str, model: str = "gpt-4o", max_tokens: int = 4000) -> Optional[str]:
        """Приватный метод для вызова OpenAI API с поддержкой JSON mode."""
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=max_tokens,
                response_format={"type": "json_object"}
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error calling OpenAI API for business analysis: {e}", exc_info=True)
            return None

    def run_comprehensive_analysis(self, text: str) -> Optional[Dict]:
        """
        Выполняет полный бизнес-анализ текста с помощью одного запроса к API.
        Возвращает словарь с результатами или None в случае ошибки.
        """
        if not text or not text.strip():
            return None

        prompt = self.MASTER_PROMPT.format(text=text)
        response_str = self._get_completion(prompt)

        if not response_str:
            return None

        try:
            return json.loads(response_str)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON from comprehensive analysis: {response_str}")
            return None