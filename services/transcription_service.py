# services/transcription_service.py
import openai
import os
import logging
import tempfile
from config.transcrib_suggestion_config import SUPPORTED_LANGUAGES_MAP
from .s3_service import S3Service

logger = logging.getLogger(__name__)


class TranscriptionService:
    def __init__(self, s3_service: S3Service):
        self.logger = logging.getLogger(__name__)
        self.s3_service = s3_service
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY не найден в переменных окружения")
        try:
            self.client = openai.OpenAI(api_key=api_key)
            self.logger.info("OpenAI клиент успешно инициализирован")
        except Exception as e:
            self.logger.error(f"Ошибка инициализации OpenAI: {e}")
            raise

    def transcribe_audio_from_s3(self, s3_key: str, language_hint: str = None) -> str:
        self.logger.info(f"Начинаем транскрибацию из S3 для ключа: {s3_key}")
        file_suffix = os.path.splitext(s3_key)[1] or '.tmp'
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_suffix) as temp_audio_file:
            local_path = temp_audio_file.name

        try:
            self.logger.info(f"Скачиваем {s3_key} в {local_path}")
            download_success = self.s3_service.download_file(s3_key, local_path)
            if not download_success:
                raise Exception(f"Не удалось скачать файл из S3: {s3_key}")
            self.logger.info("Скачивание завершено.")

            result = self._transcribe_sync(local_path, language_hint=language_hint)
            if not result['success']:
                raise result.get('error', Exception("Неизвестная ошибка транскрипции"))

            self.logger.info(f"Транскрибация для {s3_key} успешно завершена.")
            return result.get('text', '')

        except Exception as e:
            self.logger.error(f"Произошла ошибка во время транскрипции из S3: {e}", exc_info=True)
            return ""
        finally:
            if os.path.exists(local_path):
                os.remove(local_path)
                self.logger.info(f"Временный файл {local_path} удален.")

    def _transcribe_sync(self, audio_path: str, language_hint: str = None) -> dict:
        try:
            with open(audio_path, "rb") as audio_file:
                prompt_text = None
                if language_hint == 'km':
                    prompt_text = "សួស្តី, ជំរាបសួរ, អរគុណ, សូម, បាទ, ចាស, ខ្ញុំ"

                if language_hint and len(language_hint) != 2:
                    self.logger.warning(
                        f"Получен некорректный language_hint: '{language_hint}'. Выполняем в режиме автоопределения.")
                    language_hint = None

                response = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language_hint,
                    prompt=prompt_text,
                    response_format="verbose_json"
                )

                detected_language_name = response.language.lower()
                transcribed_text = response.text.strip() if response.text else ''

                if len(detected_language_name) > 15 or ' ' in detected_language_name:
                    self.logger.warning(
                        f"Whisper вернул невалидное имя языка: '{detected_language_name}'. Считаем язык неопределенным.")
                    final_lang_code = 'unknown'
                else:
                    final_lang_code = SUPPORTED_LANGUAGES_MAP.get(detected_language_name, detected_language_name)

                self.logger.info(f"OpenAI определил язык: {detected_language_name} (нормализован в {final_lang_code}).")

                return {
                    'success': True,
                    'text': transcribed_text,
                    'detected_language_code': final_lang_code,
                    'detected_language_name': detected_language_name
                }
        except Exception as e:
            self.logger.error(f"Ошибка транскрипции в _transcribe_sync: {e}", exc_info=True)
            return {'success': False, 'text': '', 'error': e}
