# config/transcrib_suggestion_config.py

# === СПИСОК №1: ДЛЯ ИСПРАВЛЕНИЯ ЯЗЫКА ТРАНСКРИПЦИИ ===
# Языки, которые, скорее всего, будут использовать в регионе.
DEFAULT_POPULAR_TRANSCRIPTION_LANGS = [
    {'code': 'km', 'title': '🇰🇭 KM'},
    {'code': 'en', 'title': '🇬🇧 EN'},
    {'code': 'th', 'title': '🇹🇭 TH'},
    {'code': 'vi', 'title': '🇻🇳 VI'},
    {'code': 'zh', 'title': '🇨🇳 ZH'},
    {'code': 'ru', 'title': '🇷🇺 RU'},
]

# === СПИСОК №2: ДЛЯ ВЫБОРА ЯЗЫКА ПЕРЕВОДА ===
# Популярные международные языки, на которые чаще всего переводят.
DEFAULT_POPULAR_TRANSLATION_LANGS = [
    {'code': 'en', 'title': 'to English'},
    {'code': 'ru', 'title': 'на Русский'},
    {'code': 'zh', 'title': '到中文'},
    {'code': 'th', 'title': 'เป็นภาษาไทย'},
    {'code': 'fr', 'title': 'en Français'},
    {'code': 'de', 'title': 'auf Deutsch'},
]

# Полный словарь для распознавания языков, введенных текстом.
SUPPORTED_LANGUAGES_MAP = {
    'afrikaans': 'af', 'af': 'af', 'arabic': 'ar', 'ar': 'ar', 'armenian': 'hy', 'hy': 'hy',
    'azerbaijani': 'az', 'az': 'az', 'belarusian': 'be', 'be': 'be', 'bosnian': 'bs', 'bs': 'bs',
    'bulgarian': 'bg', 'bg': 'bg', 'catalan': 'ca', 'ca': 'ca', 'chinese': 'zh', 'zh': 'zh',
    'croatian': 'hr', 'hr': 'hr', 'czech': 'cs', 'cs': 'cs', 'danish': 'da', 'da': 'da',
    'dutch': 'nl', 'nl': 'nl', 'english': 'en', 'en': 'en', 'estonian': 'et', 'et': 'et',
    'finnish': 'fi', 'fi': 'fi', 'french': 'fr', 'fr': 'fr', 'galician': 'gl', 'gl': 'gl',
    'german': 'de', 'de': 'de', 'greek': 'el', 'el': 'el', 'hebrew': 'he', 'he': 'he',
    'hindi': 'hi', 'hi': 'hi', 'hungarian': 'hu', 'hu': 'hu', 'icelandic': 'is', 'is': 'is',
    'indonesian': 'id', 'id': 'id', 'italian': 'it', 'it': 'it', 'japanese': 'ja', 'ja': 'ja',
    'kannada': 'kn', 'kn': 'kn', 'kazakh': 'kk', 'kk': 'kk', 'khmer': 'km', 'km': 'km',
    'korean': 'ko', 'ko': 'ko', 'latvian': 'lv', 'lv': 'lv', 'lithuanian': 'lt', 'lt': 'lt',
    'macedonian': 'mk', 'mk': 'mk', 'malay': 'ms', 'ms': 'ms', 'marathi': 'mr', 'mr': 'mr',
    'maori': 'mi', 'mi': 'mi', 'nepali': 'ne', 'ne': 'ne', 'norwegian': 'no', 'no': 'no',
    'persian': 'fa', 'fa': 'fa', 'polish': 'pl', 'pl': 'pl', 'portuguese': 'pt', 'pt': 'pt',
    'romanian': 'ro', 'ro': 'ro', 'russian': 'ru', 'ru': 'ru', 'serbian': 'sr', 'sr': 'sr',
    'slovak': 'sk', 'sk': 'sk', 'slovenian': 'sl', 'sl': 'sl', 'spanish': 'es', 'es': 'es',
    'swahili': 'sw', 'sw': 'sw', 'swedish': 'sv', 'sv': 'sv', 'tagalog': 'tl', 'tl': 'tl',
    'tamil': 'ta', 'ta': 'ta', 'thai': 'th', 'th': 'th', 'turkish': 'tr', 'tr': 'tr',
    'ukrainian': 'uk', 'uk': 'uk', 'urdu': 'ur', 'ur': 'ur', 'vietnamese': 'vi', 'vi': 'vi',
    'welsh': 'cy', 'cy': 'cy'
}