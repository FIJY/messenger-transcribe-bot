# services/processing_config.py
# This file centralizes all settings for processing options, quick packs, and tariff plans.

# Defines the limits for each subscription plan.
# 'name' is for display, 'checkboxes' is the functional limit.
TARIFF_LIMITS = {
    "free": {"name": "Бесплатный", "checkboxes": 1},
    "base": {"name": "Базовый", "checkboxes": 2},
    "standard": {"name": "Стандарт", "checkboxes": 3},
    "pro": {"name": "Про", "checkboxes": 5},
}

# Configuration for all available checkboxes, grouped by category.
# 'code' is the internal identifier used in logic.
# 'label' is the text displayed on the button.
CHECKBOX_CONFIG = {
    "📝 ОСНОВНОЕ": [
        {"code": "summary", "label": "Краткое содержание"},
        {"code": "keywords", "label": "Ключевые моменты с таймкодами"},
    ],
    "💼 ДЛЯ РАБОТЫ": [
        {"code": "protocol", "label": "Протокол совещания"},
        {"code": "action_items", "label": "Action Items с дедлайнами"},
        {"code": "report", "label": "Отчет для руководства"},
        {"code": "conclusions", "label": "Выводы и рекомендации"},
    ],
    "📱 ДЛЯ КОНТЕНТА": [
        {"code": "post_instagram", "label": "Пост для Instagram"},
        {"code": "shorts_ideas", "label": "Нарезки для Shorts"},
        {"code": "youtube_notes", "label": "Show Notes для YouTube"},
        {"code": "presentation_cards", "label": "Карточки для презентации"},
    ],
    "🎓 ДЛЯ УЧЕБЫ": [
        {"code": "lecture_summary", "label": "Конспект лекции"},
        {"code": "exam_questions", "label": "Вопросы для экзамена"},
        {"code": "glossary", "label": "Глоссарий терминов"},
    ],
    # Note: Translation is handled by a separate menu and is not part of the checkbox system
    # to avoid complexity and hitting API limits too quickly. It remains a separate feature.
}

# Pre-configured sets of options for common use cases.
# 'label' is the button text, 'options' is a list of 'codes' from CHECKBOX_CONFIG.
QUICK_PACKS = {
    "meeting": {"label": "🔥 Для совещания", "options": ["protocol", "action_items", "report"]},
    "content": {"label": "📱 Для контента", "options": ["summary", "post_instagram", "shorts_ideas"]},
    "study": {"label": "🎓 Для учебы", "options": ["lecture_summary", "exam_questions", "glossary"]},
    "business": {"label": "💼 Для бизнеса", "options": ["keywords", "conclusions", "report"]},
}

