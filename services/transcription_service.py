# services/transcription_service.py
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
        try:
            self.logger.info(f"Запускаем транскрибацию для языка: {language or 'auto'}")
            result = self._transcribe_sync(audio_file_path, language)
            text = result.get('text', '').strip()

            if result['success'] and text:
                detected_lang = result.get('detected_language', language or 'unknown')
                return text, detected_lang

            self.logger.warning("Первая попытка не дала результата, пробуем в режиме автоопределения.")
            fallback_result = self._transcribe_sync(audio_file_path, None)
            fallback_text = fallback_result.get('text', '').strip()

            if fallback_result['success'] and fallback_text:
                detected_lang = fallback_result.get('detected_language', 'unknown')
                return fallback_text, detected_lang
            else:
                # ===> ИЗМЕНЕНИЕ ЗДЕСЬ <===
                # Пробрасываем ошибку, чтобы ее можно было поймать выше
                raise fallback_result.get('error', result.get('error', Exception('Unknown transcription error')))

        except Exception as e:
            self.logger.error(f"Критическая ошибка в transcribe_with_fallback: {e}", exc_info=True)
            # Возвращаем ошибку в понятном виде
            return f"Ошибка транскрипции: {str(e)}", 'unknown'

    def _transcribe_sync(self, audio_path: str, language_hint: str = None) -> dict:
        try:
            with open(audio_path, "rb") as audio_file:
                prompt_text = None
                if language_hint == 'km':
                    prompt_text = "សួស្តី, ជំរាបសួរ, អរគុណ, សូម, បាទ, ចាស, ខ្ញុំ"
                    self.logger.info(f"Используем prompt для кхмерского языка.")

                response = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language_hint,
                    prompt=prompt_text,
                    response_format="verbose_json"
                )

                detected_language_raw = response.language
                transcribed_text = response.text.strip() if response.text else ''
                detected_language = detected_language_raw.lower()
                if detected_language == 'khmer':
                    detected_language = 'km'

                self.logger.info(f"OpenAI определил язык: {detected_language_raw} (нормализован в {detected_language}).")
                return {
                    'success': True,
                    'text': transcribed_text,
                    'detected_language': detected_language
                }
        # ===> ИЗМЕНЕНИЕ ЗДЕСЬ <===
        except Exception as e:
            self.logger.error(f"Ошибка транскрипции в _transcribe_sync: {e}", exc_info=True)
            # Возвращаем саму ошибку, а не ее текст
            return {'success': False, 'text': '', 'error': e}