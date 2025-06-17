# Лимиты для бесплатных пользователей
FREE_DAILY_LIMIT = 10
MAX_AUDIO_DURATION_FREE = 300  # 5 минут в секундах для бесплатных
MAX_AUDIO_DURATION_PREMIUM = 3600  # 60 минут в секундах для премиум

# Размер файла
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

# Типы подписок
SUBSCRIPTION_TYPES = {
    'free': {
        'name': 'Free',
        'daily_limit': FREE_DAILY_LIMIT,
        'max_duration': MAX_AUDIO_DURATION_FREE,
        'features': [
            'До 10 транскрипций в день',
            'Файлы до 5 минут',
            'Автоопределение языка',
            'Базовая поддержка'
        ]
    },
    'premium': {
        'name': 'Premium',
        'daily_limit': None,  # Безлимит
        'max_duration': MAX_AUDIO_DURATION_PREMIUM,
        'features': [
            'Безлимитные транскрипции',
            'Файлы до 60 минут',
            'Приоритетная обработка',
            'История транскрипций',
            'API доступ'
        ],
        'price': 4.99
    }
}

# Поддерживаемые языки
SUPPORTED_LANGUAGES = {
    'af': 'Afrikaans',
    'ar': 'العربية',
    'hy': 'Հայերեն',
    'az': 'Azərbaycan',
    'be': 'Беларуская',
    'bs': 'Bosanski',
    'bg': 'Български',
    'ca': 'Català',
    'zh': '中文',
    'hr': 'Hrvatski',
    'cs': 'Čeština',
    'da': 'Dansk',
    'nl': 'Nederlands',
    'en': 'English',
    'et': 'Eesti',
    'fi': 'Suomi',
    'fr': 'Français',
    'gl': 'Galego',
    'de': 'Deutsch',
    'el': 'Ελληνικά',
    'he': 'עברית',
    'hi': 'हिन्दी',
    'hu': 'Magyar',
    'is': 'Íslenska',
    'id': 'Indonesia',
    'it': 'Italiano',
    'ja': '日本語',
    'kn': 'ಕನ್ನಡ',
    'kk': 'Қазақ',
    'km': 'ខ្មែរ',
    'ko': '한국어',
    'lv': 'Latviešu',
    'lt': 'Lietuvių',
    'mk': 'Македонски',
    'ms': 'Melayu',
    'mr': 'मराठी',
    'mi': 'Māori',
    'ne': 'नेपाली',
    'no': 'Norsk',
    'fa': 'فارسی',
    'pl': 'Polski',
    'pt': 'Português',
    'ro': 'Română',
    'ru': 'Русский',
    'sr': 'Српски',
    'sk': 'Slovenčina',
    'sl': 'Slovenščina',
    'es': 'Español',
    'sw': 'Kiswahili',
    'sv': 'Svenska',
    'tl': 'Tagalog',
    'ta': 'தமிழ்',
    'th': 'ไทย',
    'tr': 'Türkçe',
    'uk': 'Українська',
    'ur': 'اردو',
    'vi': 'Tiếng Việt',
    'cy': 'Cymraeg'
}