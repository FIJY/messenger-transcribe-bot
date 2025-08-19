# config.py - ОБНОВЛЕННАЯ версия с новыми категориями

import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    """Настройки приложения"""

    def __init__(self):
        # Обязательные переменные
        self.TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
        self.OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
        self.MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
        self.DATABASE_NAME = os.getenv('DATABASE_NAME', 'transcribe_bot_db')
        self.REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')

        # Опциональные
        self.WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')
        self.DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'

        # Лимиты файлов
        self.MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB', '2048'))
        self.MAX_DURATION_MINUTES = int(os.getenv('MAX_DURATION_MINUTES', '180'))
        self.CHUNK_SIZE_BYTES = int(os.getenv('CHUNK_SIZE_BYTES', '1048576'))
        self.MEMORY_LIMIT_MB = int(os.getenv('MEMORY_LIMIT_MB', '200'))

settings = Settings()

# Проверки
if not settings.TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не установлен!")

# НОВАЯ СТРУКТУРА: Тарифные планы с минутами
SUBSCRIPTION_PLANS = {
    "trial": {
        "name": "🆓 Триал", 
        "minutes": 15, 
        "price_rub": 0,
        "description": "Бесплатно для знакомства"
    },
    "starter": {
        "name": "💰 Стартовый", 
        "minutes": 120, 
        "price_rub": 399,
        "description": "2 часа обработки"
    },
    "work": {
        "name": "💼 Рабочий", 
        "minutes": 220, 
        "price_rub": 699,
        "description": "3.5 часа + приоритет"
    },
    "pro": {
        "name": "🚀 Профи", 
        "minutes": 500, 
        "price_rub": 1499,
        "description": "8+ часов + все форматы"
    }
}

# ПОПУЛЯРНЫЕ ФОРМАТЫ (показываем сразу после транскрипции)
QUICK_FORMATS = {
    "protocol": {
        "emoji": "📋",
        "name": "Протокол",
        "description": "Решения + задачи + ответственные",
        "cost_minutes": 0,  # БЕСПЛАТНО для триала
        "category": "work"
    },
    "instagram": {
        "emoji": "📱",
        "name": "Instagram",
        "description": "Пост + хештеги",
        "cost_minutes": 0,  # БЕСПЛАТНО для триала
        "category": "content"
    },
    "summary": {
        "emoji": "🎓",
        "name": "Конспект",
        "description": "Структурированные заметки",
        "cost_minutes": 0,  # БЕСПЛАТНО для триала
        "category": "study"
    },
    "translate_en": {
        "emoji": "🌍",
        "name": "→ EN",
        "description": "Перевод на английский",
        "cost_minutes": 0,  # БЕСПЛАТНО для триала
        "category": "translate"
    }
}

