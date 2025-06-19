# services/transcription_service.py - ФИНАЛЬНАЯ И ЕДИНСТВЕННО ПРАВИЛЬНАЯ ВЕРСИЯ
import openai
import os
import logging

logger = logging.getLogger(__name__)

class TranscriptionService:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY не найден в переменных окружения")
        try:
            self.client = openai.OpenAI(api_key=api_key)
            self.logger.info("OpenAI клиент успешно инициализирован")
        except Exception as e:
            self.logger.error(f"Ошибка инициализации OpenAI: {e}")
            raise

    def transcribe_with_fallback(self, audio_file_path, language=None):
        """
        Транскрипция с дополнительными попытками и подсказками для сложных языков.
        Returns: tuple: (transcription_text, detected_language)
        """
        try:
            self.logger.info(f"Запускаем транскрибацию для языка: {language or 'auto'}")

            # Первая попытка
            result = self._transcribe_sync(audio_file_path, language)
            text = result.get('text', '').strip()

            if result['success'] and text:
                detected_lang = result.get('detected_language', language or 'unknown')
                self.logger.info(f"Транскрибация успешна. Язык: {detected_lang}")
                return text, detected_lang

            # Если первая попытка не дала результата, пробуем еще раз в режиме автоопределения.
            self.logger.warning("Первая попытка не дала результата, пробуем в режиме автоопределения.")
            fallback_result = self._transcribe_sync(audio_file_path, None)
            fallback_text = fallback_result.get('text', '').strip()

            if fallback_result['success'] and fallback_text:
                detected_lang = fallback_result.get('detected_language', 'unknown')
                return fallback_text, detected_lang
            else:
                error_msg = fallback_result.get('error', result.get('error', 'Unknown error'))
                return f"Ошибка транскрипции: {error_msg}", 'unknown'

        except Exception as e:
            self.logger.error(f"Критическая ошибка в transcribe_with_fallback: {e}", exc_info=True)
            return f"Ошибка транскрипции: {str(e)}", 'unknown'

    def _transcribe_sync(self, audio_path: str, language_hint: str = None) -> dict:
        """Синхронная версия транскрипции с подсказками (prompt) и нормализацией."""
        try:
            with open(audio_path, "rb") as audio_file:
                prompt_text = None
                # Применяем подсказку, только если язык был выбран принудительно (например, при ретрае)
                if language_hint == 'km':
                    prompt_text = "សួស្តី, ជំរាបសួរ, អរគុណ, សូម, បាទ, ចាស, ខ្ញុំ"
                    self.logger.info(f"Используем prompt для кхмерского языка: {prompt_text}")

                response = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language_hint if language_hint else None,
                    prompt=prompt_text,
                    response_format="verbose_json"
                )

                detected_language_raw = response.language
                transcribed_text = response.text.strip() if response.text else ''

                # НОРМАЛИЗАЦИЯ ЯЗЫКА: Приводим 'khmer' к стандартному коду 'km'
                detected_language = detected_language_raw.lower()
                if detected_language == 'khmer':
                    detected_language = 'km'
                    logger.info("Нормализовали язык: 'khmer' -> 'km'")

                self.logger.info(f"OpenAI определил язык: {detected_language_raw} (нормализован в {detected_language}).")

                return {
                    'success': True,
                    'text': transcribed_text,
                    'detected_language': detected_language
                }

        except Exception as e:
            self.logger.error(f"Ошибка транскрипции в _transcribe_sync: {e}", exc_info=True)
            return {'success': False, 'text': '', 'error': str(e)}git add services/transcription_service.py