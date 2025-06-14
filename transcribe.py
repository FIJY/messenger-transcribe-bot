import os
import tempfile
import logging
# import whisper  # Временно отключаем
# from pydub import AudioSegment  # Временно отключаем
# from pydub.exceptions import CouldntDecodeError  # Временно отключаем
import io


class TranscribeService:
    def __init__(self):
        # Временно отключаем загрузку модели Whisper
        model_size = os.getenv('WHISPER_MODEL', 'base')
        logging.info(f"TranscribeService initialized (Whisper temporarily disabled for deployment)")
        # self.model = whisper.load_model(model_size)

        # Поддерживаемые языки (можно расширить)
        self.supported_languages = {
            'km': 'ខ្មែរ (Khmer)',
            'en': 'English',
            'ru': 'Русский',
            'zh': '中文',
            'th': 'ไทย',
            'vi': 'Tiếng Việt',
            'fr': 'Français',
            'es': 'Español',
            'ja': '日本語',
            'ko': '한국어'
        }

    def transcribe(self, audio_data):
        """Транскрибировать аудио данные - временная заглушка"""
        logging.info("Transcribe called (returning mock result)")

        # Временная заглушка
        return {
            'success': True,
            'text': '🔧 Сервис транскрипции настраивается. Скоро будет доступен!',
            'language': 'System Message',
            'language_code': 'sys',
            'duration': 0
        }

    def translate_to_english(self, audio_data):
        """Транскрибировать и перевести в английский - временная заглушка"""
        logging.info("Translate called (returning mock result)")

        return {
            'success': True,
            'text': '🔧 Translation service is being set up. Coming soon!',
            'original_language': 'unknown'
        }

    def get_supported_languages(self):
        """Получить список поддерживаемых языков"""
        return self.supported_languages

    def is_language_supported(self, language_code):
        """Проверить поддерживается ли язык"""
        return language_code in self.supported_languages

    # Оставляем остальные методы как заглушки для совместимости
    def _convert_audio(self, input_path):
        """Временная заглушка"""
        return input_path

    def _get_audio_duration(self, audio_path):
        """Временная заглушка"""
        return 0