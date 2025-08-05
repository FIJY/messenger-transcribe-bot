# config.py - Централизованная конфигурация
import os
from typing import Dict, List
from pydantic import BaseSettings


class Settings(BaseSettings):
    """Настройки приложения"""
    # Telegram Bot
    TELEGRAM_TOKEN: str
    WEBHOOK_URL: str

    # OpenAI
    OPENAI_API_KEY: str

    # База данных
    MONGODB_URI: str
    DATABASE_NAME: str = "transcribe_bot"

    # Хранилище файлов
    S3_ENDPOINT_URL: str
    S3_ACCESS_KEY_ID: str
    S3_SECRET_ACCESS_KEY: str
    S3_BUCKET_NAME: str

    # Redis для Celery
    REDIS_URL: str

    # Разработка
    DEBUG: bool = False

    # Платежная система
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Создаем экземпляр настроек
settings = Settings()

# Тарифные планы
PLANS = {
    "free": {
        "name": "Бесплатный",
        "minutes_limit": 60,  # 1 час в месяц
        "processing_options": 1,
        "features": [
            "Транскрипция до 5 минут",
            "Базовое саммари",
            "1 опция обработки"
        ],
        "file_size_limit_mb": 25,
        "max_duration_minutes": 5
    },
    "basic": {
        "name": "Базовый",
        "minutes_limit": 300,  # 5 часов в месяц
        "processing_options": 3,
        "features": [
            "Транскрипция до 30 минут",
            "Все виды саммари",
            "Переводы на основные языки",
            "3 опции обработки",
            "Экспорт в TXT/DOCX"
        ],
        "file_size_limit_mb": 100,
        "max_duration_minutes": 30,
        "price_monthly": 999  # центы
    },
    "pro": {
        "name": "Профессиональный",
        "minutes_limit": 1800,  # 30 часов в месяц
        "processing_options": 10,
        "features": [
            "Неограниченная длительность файлов",
            "Все виды обработки",
            "Переводы на все языки",
            "До 10 опций обработки",
            "Экспорт во все форматы",
            "Приоритетная обработка",
            "API доступ"
        ],
        "file_size_limit_mb": 500,
        "max_duration_minutes": 240,  # 4 часа
        "price_monthly": 1999  # центы
    }
}

# Категории обработки контента
PROCESSING_CATEGORIES = {
    "basic": {
        "name": "📝 ОСНОВНОЕ",
        "always_available": True,
        "options": [
            {
                "code": "full_transcription",
                "name": "Полная транскрипция",
                "description": "Полный текст с временными метками",
                "default": True,
                "free": False  # Не считается в лимит
            },
            {
                "code": "summary",
                "name": "Краткое содержание",
                "description": "Основные тезисы и выводы",
                "default": False,
                "free": True
            },
            {
                "code": "keypoints",
                "name": "Ключевые моменты с таймкодами",
                "description": "Важные моменты с указанием времени",
                "default": False,
                "free": False
            }
        ]
    },
    "translation": {
        "name": "🌍 ПЕРЕВОД",
        "always_available": False,
        "min_plan": "basic",
        "options": [
            {
                "code": "translate_en",
                "name": "Английский",
                "description": "Перевод на английский язык",
                "target_lang": "en"
            },
            {
                "code": "translate_zh",
                "name": "Китайский",
                "description": "Перевод на китайский язык",
                "target_lang": "zh"
            },
            {
                "code": "translate_es",
                "name": "Испанский",
                "description": "Перевод на испанский язык",
                "target_lang": "es"
            },
            {
                "code": "translate_fr",
                "name": "Французский",
                "description": "Перевод на французский язык",
                "target_lang": "fr"
            },
            {
                "code": "translate_de",
                "name": "Немецкий",
                "description": "Перевод на немецкий язык",
                "target_lang": "de"
            },
            {
                "code": "translate_ja",
                "name": "Японский",
                "description": "Перевод на японский язык",
                "target_lang": "ja"
            },
            {
                "code": "translate_ko",
                "name": "Корейский",
                "description": "Перевод на корейский язык",
                "target_lang": "ko"
            },
            {
                "code": "translate_ar",
                "name": "Арабский",
                "description": "Перевод на арабский язык",
                "target_lang": "ar"
            }
        ]
    },
    "business": {
        "name": "💼 ДЛЯ РАБОТЫ",
        "always_available": False,
        "min_plan": "basic",
        "options": [
            {
                "code": "meeting_protocol",
                "name": "Протокол совещания",
                "description": "Структурированный протокол с решениями и задачами"
            },
            {
                "code": "action_items",
                "name": "Action Items с дедлайнами",
                "description": "Список задач с ответственными и сроками"
            },
            {
                "code": "executive_report",
                "name": "Отчет для руководства",
                "description": "Краткий отчет для топ-менеджмента"
            },
            {
                "code": "conclusions",
                "name": "Выводы и рекомендации",
                "description": "Основные выводы и рекомендации к действию"
            }
        ]
    },
    "content": {
        "name": "📱 ДЛЯ КОНТЕНТА",
        "always_available": False,
        "min_plan": "basic",
        "options": [
            {
                "code": "instagram_post",
                "name": "Пост для Instagram",
                "description": "Готовый пост с текстом и хештегами"
            },
            {
                "code": "shorts_clips",
                "name": "Нарезки для Shorts",
                "description": "Яркие моменты с таймкодами для коротких видео"
            },
            {
                "code": "youtube_notes",
                "name": "Show Notes для YouTube",
                "description": "Описание с главами и временными метками"
            },
            {
                "code": "presentation_cards",
                "name": "Карточки для презентации",
                "description": "Слайды с ключевыми тезисами"
            }
        ]
    },
    "education": {
        "name": "🎓 ДЛЯ УЧЕБЫ",
        "always_available": False,
        "min_plan": "basic",
        "options": [
            {
                "code": "lecture_notes",
                "name": "Конспект лекции",
                "description": "Структурированный конспект с основными темами"
            },
            {
                "code": "exam_questions",
                "name": "Вопросы для экзамена",
                "description": "Возможные вопросы и ответы по материалу"
            },
            {
                "code": "brief_summary",
                "name": "Краткий саммари",
                "description": "Сжатое изложение основных идей"
            },
            {
                "code": "glossary",
                "name": "Глоссарий терминов",
                "description": "Словарь ключевых понятий и определений"
            }
        ]
    },
    "parental": {
        "name": "👨‍👩‍👧‍👦 ДЛЯ РОДИТЕЛЕЙ",
        "always_available": False,
        "min_plan": "pro",
        "options": [
            {
                "code": "content_safety",
                "name": "Анализ безопасности контента",
                "description": "Проверка на возрастные ограничения и нежелательный контент"
            },
            {
                "code": "educational_value",
                "name": "Образовательная ценность",
                "description": "Оценка полезности контента для детей"
            },
            {
                "code": "parent_summary",
                "name": "Краткий пересказ для родителей",
                "description": "Понятное изложение содержания"
            },
            {
                "code": "discussion_topics",
                "name": "Список обсуждаемых тем",
                "description": "Темы для разговора с ребенком"
            },
            {
                "code": "time_markers",
                "name": "Временные метки важных моментов",
                "description": "Отметки моментов, требующих внимания"
            },
            {
                "code": "viewing_recommendations",
                "name": "Рекомендации по просмотру с детьми",
                "description": "Советы по совместному просмотру"
            }
        ]
    }
}

