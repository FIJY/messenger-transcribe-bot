import os
import tempfile
import logging
import io
import openai
from config.constants import MAX_AUDIO_DURATION_FREE, MAX_AUDIO_DURATION_PREMIUM, MAX_FILE_SIZE

logger = logging.getLogger(__name__)


class TranscribeService:
    def __init__(self):
        """Инициализация сервиса транскрипции с OpenAI API"""
        self.openai_api_key = os.getenv('OPENAI_API_KEY')

        if not self.openai_api_key:
            logger.warning("OPENAI_API_KEY not found, using mock transcription")
            self.client_ready = False
        else:
            try:
                openai.api_key = self.openai_api_key
                self.client_ready = True
                logger.info("OpenAI Whisper API initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
                self.client_ready = False

        # Поддерживаемые языки
        self.supported_languages = {
            'km': 'ខ្មែរ',
            'en': 'English',
            'ru': 'Русский',
            'zh': '中文',
            'th': 'ไทย',
            'vi': 'Tiếng Việt',
            'fr': 'Français',
            'es': 'Español',
            'ja': '日本語',
            'ko': '한국어',
            'de': 'Deutsch',
            'it': 'Italiano',
            'pt': 'Português',
            'ar': 'العربية',
            'hi': 'हिन्दी',
            'tr': 'Türkçe',
            'pl': 'Polski',
            'nl': 'Nederlands',
            'sv': 'Svenska',
            'da': 'Dansk',
            'no': 'Norsk',
            'fi': 'Suomi'
        }

    def transcribe(self, media_data, user_subscription='free', media_type='audio'):
        """Транскрибировать аудио/видео данные через OpenAI API"""
        if not self.client_ready:
            return self._mock_transcription()

        try:
            # Проверка размера файла
            if len(media_data) > MAX_FILE_SIZE:
                return {
                    'success': False,
                    'error': f'Файл слишком большой. Максимум {MAX_FILE_SIZE // (1024 * 1024)}MB.'
                }

            # Определяем расширение файла в зависимости от типа
            if media_type == 'video':
                file_suffix = '.mp4'
            else:
                file_suffix = '.mp3'

            # Создаем временный файл
            with tempfile.NamedTemporaryFile(suffix=file_suffix, delete=False) as tmp_file:
                tmp_file.write(media_data)
                tmp_file_path = tmp_file.name

            logger.info(f"Starting transcription of {media_type} with OpenAI API")

            # Отправляем на транскрипцию (OpenAI API работает и с видео!)
            with open(tmp_file_path, 'rb') as media_file:
                transcript = openai.Audio.transcribe(
                    model="whisper-1",
                    file=media_file,
                    response_format="json"
                )

            # Удаляем временный файл
            os.unlink(tmp_file_path)

            # Определяем язык
            detected_language = transcript.get('language', 'unknown')
            language_name = self.supported_languages.get(
                detected_language,
                detected_language.upper() if detected_language else 'Auto-detected'
            )

            # Получаем текст
            text = transcript['text'].strip()

            # Примерная проверка длительности по размеру файла
            estimated_duration = self._estimate_duration(len(media_data))
            max_duration = MAX_AUDIO_DURATION_PREMIUM if user_subscription == 'premium' else MAX_AUDIO_DURATION_FREE

            # Проверяем лимиты по времени (примерная оценка)
            if estimated_duration > max_duration:
                duration_minutes = max_duration // 60
                return {
                    'success': False,
                    'error': f'Файл слишком длинный. Максимум {duration_minutes} минут для вашего тарифа.'
                }

            logger.info(f"Transcription completed successfully. Language: {detected_language}")

            return {
                'success': True,
                'text': text,
                'language': language_name,
                'language_code': detected_language,
                'duration': estimated_duration,
                'media_type': media_type
            }

        except Exception as e:
            logger.error(f"OpenAI transcription error: {e}")

            try:
                if 'tmp_file_path' in locals():
                    os.unlink(tmp_file_path)
            except:
                pass

            # Обработка ошибок
            error_message = str(e)
            if "insufficient_quota" in error_message:
                return {
                    'success': False,
                    'error': 'Превышена квота OpenAI API. Попробуйте позже.'
                }
            elif "audio" in error_message.lower() or "video" in error_message.lower():
                return {
                    'success': False,
                    'error': 'Не удалось обработать медиа файл. Проверьте качество записи.'
                }
            else:
                return {
                    'success': False,
                    'error': 'Ошибка транскрипции. Попробуйте позже.'
                }

    def _estimate_duration(self, file_size_bytes):
        """Примерная оценка длительности по размеру файла"""
        # Очень грубая оценка: 1MB ≈ 1 минута для сжатого аудио
        # Для видео коэффициент больше
        estimated_minutes = file_size_bytes / (1024 * 1024)  # MB
        return int(estimated_minutes * 60)  # секунды

    def translate_to_english(self, media_data, media_type='audio'):
        """Транскрибировать и перевести в английский"""
        if not self.client_ready:
            return {
                'success': True,
                'text': '🔧 Translation service will be available after API setup.',
                'original_language': 'unknown'
            }

        try:
            file_suffix = '.mp4' if media_type == 'video' else '.mp3'

            with tempfile.NamedTemporaryFile(suffix=file_suffix, delete=False) as tmp_file:
                tmp_file.write(media_data)
                tmp_file_path = tmp_file.name

            logger.info(f"Starting translation of {media_type} with OpenAI API")

            with open(tmp_file_path, 'rb') as media_file:
                translation = openai.Audio.translate(
                    model="whisper-1",
                    file=media_file,
                    response_format="json"
                )

            os.unlink(tmp_file_path)

            return {
                'success': True,
                'text': translation['text'].strip(),
                'original_language': translation.get('language', 'unknown'),
                'media_type': media_type
            }

        except Exception as e:
            logger.error(f"OpenAI translation error: {e}")
            return self._handle_transcription_error(e)

    def _handle_transcription_error(self, error):
        """Обработка ошибок транскрипции"""
        error_message = str(error)
        if "insufficient_quota" in error_message:
            return {
                'success': False,
                'error': 'Превышена квота OpenAI API. Попробуйте позже.'
            }
        elif "audio" in error_message.lower() or "video" in error_message.lower():
            return {
                'success': False,
                'error': 'Не удалось обработать медиа файл. Проверьте качество записи.'
            }
        else:
            return {
                'success': False,
                'error': 'Ошибка транскрипции. Попробуйте позже.'
            }

    def _mock_transcription(self):
        """Временная заглушка когда API недоступен"""
        return {
            'success': True,
            'text': '🔧 Настройте OPENAI_API_KEY для включения транскрипции.',
            'language': 'System Message',
            'language_code': 'sys',
            'duration': 0,
            'media_type': 'audio'
        }

    def get_supported_languages(self):
        """Получить список поддерживаемых языков"""
        return self.supported_languages

    def is_language_supported(self, language_code):
        """Проверить поддерживается ли язык"""
        return language_code in self.supported_languages