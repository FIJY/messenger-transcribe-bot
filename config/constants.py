# Лимиты для бесплатных пользователей
FREE_DAILY_LIMIT = 3
MAX_AUDIO_DURATION = 300  # 5 минут в секундах
MAX_PREMIUM_AUDIO_DURATION = 600  # 10 минут для премиум

# Типы подписок
SUBSCRIPTION_TYPES = {
    'free': {
        'name': 'Free',
        'daily_limit': FREE_DAILY_LIMIT,
        'max_duration': MAX_AUDIO_DURATION,
        'price': 0
    },
    'premium': {
        'name': 'Premium',
        'daily_limit': None,  # Безлимитно
        'max_duration': MAX_PREMIUM_AUDIO_DURATION,
        'price': 4.99
    }
}

# Поддерживаемые форматы аудио
SUPPORTED_AUDIO_FORMATS = [
    'audio/mpeg',
    'audio/mp3',
    'audio/wav',
    'audio/ogg',
    'audio/m4a',
    'audio/aac'
]

# Сообщения для разных языков
MESSAGES = {
    'welcome': {
        'en': "👋 Welcome to Audio Transcribe Bot!\n\n🎤 I can convert your voice messages to text in any language.\n\n📝 Just send me an audio message!",
        'ru': "👋 Добро пожаловать в Audio Transcribe Bot!\n\n🎤 Я могу превратить ваши голосовые сообщения в текст на любом языке.\n\n📝 Просто отправьте мне аудио сообщение!",
        'km': "👋 ស្វាគមន៍មកកាន់ Audio Transcribe Bot!\n\n🎤 ខ្ញុំអាចបំលែងសារជាសំឡេងរបស់អ្នកទៅជាអត្ថបទ។\n\n📝 គ្រាន់តែផ្ញើសារជាសំឡេងមកខ្ញុំ!"
    },
    'processing': {
        'en': "🎧 Processing your audio... Please wait.",
        'ru': "🎧 Обрабатываю ваше аудио... Пожалуйста, подождите.",
        'km': "🎧 កំពុងដំណើរការសំឡេងរបស់អ្នក... សូមរង់ចាំ។"
    },
    'error': {
        'en': "❌ Error processing audio. Please try again.",
        'ru': "❌ Ошибка при обработке аудио. Попробуйте еще раз.",
        'km': "❌ មានបញ្ហាក្នុងការដំណើរការ។ សូមព្យាយាមម្តងទៀត។"
    }
}

# API версии и endpoints
API_VERSION = "v1.0.0"
FACEBOOK_GRAPH_API_VERSION = "v18.0"

# Размеры файлов
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
MAX_FREE_FILE_SIZE = 10 * 1024 * 1024  # 10 MB для бесплатных пользователей