# Быстрые пакеты опций
QUICK_PACKS = {
    "business_meeting": {
        "label": "Для работы",
        "icon": "💼",
        "options": ["meeting_protocol", "action_items", "executive_report"],
        "description": "Полная обработка рабочих встреч"
    },
    "content_creation": {
        "label": "Для контента",
        "icon": "📱",
        "options": ["summary", "instagram_post", "shorts_clips"],
        "description": "Подготовка контента для соцсетей"
    },
    "education": {
        "label": "Для учебы",
        "icon": "🎓",
        "options": ["lecture_notes", "exam_questions", "glossary"],
        "description": "Обработка учебных материалов"
    },
    "analysis": {
        "label": "Анализ контента",
        "icon": "📊",
        "options": ["summary", "keypoints", "conclusions"],
        "description": "Глубокий анализ содержания"
    }
}

# Поддерживаемые языки интерфейса
SUPPORTED_LANGUAGES = {
    "ru": {"name": "Русский", "flag": "🇷🇺", "native": "Русский"},
    "en": {"name": "English", "flag": "🇺🇸", "native": "English"},
    "zh": {"name": "Chinese", "flag": "🇨🇳", "native": "中文"},
    "es": {"name": "Spanish", "flag": "🇪🇸", "native": "Español"},
    "fr": {"name": "French", "flag": "🇫🇷", "native": "Français"},
    "de": {"name": "German", "flag": "🇩🇪", "native": "Deutsch"},
    "ja": {"name": "Japanese", "flag": "🇯🇵", "native": "日本語"},
    "ko": {"name": "Korean", "flag": "🇰🇷", "native": "한국어"},
    "ar": {"name": "Arabic", "flag": "🇦🇪", "native": "العربية"},
    "km": {"name": "Khmer", "flag": "🇰🇭", "native": "ខ្មែរ"}
}

# Форматы экспорта файлов
EXPORT_FORMATS = {
    "txt": {
        "name": "Текстовый файл",
        "extension": ".txt",
        "mime_type": "text/plain",
        "encoding": "utf-8"
    },
    "docx": {
        "name": "Microsoft Word",
        "extension": ".docx",
        "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    },
    "pdf": {
        "name": "PDF документ",
        "extension": ".pdf",
        "mime_type": "application/pdf"
    },
    "srt": {
        "name": "Субтитры SRT",
        "extension": ".srt",
        "mime_type": "application/x-subrip"
    },
    "json": {
        "name": "JSON данные",
        "extension": ".json",
        "mime_type": "application/json"
    }
}

# Лимиты файлов
FILE_LIMITS = {
    "free": {
        "max_size_mb": 25,
        "max_duration_minutes": 5,
        "supported_formats": ["mp3", "wav", "ogg", "m4a"]
    },
    "basic": {
        "max_size_mb": 100,
        "max_duration_minutes": 30,
        "supported_formats": ["mp3", "wav", "ogg", "m4a", "mp4", "mov", "avi"]
    },
    "pro": {
        "max_size_mb": 500,
        "max_duration_minutes": 240,
        "supported_formats": ["mp3", "wav", "ogg", "m4a", "flac", "mp4", "mov", "avi", "mkv", "webm"]
    }
}

# Статусы обработки
PROCESSING_STATUSES = {
    "pending": "Ожидает обработки",
    "downloading": "Скачивание файла",
    "uploaded": "Файл загружен",
    "transcribing": "Транскрибация",
    "processing": "Обработка",
    "completed": "Завершено",
    "failed": "Ошибка"
}