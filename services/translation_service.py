import os
import logging
import openai
from .audio_processor import AudioProcessor

logger = logging.getLogger(__name__)


class TranslationService:
    """Сервис для перевода аудио/видео на английский"""

    def __init__(self):
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        self.audio_processor = AudioProcessor()

        if self.openai_api_key:
            openai.api_key = self.openai_api_key
            logger.info("Translation service initialized with OpenAI API")
        else:
            logger.warning("OPENAI_API_KEY not found, translation will not work")

    def translate_from_url(self, media_url, media_type='audio', user_subscription='free'):
        """
        Перевод медиа файла по URL на английский

        Args:
            media_url: URL медиа файла
            media_type: Тип медиа ('audio' или 'video')
            user_subscription: Тип подписки пользователя

        Returns:
            dict: Результат перевода
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

            # 3. Переводим
            return self.translate_from_data(media_data, media_type, user_subscription)

        except Exception as e:
            logger.error(f"Translation error: {str(e)}")
            return {
                'success': False,
                'error': f"Translation failed: {str(e)}"
            }

    def translate_from_data(self, media_data, media_type='audio', user_subscription='free'):
        """
        Перевод из данных файла

        Args:
            media_data: Байты медиа файла
            media_type: Тип медиа
            user_subscription: Тип подписки

        Returns:
            dict: Результат перевода
        """
        if not self.openai_api_key:
            return {
                'success': False,
                'error': 'Translation service not configured'
            }

        temp_file_path = None

        try:
            # 1. Создаем временный файл
            extension = 'mp4' if media_type == 'video' else 'mp3'
            temp_file_path = self.audio_processor.save_temp_file(media_data, extension)

            if not temp_file_path:
                return {
                    'success': False,
                    'error': 'Failed to create temporary file'
                }

            # 2. Переводим через OpenAI
            logger.info("Starting OpenAI translation")

            with open(temp_file_path, 'rb') as audio_file:
                response = openai.Audio.translate(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json"
                )

            original_language = response.get('language', 'unknown')
            logger.info(f"Translation completed. Original language: {original_language}")

            return {
                'success': True,
                'text': response['text'],
                'original_language': original_language,
                'target_language': 'en',
                'duration': response.get('duration')
            }

        except Exception as e:
            logger.error(f"Translation error: {str(e)}")
            return {
                'success': False,
                'error': f"OpenAI API error: {str(e)}"
            }

        finally:
            # Очищаем временный файл
            if temp_file_path:
                self.audio_processor.cleanup_temp_file(temp_file_path)