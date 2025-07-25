# services/processing_config.py
# Этот файл централизует все настройки для опций обработки, быстрых пакетов и тарифных планов.

# Определяет лимиты для каждого тарифного плана.
# 'name' - для отображения, 'checkboxes' - функциональный лимит.
TARIFF_LIMITS = {
    "free": {"name": "Бесплатный", "checkboxes": 1},
    "base": {"name": "Базовый", "checkboxes": 2},
    "standard": {"name": "Стандарт", "checkboxes": 3},
    "pro": {"name": "Про", "checkboxes": 5},
}

# Конфигурация всех доступных галочек, сгруппированных по категориям.
# 'code' - внутренний идентификатор.
# 'label' - текст на кнопке.
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
}

# Предустановленные наборы опций для частых сценариев.
QUICK_PACKS = {
    "meeting": {"label": "🔥 Для совещания", "options": ["protocol", "action_items", "report"]},
    "content": {"label": "📱 Для контента", "options": ["summary", "post_instagram", "shorts_ideas"]},
    "study": {"label": "🎓 Для учебы", "options": ["lecture_summary", "exam_questions", "glossary"]},
    "business": {"label": "💼 Для бизнеса", "options": ["keywords", "conclusions", "report"]},
}
