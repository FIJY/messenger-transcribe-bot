# services/transcription_service.py
import openai
import os
import logging
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
                text = result.get('text', '').strip()
                if text:
                    detected_lang = result.get('detected_language')
                    # Возвращаем не только код языка, но и его полное имя для media_handler
                    detected_lang_name = result.get('detected_language_name', detected_lang)
                    self.logger.info(f"Транскрипция успешна. Язык: {detected_lang_name}")
                    return detected_lang, detected_lang_name

            self.logger.warning("Первая попытка не дала результата или текст пустой, пробуем в режиме автоопределения.")
            fallback_result = self._transcribe_sync(audio_file_path, None)

            if fallback_result['success']:
                fallback_text = fallback_result.get('text', '').strip()
                if fallback_text:
                    detected_lang = fallback_result.get('detected_language')
                    detected_lang_name = fallback_result.get('detected_language_name', detected_lang)
                    return detected_lang, detected_lang_name

            error_obj = fallback_result.get('error', result.get('error', Exception('Unknown transcription error')))
            raise error_obj

        except Exception as e:
            self.logger.error(f"Критическая ошибка в transcribe_with_fallback: {e}", exc_info=True)
            return 'unknown', 'unknown'

    def _transcribe_sync(self, audio_path: str, language_hint: str = None) -> dict:
        try:
            with open(audio_path, "rb") as audio_file:
                prompt_text = None
                if language_hint == 'km':
                    prompt_text = "សួស្តី, ជំរាបសួរ, អរគុណ, សូម, បាទ, ចាស, ខ្ញុំ"
                    self.logger.info(f"Используем prompt для кхмерского языка.")

                # ===> ИСПРАВЛЕНИЕ: Добавлен предохранитель <===
                # Если переданный language_hint некорректен (не 2 буквы), не используем его
                if language_hint and len(language_hint) != 2:
                    self.logger.warning(
                        f"Получен некорректный language_hint: '{language_hint}'. Выполняем транскрипцию в режиме автоопределения.")
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

                # ===> ИСПРАВЛЕНИЕ: Проверяем результат определения языка от Whisper <===
                # Если Whisper вернул бессмыслицу вместо языка, используем "неизвестный"
                if len(detected_language_name) > 10 or ' ' in detected_language_name:
                    logger.warning(
                        f"Whisper вернул некорректное имя языка: '{detected_language_name}'. Потребуется повторное определение.")
                    final_lang_code = 'unknown'  # Это поможет инициировать fallback, если нужно
                else:
                    final_lang_code = SUPPORTED_LANGUAGES_MAP.get(detected_language_name, detected_language_name)

                self.logger.info(f"OpenAI определил язык: {detected_language_name} (нормализован в {final_lang_code}).")

                return {
                    'success': True,
                    'text': transcribed_text,
                    'detected_language': final_lang_code,
                    'detected_language_name': detected_language_name
                }
        except Exception as e:
            self.logger.error(f"Ошибка транскрипции в _transcribe_sync: {e}", exc_info=True)
            return {'success': False, 'text': '', 'error': e}