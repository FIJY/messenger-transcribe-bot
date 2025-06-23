# config/transcrib_suggestion_config.py

# Список языков, которые будут предложены пользователю в виде кнопок
# для быстрой коррекции языка.
SUPPORTED_LANGUAGES_FOR_RETRY = [
    # ==> ИЗМЕНЕНЫ ПОЛЯ 'title' <==
    {'code': 'km', 'title': '🇰🇭 KM'},
    {'code': 'en', 'title': '🇬🇧 EN'},
    {'code': 'ru', 'title': '🇷🇺 RU'},
    {'code': 'th', 'title': '🇹🇭 TH'},
    {'code': 'vi', 'title': '🇻🇳 VI'},
    {'code': 'zh', 'title': '🇨🇳 ZH'},
]

# Максимальное количество кнопок, которое поддерживает Messenger
MESSENGER_QUICK_REPLIES_LIMIT = 13