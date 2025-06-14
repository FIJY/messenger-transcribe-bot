import os
import tempfile
import logging
import io
from openai import OpenAI

logger = logging.getLogger(__name__)


class TranscribeService:
    def __init__(self):
        """Инициализация сервиса транскрипции с OpenAI API"""
        self.openai_api_key = os.getenv('OPENAI_API_KEY')

        if not self.openai_api_key:
            logger.warning("OPENAI_API_KEY not found, using mock transcription")
            self.client = None
        else:
            try:
                self.client = OpenAI(api_key=self.openai_api_key)
                logger.info("OpenAI Whisper API initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
                self.client = None

        # Поддерживаемые языки
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
        """Транскрибировать аудио данные через OpenAI API"""
        if not self.client:
            return self._mock_transcription()

        try:
            # Создаем временный файл
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_file:
                tmp_file.write(audio_data)
                tmp_file_path = tmp_file.name

            logger.info("Starting transcription with OpenAI API")

            # Отправляем на транскрипцию
            with open(tmp_file_path, 'rb') as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="json"
                )

            # Удаляем временный файл
            os.unlink(tmp_file_path)

            # Определяем язык
            detected_language = getattr(transcript, 'language', 'unknown')
            language_name = self.supported_languages.get(
                detected_language,
                f"Detected: {detected_language}"
            )

            logger.info(f"Transcription completed successfully. Language: {detected_language}")

            return {
                'success': True,
                'text': transcript.text.strip(),
                'language': language_name,
                'language_code': detected_language,
                'duration': 0
            }

        except Exception as e:
            logger.error(f"OpenAI transcription error: {e}")

            try:
                if 'tmp_file_path' in locals():
                    os.unlink(tmp_file_path)
            except:
                pass

            return {
                'success': False,
                'error': 'Ошибка транскрипции. Попробуйте позже.'
            }

    def translate_to_english(self, audio_data):
        """Транскрибировать и перевести в английский"""
        if not self.client:
            return {
                'success': True,
                'text': '🔧 Translation service will be available after API setup.',
                'original_language': 'unknown'
            }

        try:
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_file:
                tmp_file.write(audio_data)
                tmp_file_path = tmp_file.name

            logger.info("Starting translation with OpenAI API")

            with open(tmp_file_path, 'rb') as audio_file:
                translation = self.client.audio.translations.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="json"
                )

            os.unlink(tmp_file_path)

            return {
                'success': True,
                'text': translation.text.strip(),
                'original_language': getattr(translation, 'language', 'unknown')
            }

        except Exception as e:
            logger.error(f"OpenAI translation error: {e}")

            try:
                if 'tmp_file_path' in locals():
                    os.unlink(tmp_file_path)
            except:
                pass

            return {
                'success': False,
                'error': 'Ошибка перевода. Попробуйте позже.'
            }

    def _mock_transcription(self):
        """Временная заглушка когда API недоступен"""
        return {
            'success': True,
            'text': '🔧 Настройте OPENAI_API_KEY для включения транскрипции.',
            'language': 'System Message',
            'language_code': 'sys',
            'duration': 0
        }

    def get_supported_languages(self):
        """Получить список поддерживаемых языков"""
        return self.supported_languages

    def is_language_supported(self, language_code):
        """Проверить поддерживается ли язык"""
        return language_code in self.supported_languages