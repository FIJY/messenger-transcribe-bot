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

    def detect_language(self, audio_file_path: str) -> tuple[str, str]:
        """
        Определяет язык аудиофайла, не выполняя полной транскрипции.
        Возвращает кортеж (код_языка, полное_имя_языка).
        """
        try:
            self.logger.info(f"Запускаем определение языка для файла: {audio_file_path}")
            # Мы делаем короткую транскрипцию, чтобы просто получить язык
            result = self._transcribe_sync(audio_file_path, language_hint=None, task='transcribe')

            if result['success']:
                code = result.get('detected_language_code', 'unknown')
                name = result.get('detected_language_name', 'unknown')
                return code, name

            raise result.get('error', Exception('Unknown language detection error'))

        except Exception as e:
            self.logger.error(f"Критическая ошибка в detect_language: {e}", exc_info=True)
            return 'unknown', 'unknown'

    def _transcribe_sync(self, audio_path: str, language_hint: str = None, task: str = 'transcribe') -> dict:
        """
        Синхронно транскрибирует аудиофайл.
        task='transcribe' для получения текста, task='detect' только для языка.
        """
        try:
            with open(audio_path, "rb") as audio_file:
                prompt_text = None
                if language_hint == 'km':
                    prompt_text = "សួស្តី, ជំរាបសួរ, អរគុណ, សូម, បាទ, ចាស, ខ្ញុំ"

                # Предохранитель: если language_hint не является двухбуквенным кодом, не используем его
                if language_hint and len(language_hint) != 2:
                    self.logger.warning(
                        f"Получен некорректный language_hint: '{language_hint}'. Выполняем в режиме автоопределения.")
                    language_hint = None

                response = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language_hint,
                    prompt=prompt_text,
                    response_format="verbose_json",
                    # timestamp_granularities=["word"] # Можно включить для получения временных меток слов
                )

                detected_language_name = response.language.lower()
                transcribed_text = response.text.strip() if response.text else ''

                # Предохранитель: Проверяем, вернул ли Whisper корректное имя языка
                if len(detected_language_name) > 15 or ' ' in detected_language_name:
                    logger.warning(
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