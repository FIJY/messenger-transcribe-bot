import os
import logging
import openai
from .audio_processor import AudioProcessor
from .language_detector import LanguageDetector

logger = logging.getLogger(__name__)


class TranscriptionService:
    """Сервис для транскрипции аудио/видео"""

    def __init__(self):
        self.api_key = os.getenv('OPENAI_API_KEY')
        self.audio_processor = AudioProcessor()
        self.language_detector = LanguageDetector()

        if self.api_key:
            openai.api_key = self.api_key
            logger.info("OpenAI Whisper API initialized successfully")
        else:
            logger.warning("OPENAI_API_KEY not found, transcription will not work")

    def transcribe_from_url(self, media_url, media_type='audio', user_subscription='free'):
        """
        Транскрипция медиа файла по URL

        Args:
            media_url: URL медиа файла
            media_type: Тип медиа ('audio' или 'video')
            user_subscription: Тип подписки пользователя

        Returns:
            dict: Результат транскрипции
        """
        try:
            # 1. Скачиваем файл
            media_data = self.audio_processor.download_media(media_url)
            if not media_data:
                return {
                    'success': False,
                    'error': 'Failed to download media file'
                }

            # 2. Валидируем файл
            validation = self.audio_processor.validate_media(
                media_data, media_type, user_subscription
            )

            if not validation['is_valid']:
                return {
                    'success': False,
                    'error': validation['error']
                }

            # 3. Транскрибируем
            return self.transcribe_from_data(media_data, media_type, user_subscription)

        except Exception as e:
            logger.error(f"Transcription error: {str(e)}")
            return {
                'success': False,
                'error': f"Transcription failed: {str(e)}"
            }

    def transcribe_from_data(self, media_data, media_type='audio', user_subscription='free'):
        """
        Транскрипция из данных файла

        Args:
            media_data: Байты медиа файла
            media_type: Тип медиа
            user_subscription: Тип подписки

        Returns:
            dict: Результат транскрипции
        """
        if not self.api_key:
            return {
                'success': False,
                'error': 'Настройте OPENAI_API_KEY для включения транскрипции.',
                'text': 'Настройте OPENAI_API_KEY для включения транскрипции.',
                'language_info': {
                    'api_detected': 'unknown',
                    'final_language': 'unknown',
                    'display_name': 'System Message'
                }
            }

        temp_file_path = None

        try:
            # 1. Создаем временный файл (используем save_temp_file вместо create_temp_file)
            extension = 'mp4' if media_type == 'video' else 'mp3'
            temp_file_path = self.audio_processor.save_temp_file(media_data, extension)

            if not temp_file_path:
                return {
                    'success': False,
                    'error': 'Failed to create temporary file'
                }

            # 2. Транскрибируем через OpenAI
            logger.info(f"Starting OpenAI transcription")

            with open(temp_file_path, 'rb') as audio_file:
                response = openai.Audio.transcribe(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json"
                )

            # 3. Анализируем язык
            detected_language = response.get('language', 'unknown')
            logger.info(f"Transcription completed. Detected language: {detected_language}")

            language_info = self.language_detector.analyze_language(
                response['text'],
                detected_language
            )

            return {
                'success': True,
                'text': response['text'],
                'language_info': language_info,
                'duration': response.get('duration'),
                'segments': response.get('segments', [])
            }

        except Exception as e:
            logger.error(f"Transcription error: {str(e)}")
            return {
                'success': False,
                'error': f"OpenAI API error: {str(e)}"
            }

        finally:
            # Очищаем временный файл
            if temp_file_path:
                self.audio_processor.cleanup_temp_file(temp_file_path)

    def get_supported_languages(self):
        """Получить список поддерживаемых языков"""
        return self.language_detector.supported_languages