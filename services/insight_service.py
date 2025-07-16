# services/insight_service.py
import os
import logging
import json
from openai import OpenAI
from typing import List, Optional

logger = logging.getLogger(__name__)


class InsightService:
    # ДОБАВЛЕНЫ ВСЕ НЕДОСТАЮЩИЕ ШАБЛОНЫ
    REPORT_PROMPTS = {
        "MEETING": {
            "name": "Meeting Minutes",
            "prompt": """You are an expert report generator. Analyze the following meeting transcript.
**RULE: You MUST generate the entire report, including all headers and content, in the exact same language as the original transcript.** Do not translate.
Structure it into clear meeting minutes in Markdown, including these sections:
1.  **Agenda**: (Main topics discussed)
2.  **Key Decisions**: (List of decisions made)
3.  **Action Items**: (List of tasks, assigning responsible people if possible)

Transcript:
---
{text}"""
        },
        "PODCAST": {
            "name": "Podcast Show Notes",
            "prompt": """You are an expert report generator. Analyze the following podcast episode transcript.
**RULE: You MUST generate the entire report, including all headers and content, in the exact same language as the original transcript.** Do not translate.
Create detailed show notes in Markdown, including these sections:
1.  **Episode Summary**: (2-4 engaging sentences)
2.  **Timestamps / Chapters**: (List of key topics with approximate start times)
3.  **Key Quotes**: (3-5 powerful and interesting quotes for social media)
4.  **Mentioned Resources**: (Books, links, or tools mentioned)

Transcript:
---
{text}"""
        },
        "COACHING": {
            "name": "Coaching Session Report",
            "prompt": """You are an expert report generator. Analyze the following coaching session transcript.
**RULE: You MUST generate the entire report, including all headers and content, in the exact same language as the original transcript.** Do not translate.
Prepare a structured report for the client in Markdown, including these sections:
1.  **Main Session Goal**: (The primary topic or problem the client brought)
2.  **Client's Key Insights**: (Important "aha" moments and realizations voiced by the client)
3.  **Action Plan**: (Specific next steps and exercises for the client)

Transcript:
---
{text}"""
        },
        "BRIEFING": {
            "name": "Client Briefing Summary",
            "prompt": """You are an expert report generator. Analyze the following client briefing transcript.
**RULE: You MUST generate the entire report, including all headers and content, in the exact same language as the original transcript.** Do not translate.
Create a structured summary for a contractor (e.g., a copywriter) in Markdown, including these sections:
1.  **Project Goal**: (What does the client want to achieve?)
2.  **Target Audience**: (Who are we addressing?)
3.  **Key Messages**: (What are the main ideas to convey?)
4.  **Constraints & Requirements**: (What are the "don'ts" and mandatory conditions?)
5.  **Next Steps**: (What is required from the contractor and the client?)

Transcript:
---
{text}"""
        },
        "PARTNERSHIP_MEETING": {
            "name": "Partnership Discussion Analysis",
            "prompt": """You are an expert report generator. Analyze the following partnership discussion transcript.
**RULE: You MUST generate the entire report, including all headers and content, in the exact same language as the original transcript.** Do not translate.
Create a partnership analysis in Markdown, including these sections:
1. **Partnership Objectives**: (What both parties want to achieve)
2. **Value Propositions**: (What each partner brings to the table)
3. **Concerns & Risks**: (Hesitations or potential issues raised)
4. **Next Steps**: (Immediate actions and timeline)

Transcript:
---
{text}"""
        },
        "BUSINESS_NEGOTIATION": {
            "name": "Business Negotiation Summary",
            "prompt": """You are an expert report generator. Analyze the following business negotiation transcript.
**RULE: You MUST generate the entire report, including all headers and content, in the exact same language as the original transcript.** Do not translate.
Create a negotiation summary in Markdown, including these sections:
1. **Negotiation Goals**: (What each party initially wanted)
2. **Deal Points Agreed**: (Terms that both parties accepted)
3. **Outstanding Issues**: (Unresolved points requiring further discussion)

Transcript:
---
{text}"""
        },
        "DUE_DILIGENCE": {
            "name": "Due Diligence Review",
            "prompt": """You are an expert report generator. Analyze the following due diligence discussion transcript.
**RULE: You MUST generate the entire report, including all headers and content, in the exact same language as the original transcript.** Do not translate.
Create a due diligence analysis in Markdown, including these sections:
1. **Company Overview**: (Target company profile and business model)
2. **Financial Health**: (Revenue, profitability, cash flow discussions)
3. **Red Flags**: (Concerns, risks, or problematic areas identified)
4. **Growth Opportunities**: (Potential for expansion or improvement)

Transcript:
---
{text}"""
        },
        "CONFLICT_RESOLUTION": {
            "name": "Partnership Conflict Analysis",
            "prompt": """You are an expert report generator. Analyze the following partnership conflict resolution transcript.
**RULE: You MUST generate the entire report, including all headers and content, in the exact same language as the original transcript.** Do not translate.
Create a conflict analysis in Markdown, including these sections:
1. **Core Issues**: (Root causes of the disagreement)
2. **Each Party's Position**: (What each partner claims or demands)
3. **Agreements Reached**: (Any points of consensus or compromise)
4. **Relationship Repair**: (Steps needed to rebuild trust and collaboration)

Transcript:
---
{text}"""
        },
        "SALES_CALL": {
            "name": "Sales Call Analysis",
            "prompt": """You are an expert report generator. Analyze the following sales call transcript.
**RULE: You MUST generate the entire report, including all headers and content, in the exact same language as the original transcript.** Do not translate.
Create a sales call analysis in Markdown, including these sections:
1. **Prospect Profile**: (Company/person details and current situation)
2. **Pain Points Identified**: (Problems the prospect mentioned)
3. **Objections Raised**: (Concerns or hesitations expressed)
4. **Next Steps**: (Follow-up actions and commitments)

Transcript:
---
{text}"""
        },
        "INTERVIEW": {
            "name": "Interview Summary",
            "prompt": """You are an expert report generator. Analyze the following interview transcript.
**RULE: You MUST generate the entire report, including all headers and content, in the exact same language as the original transcript.** Do not translate.
Create a comprehensive interview summary in Markdown, including these sections:
1. **Candidate Profile**: (Key background and experience)
2. **Strengths**: (Notable skills and positive traits)
3. **Areas of Concern**: (Potential weaknesses or gaps)
4. **Recommendation**: (Hire/No Hire with brief reasoning)

Transcript:
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
        if not text or not text.strip() or template_key not in self.REPORT_PROMPTS:
            logger.error(f"Template key '{template_key}' not found in REPORT_PROMPTS.")
            return None

        prompt_template = self.REPORT_PROMPTS[template_key]["prompt"]
        prompt = prompt_template.format(text=text)

        return self._get_completion(prompt, max_tokens=2048)

    def get_summary(self, text: str) -> Optional[str]:
        if not text or not text.strip(): return None
        prompt = f"You are an expert summarizer. Your task is to summarize the following text. **RULE: You MUST write the summary in the exact same language as the original text provided below.** Do not translate. Respond only with the summary.\n\nText to summarize:\n---\n{text}"
        return self._get_completion(prompt)

    def get_keywords(self, text: str) -> List[str]:
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