PROCESSING_CATEGORIES = {
    "work": {
        "emoji": "💼",
        "name": "РАБОТА",
        "formats": {
            "protocol": {
                "name": "📋 Протокол совещания",
                "description": "Решения + задачи + ответственные + дедлайны",
                "cost_minutes": 0  # БЕСПЛАТНО
            },
            "action_items": {
                "name": "⚡ Action Items",
                "description": "Список задач с ответственными",
                "cost_minutes": 0  # БЕСПЛАТНО
            },
            "report": {
                "name": "📊 Отчет руководству",
                "description": "Краткий отчет для менеджмента",
                "cost_minutes": 0  # БЕСПЛАТНО
            },
            "insights": {
                "name": "💡 Выводы и рекомендации",
                "description": "Ключевые инсайты и следующие шаги",
                "cost_minutes": 0  # БЕСПЛАТНО
            }
        }
    },
    "content": {
        "emoji": "📱",
        "name": "КОНТЕНТ",
        "formats": {
            "instagram": {
                "name": "📸 Instagram пост",
                "description": "Текст + хештеги + призыв к действию",
                "cost_minutes": 0  # БЕСПЛАТНО
            },
            "youtube": {
                "name": "🎬 YouTube описание",
                "description": "Show Notes + главы + временные метки",
                "cost_minutes": 0  # БЕСПЛАТНО
            },
            "shorts": {
                "name": "⚡ Нарезки для Shorts",
                "description": "Яркие моменты + таймкоды",
                "cost_minutes": 0  # БЕСПЛАТНО
            },
            "tiktok": {
                "name": "🎵 TikTok хуки",
                "description": "Цепляющие фразы для вирусных видео",
                "cost_minutes": 0  # БЕСПЛАТНО
            }
        }
    },
    "study": {
        "emoji": "🎓",
        "name": "УЧЕБА",
        "formats": {
            "lecture_notes": {
                "name": "📝 Конспект лекции",
                "description": "Структурированные заметки",
                "cost_minutes": 0  # БЕСПЛАТНО
            },
            "exam_questions": {
                "name": "❓ Вопросы для экзамена",
                "description": "Потенциальные вопросы по материалу",
                "cost_minutes": 0  # БЕСПЛАТНО
            },
            "summary": {
                "name": "📄 Краткий саммари",
                "description": "Основные тезисы",
                "cost_minutes": 0  # БЕСПЛАТНО
            },
            "glossary": {
                "name": "📚 Глоссарий терминов",
                "description": "Словарь ключевых понятий",
                "cost_minutes": 0  # БЕСПЛАТНО
            }
        }
    },
    "translate": {
        "emoji": "🌍",
        "name": "ПЕРЕВОДЫ",
        "formats": {
            "translate_en": {"name": "🇺🇸 Английский", "cost_minutes": 0},
            "translate_zh": {"name": "🇨🇳 Китайский", "cost_minutes": 0},
            "translate_es": {"name": "🇪🇸 Испанский", "cost_minutes": 0},
            "translate_fr": {"name": "🇫🇷 Французский", "cost_minutes": 0},
            "translate_de": {"name": "🇩🇪 Немецкий", "cost_minutes": 0},
            "translate_ja": {"name": "🇯🇵 Японский", "cost_minutes": 0},
            "translate_ko": {"name": "🇰🇷 Корейский", "cost_minutes": 0},
            "translate_ar": {"name": "🇦🇪 Арабский", "cost_minutes": 0}
        }
    },
    "family": {
        "emoji": "👨‍👩‍👧‍👦",
        "name": "ДЛЯ СЕМЬИ",
        "formats": {
            "safety_check": {
                "name": "🛡️ Анализ безопасности",
                "description": "Возрастные ограничения контента",
                "cost_minutes": 0  # БЕСПЛАТНО
            },
            "educational_value": {
                "name": "🎓 Образовательная ценность",
                "description": "Что полезного в материале",
                "cost_minutes": 0  # БЕСПЛАТНО
            },
            "parent_summary": {
                "name": "👨‍👩‍👧‍👦 Краткий пересказ",
                "description": "Основное содержание для родителей",
                "cost_minutes": 0  # БЕСПЛАТНО
            }
        }
    }
}

# ЭКСПОРТ ФОРМАТЫ
EXPORT_FORMATS = {
    "txt": {"emoji": "📄", "name": "Текст (.txt)", "mime": "text/plain"},
    "docx": {"emoji": "📋", "name": "Word (.docx)", "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    "pdf": {"emoji": "📑", "name": "PDF отчет", "mime": "application/pdf"},
    "srt": {"emoji": "📜", "name": "Субтитры (.srt)", "mime": "text/plain"}
}

# Поддерживаемые языки интерфейса  
SUPPORTED_LANGUAGES = {
    "ru": {"name": "Russian", "flag": "🇷🇺", "native": "Русский"},
    "en": {"name": "English", "flag": "🇺🇸", "native": "English"}
}

# В конец config.py добавьте эти строки для обратной совместимости:

# =============================================================================
# ОБРАТНАЯ СОВМЕСТИМОСТЬ (чтобы старые импорты работали)
# =============================================================================

# Создаем старую структуру PROCESSING_TYPES из новых категорий
PROCESSING_TYPES = {}

# Добавляем быстрые форматы
for format_key, format_info in QUICK_FORMATS.items():
    PROCESSING_TYPES[format_key] = {
        "code": format_key,
        "name": f"{format_info['emoji']} {format_info['name']}",
        "category": format_info["category"]
    }

# Добавляем все форматы из категорий
for category_key, category_info in PROCESSING_CATEGORIES.items():
    for format_key, format_info in category_info.get("formats", {}).items():
        if format_key not in PROCESSING_TYPES:  # Не перезаписываем быстрые форматы
            PROCESSING_TYPES[format_key] = {
                "code": format_key,
                "name": format_info["name"],
                "category": category_key
            }

# Старые PLANS для совместимости (переименовываем из SUBSCRIPTION_PLANS)
PLANS = {
    "free": {
        "name": "Бесплатный",
        "processing_options": 4,
        "minutes_limit": 15,
        "features": ["Транскрипция", "4 опции обработки", "Базовое AI-резюме"]
    },
    "starter": {
        "name": "Стартовый",
        "processing_options": 8,
        "minutes_limit": 120,
        "features": ["2 часа транскрипции", "8 опций обработки", "Все виды AI-обработки"]
    },
    "work": {
        "name": "Рабочий",
        "processing_options": 15,
        "minutes_limit": 220,
        "features": ["3.5 часа транскрипции", "15 опций обработки", "Приоритетная обработка"]
    },
    "pro": {
        "name": "Профессиональный",
        "processing_options": 25,
        "minutes_limit": 500,
        "features": ["8+ часов транскрипции", "Все опции", "Экспорт файлов", "API доступ"]
    }
}