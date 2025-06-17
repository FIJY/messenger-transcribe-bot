import logging
from .transcription_service import TranscriptionService
from .translation_service import TranslationService
from .audio_processor import AudioProcessor

logger = logging.getLogger(__name__)


class MediaHandler:
    """Главный оркестратор для обработки медиа файлов"""

    def __init__(self):
        self.transcription_service = TranscriptionService()
        self.translation_service = TranslationService()
        self.audio_processor = AudioProcessor()

    def process_media_url(self, media_url, media_type='audio',
                          user_subscription='free', include_translation=False):
        """Обработка медиа по URL с опциональным переводом"""
        try:
            if include_translation:
                return self._process_with_translation(
                    media_url, media_type, user_subscription, from_url=True
                )
            else:
                return self.transcription_service.transcribe_from_url(
                    media_url, media_type, user_subscription
                )

        except Exception as e:
            logger.error(f"Media processing error: {e}")
            return {'success': False, 'error': 'Ошибка обработки медиа файла'}

    def process_media_data(self, media_data, media_type='audio',
                           user_subscription='free', include_translation=False):
        """Обработка медиа из данных с опциональным переводом"""
        try:
            if include_translation:
                return self._process_with_translation(
                    media_data, media_type, user_subscription, from_url=False
                )
            else:
                return self.transcription_service.transcribe_from_data(
                    media_data, media_type, user_subscription
                )

        except Exception as e:
            logger.error(f"Media processing error: {e}")
            return {'success': False, 'error': 'Ошибка обработки медиа файла'}

    def _process_with_translation(self, media_input, media_type, user_subscription, from_url=True):
        """Обработка с транскрипцией И переводом"""
        try:
            # Выбираем метод в зависимости от источника
            if from_url:
                transcription_result = self.transcription_service.transcribe_from_url(
                    media_input, media_type, user_subscription
                )
                translation_result = self.translation_service.translate_from_url(
                    media_input, media_type, user_subscription
                )
            else:
                transcription_result = self.transcription_service.transcribe_from_data(
                    media_input, media_type, user_subscription
                )
                translation_result = self.translation_service.translate_from_data(
                    media_input, media_type, user_subscription
                )

            # Объединяем результаты
            if transcription_result['success'] and translation_result['success']:
                return {
                    'success': True,
                    'transcription': {
                        'text': transcription_result['text'],
                        'language': transcription_result['language'],
                        'language_code': transcription_result['language_code'],
                        'confidence': transcription_result.get('language_confidence', 'medium')
                    },
                    'translation': {
                        'text': translation_result['translated_text'],
                        'original_language': translation_result['original_language'],
                        'target_language': 'en'
                    },
                    'duration': transcription_result.get('duration', 0),
                    'media_type': media_type,
                    'has_translation': True
                }
            elif transcription_result['success']:
                # Если транскрипция удалась, а перевод нет
                logger.warning("Translation failed, returning transcription only")
                return {
                    'success': True,
                    'transcription': {
                        'text': transcription_result['text'],
                        'language': transcription_result['language'],
                        'language_code': transcription_result['language_code']
                    },
                    'translation': None,
                    'duration': transcription_result.get('duration', 0),
                    'media_type': media_type,
                    'has_translation': False,
                    'translation_error': translation_result.get('error', 'Translation failed')
                }
            else:
                # Если транскрипция не удалась
                return transcription_result

        except Exception as e:
            logger.error(f"Combined processing error: {e}")
            return {'success': False, 'error': 'Ошибка комбинированной обработки'}

    def transcribe_only(self, media_input, media_type='audio',
                        user_subscription='free', from_url=True):
        """Только транскрипция без перевода"""
        if from_url:
            return self.transcription_service.transcribe_from_url(
                media_input, media_type, user_subscription
            )
        else:
            return self.transcription_service.transcribe_from_data(
                media_input, media_type, user_subscription
            )

    def translate_only(self, media_input, media_type='audio',
                       user_subscription='free', from_url=True):
        """Только перевод без транскрипции"""
        if from_url:
            return self.translation_service.translate_from_url(
                media_input, media_type, user_subscription
            )
        else:
            return self.translation_service.translate_from_data(
                media_input, media_type, user_subscription
            )

    def get_service_status(self):
        """Статус всех сервисов"""
        return {
            'transcription': self.transcription_service.get_api_status(),
            'translation': self.translation_service.get_api_status(),
            'audio_processor': {
                'supported_formats': self.audio_processor.supported_formats
            }
        }

    def validate_media_before_processing(self, media_data, media_type, user_subscription='free'):
        """Предварительная валидация медиа"""
        try:
            duration = self.audio_processor.validate_media_file(
                media_data, media_type, user_subscription
            )
            return {
                'valid': True,
                'estimated_duration': duration,
                'size_mb': len(media_data) / (1024 * 1024)
            }
        except ValueError as e:
            return {
                'valid': False,
                'error': str(e)
            }