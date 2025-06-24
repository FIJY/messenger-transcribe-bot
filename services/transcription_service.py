# services/transcription_service.py
import openai
import os
import logging
# ===> НОВЫЙ ИМПОРТ <===
from config.transcrib_suggestion_config import SUPPORTED_LANGUAGES_MAP

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

            if result['success']:
                # Успешная транскрипция с первого раза
                text = result.get('text', '').strip()
                if text:
                    detected_lang = result.get('detected_language')
                    self.logger.info(f"Транскрипция успешна. Язык: {detected_lang}")
                    return text, detected_lang

            # Если первая попытка не дала результата, пробуем еще раз в режиме автоопределения.
            self.logger.warning("Первая попытка не дала результата или текст пустой, пробуем в режиме автоопределения.")
            fallback_result = self._transcribe_sync(audio_file_path, None)

            if fallback_result['success']:
                fallback_text = fallback_result.get('text', '').strip()
                if fallback_text:
                    detected_lang = fallback_result.get('detected_language')
                    return fallback_text, detected_lang

            # Если обе попытки не удались
            error_obj = fallback_result.get('error', result.get('error', Exception('Unknown transcription error')))
            raise error_obj

        except Exception as e:
            self.logger.error(f"Критическая ошибка в transcribe_with_fallback: {e}", exc_info=True)
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

                detected_language_name = response.language.lower()
                transcribed_text = response.text.strip() if response.text else ''

                # ===> ГЛАВНОЕ ИСПРАВЛЕНИЕ: НОРМАЛИЗАЦИЯ ЛЮБОГО ЯЗЫКА <===
                # Преобразуем "russian" -> "ru", "english" -> "en" и т.д.
                # Если название не найдено, оставляем как есть (на случай новых языков от OpenAI)
                final_lang_code = SUPPORTED_LANGUAGES_MAP.get(detected_language_name, detected_language_name)

                self.logger.info(f"OpenAI определил язык: {detected_language_name} (нормализован в {final_lang_code}).")

                return {
                    'success': True,
                    'text': transcribed_text,
                    'detected_language': final_lang_code
                }
        except Exception as e:
            self.logger.error(f"Ошибка транскрипции в _transcribe_sync: {e}", exc_info=True)
            return {'success': False, 'text': '', 'error': e}