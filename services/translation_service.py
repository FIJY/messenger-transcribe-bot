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

        if not self.openai_api_key:
            logger.warning("OPENAI_API_KEY not found")
            self.client_ready = False
        else:
            try:
                openai.api_key = self.openai_api_key
                self.client_ready = True
                logger.info("OpenAI Translation API initialized")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI: {e}")
                self.client_ready = False

    def translate_from_url(self, media_url, media_type='audio', user_subscription='free'):
        """Перевод медиа по URL"""
        if not self.client_ready:
            return self._mock_result()

        temp_file_path = None
        try:
            # 1. Скачиваем файл
            media_data = self.audio_processor.download_media(media_url)

            # 2. Валидируем файл
            estimated_duration = self.audio_processor.validate_media_file(
                media_data, media_type, user_subscription
            )

            # 3. Создаем временный файл
            temp_file_path = self.audio_processor.create_temp_file(media_data, media_type)

            # 4. Переводим
            result = self._translate_file(temp_file_path)

            # 5. Обрабатываем результат
            if result['success']:
                result.update({
                    'duration': estimated_duration,
                    'media_type': media_type
                })

            return result

        except ValueError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return {'success': False, 'error': 'Ошибка перевода. Попробуйте позже.'}
        finally:
            if temp_file_path:
                self.audio_processor.cleanup_temp_file(temp_file_path)

    def translate_from_data(self, media_data, media_type='audio', user_subscription='free'):
        """Перевод медиа из данных в памяти"""
        if not self.client_ready:
            return self._mock_result()

        temp_file_path = None
        try:
            # 1. Валидируем файл
            estimated_duration = self.audio_processor.validate_media_file(
                media_data, media_type, user_subscription
            )

            # 2. Создаем временный файл
            temp_file_path = self.audio_processor.create_temp_file(media_data, media_type)

            # 3. Переводим
            result = self._translate_file(temp_file_path)

            # 4. Обрабатываем результат
            if result['success']:
                result.update({
                    'duration': estimated_duration,
                    'media_type': media_type
                })

            return result

        except ValueError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return {'success': False, 'error': 'Ошибка перевода. Попробуйте позже.'}
        finally:
            if temp_file_path:
                self.audio_processor.cleanup_temp_file(temp_file_path)

    def _translate_file(self, file_path):
        """Внутренний метод перевода файла"""
        try:
            logger.info("Starting OpenAI translation")

            with open(file_path, 'rb') as audio_file:
                translation = openai.Audio.translate(
                    model="whisper-1",
                    file=audio_file,
                    response_format="json"
                )

            translated_text = translation['text'].strip()
            original_language = translation.get('language', 'unknown')

            logger.info(f"Translation completed. Original language: {original_language}")

            return {
                'success': True,
                'translated_text': translated_text,
                'original_language': original_language,
                'target_language': 'en',
                'raw_response': translation
            }

        except Exception as e:
            logger.error(f"OpenAI translation API error: {e}")
            return self._handle_api_error(e)

    def _handle_api_error(self, error):
        """Обработка ошибок OpenAI API"""
        error_message = str(error)

        if "insufficient_quota" in error_message:
            return {
                'success': False,
                'error': 'Превышена квота OpenAI API. Попробуйте позже.'
            }
        elif "invalid_request_error" in error_message:
            return {
                'success': False,
                'error': 'Неподдерживаемый формат файла для перевода.'
            }
        elif "rate_limit" in error_message:
            return {
                'success': False,
                'error': 'Превышен лимит запросов. Попробуйте через минуту.'
            }
        else:
            return {
                'success': False,
                'error': 'Ошибка перевода. Попробуйте позже.'
            }

    def _mock_result(self):
        """Заглушка когда API недоступен"""
        return {
            'success': True,
            'translated_text': '🔧 Настройте OPENAI_API_KEY для включения перевода.',
            'original_language': 'unknown',
            'target_language': 'en'
        }

    def get_api_status(self):
        """Статус API"""
        return {
            'translation_available': self.client_ready,
            'target_languages': ['en'],  # OpenAI Whisper переводит только на английский
            'supported_formats': self.audio_processor.supported_formats
        }