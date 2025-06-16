# Лимиты для бесплатных пользователей
FREE_DAILY_LIMIT = 10
MAX_AUDIO_DURATION_FREE = 300  # 5 минут в секундах для бесплатных
MAX_AUDIO_DURATION_PREMIUM = 3600  # 60 минут в секундах для премиум

# Типы подписок
SUBSCRIPTION_TYPES = {
    'free': {
        'name': 'Free',
        'daily_limit': FREE_DAILY_LIMIT,
        'max_duration': MAX_AUDIO_DURATION_FREE,
        'price': 0
    },
    'premium': {
        'name': 'Premium',
        'daily_limit': None,  # Безлимитно
        'max_duration': MAX_AUDIO_DURATION_PREMIUM,
        'price': 4.99
    }
}

# Поддерживаемые форматы медиа
SUPPORTED_MEDIA_FORMATS = [
    'audio/mpeg',
    'audio/mp3',
    'audio/wav',
    'audio/ogg',
    'audio/m4a',
    'audio/aac',
    'video/mp4',
    'video/mpeg',
    'video/quicktime',
    'video/x-msvideo'  # .avi
]

# Сообщения для разных языков
MESSAGES = {
    'welcome': {
        'en': "👋 Welcome to Audio Transcribe Bot!\n\n🎤 I can convert your voice messages and videos to text in any language.\n\n📝 Just send me an audio or video message!",
        'ru': "👋 Добро пожаловать в Audio Transcribe Bot!\n\n🎤 Я могу превратить ваши голосовые сообщения и видео в текст на любом языке.\n\n📝 Просто отправьте мне аудио или видео!",
        'km': "👋 ស្វាគមន៍មកកាន់ Audio Transcribe Bot!\n\n🎤 ខ្ញុំអាចបំលែងសារជាសំឡេងនិងវីដេអូរបស់អ្នកទៅជាអត្ថបទ។\n\n📝 គ្រាន់តែផ្ញើសារជាសំឡេងឬវីដេអូមកខ្ញុំ!"
    },
    'processing': {
        'en': "🎧 Processing your media... Please wait.",
        'ru': "🎧 Обрабатываю ваш файл... Пожалуйста, подождите.",
        'km': "🎧 កំពុងដំណើរការឯកសាររបស់អ្នក... សូមរង់ចាំ។"
    },
    'error': {
        'en': "❌ Error processing media. Please try again.",
        'ru': "❌ Ошибка при обработке файла. Попробуйте еще раз.",
        'km': "❌ មានបញ្ហាក្នុងការដំណើរការ។ សូមព្យាយាមម្តងទៀត។"
    }
}

# API версии и endpoints
API_VERSION = "v1.0.0"
FACEBOOK_GRAPH_API_VERSION = "v18.0"

# Размеры файлов
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB для OpenAI API
MAX_FREE_FILE_SIZE = 25 * 1024 * 1024  # 25 MB одинаково для всех