import logging
from .transcription_service import TranscriptionService
from .translation_service import TranslationService
from .audio_processor import AudioProcessor

logger = logging.getLogger(__name__)


class MediaHandler:
    """Главный оркестратор для обработки медиа файлов"""

    def __init__(self):
        self.audio_processor = AudioProcessor()
        self.transcription_service = TranscriptionService()
        self.translation_service = TranslationService()

    def process_media_url(self, media_url, media_type='audio', user_subscription='free', include_translation=False):
        """
        Обработка медиа файла по URL

        Args:
            media_url: URL медиа файла
            media_type: Тип медиа ('audio' или 'video')
            user_subscription: Тип подписки пользователя
            include_translation: Включить ли перевод

        Returns:
            dict: Результат обработки
        """
        try:
            # Скачиваем и проверяем файл
            file_data = self.audio_processor.download_media(media_url)
            if not file_data:
                return {
                    'success': False,
                    'error': 'Failed to download media file'
                }

            # Валидация файла
            validation = self.audio_processor.validate_media(
                file_data,
                media_type,
                user_subscription
            )

            if not validation['is_valid']:
                return {
                    'success': False,
                    'error': validation['error']
                }

            # Транскрипция
            transcription_result = self.transcription_service.transcribe_from_data(
                file_data,
                media_type,
                user_subscription
            )

            if not transcription_result['success']:
                return transcription_result

            # Базовый результат
            result = {
                'success': True,
                'text': transcription_result['text'],
                'language': transcription_result['language_info']['display_name'],
                'language_code': transcription_result['language_info']['final_language'],
                'duration_seconds': validation.get('estimated_duration')
            }

            # Добавляем перевод если нужно
            if include_translation and transcription_result['language_info']['final_language'] != 'en':
                translation_result = self.translation_service.translate_from_data(
                    file_data,
                    media_type,
                    user_subscription
                )

                if translation_result['success']:
                    result['translation'] = translation_result['text']

            return result

        except Exception as e:
            logger.error(f"Error processing media: {str(e)}")
            return {
                'success': False,
                'error': f"Processing error: {str(e)}"
            }

    def transcribe_only(self, media_url, media_type='audio', user_subscription='free'):
        """Только транскрипция без перевода"""
        return self.process_media_url(media_url, media_type, user_subscription, include_translation=False)

    def transcribe_and_translate(self, media_url, media_type='audio', user_subscription='free'):
        """Транскрипция с переводом"""
        return self.process_media_url(media_url, media_type, user_subscription, include_translation=True)