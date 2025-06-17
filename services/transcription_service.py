import os
import logging
import openai
from .audio_processor import AudioProcessor
from .language_detector import LanguageDetector

logger = logging.getLogger(__name__)


class TranscriptionService:
    """Сервис для транскрипции аудио/видео"""

    def __init__(self):
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        self.audio_processor = AudioProcessor()
        self.language_detector = LanguageDetector()

        if not self.openai_api_key:
            logger.warning("OPENAI_API_KEY not found")
            self.client_ready = False
        else:
            try:
                openai.api_key = self.openai_api_key
                self.client_ready = True
                logger.info("OpenAI Transcription API initialized")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI: {e}")
                self.client_ready = False

    def transcribe_from_url(self, media_url, media_type='audio', user_subscription='free'):
        """Транскрипция медиа по URL"""
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

            # 4. Транскрибируем
            result = self._transcribe_file(temp_file_path)

            # 5. Обрабатываем результат
            if result['success']:
                # Улучшаем определение языка
                language_analysis = self.language_detector.analyze_text_language(
                    result['text'], result.get('language_code')
                )

                result.update({
                    'language': self.language_detector.get_language_name(language_analysis['final_language']),
                    'language_code': language_analysis['final_language'],
                    'language_confidence': language_analysis['confidence'],
                    'duration': estimated_duration,
                    'media_type': media_type
                })

            return result

        except ValueError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return {'success': False, 'error': 'Ошибка транскрипции. Попробуйте позже.'}
        finally:
            if temp_file_path:
                self.audio_processor.cleanup_temp_file(temp_file_path)

    def transcribe_from_data(self, media_data, media_type='audio', user_subscription='free'):
        """Транскрипция медиа из данных в памяти"""
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

            # 3. Транскрибируем
            result = self._transcribe_file(temp_file_path)

            # 4. Обрабатываем результат
            if result['success']:
                language_analysis = self.language_detector.analyze_text_language(
                    result['text'], result.get('language_code')
                )

                result.update({
                    'language': self.language_detector.get_language_name(language_analysis['final_language']),
                    'language_code': language_analysis['final_language'],
                    'language_confidence': language_analysis['confidence'],
                    'duration': estimated_duration,
                    'media_type': media_type
                })

            return result

        except ValueError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return {'success': False, 'error': 'Ошибка транскрипции. Попробуйте позже.'}
        finally:
            if temp_file_path:
                self.audio_processor.cleanup_temp_file(temp_file_path)

    def _transcribe_file(self, file_path):
        """Внутренний метод транскрипции файла"""
        try:
            logger.info("Starting OpenAI transcription")

            with open(file_path, 'rb') as audio_file:
                transcript = openai.Audio.transcribe(
                    model="whisper-1",
                    file=audio_file,
                    response_format="json"
                )

            text = transcript['text'].strip()
            language_code = transcript.get('language', 'unknown')

            logger.info(f"Transcription completed. Detected language: {language_code}")

            return {
                'success': True,
                'text': text,
                'language_code': language_code,
                'raw_response': transcript
            }

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
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
                'error': 'Неподдерживаемый формат файла.'
            }
        elif "rate_limit" in error_message:
            return {
                'success': False,
                'error': 'Превышен лимит запросов. Попробуйте через минуту.'
            }
        else:
            return {
                'success': False,
                'error': 'Ошибка транскрипции. Попробуйте позже.'
            }

    def _mock_result(self):
        """Заглушка когда API недоступен"""
        return {
            'success': True,
            'text': '🔧 Настройте OPENAI_API_KEY для включения транскрипции.',
            'language': 'System Message',
            'language_code': 'sys',
            'duration': 0,
            'media_type': 'audio'
        }

    def get_api_status(self):
        """Статус API"""
        return {
            'transcription_available': self.client_ready,
            'supported_formats': self.audio_processor.supported_formats
        }