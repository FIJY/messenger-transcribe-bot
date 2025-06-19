# services/transcription_service.py - ПОЛНАЯ ИСПРАВЛЕННАЯ ВЕРСИЯ
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

            # Первая попытка с указанным языком (если он есть)
            result = self._transcribe_sync(audio_file_path, language)
            text = result.get('text', '').strip()

            if result['success'] and text:
                # Если первая попытка успешна, возвращаем результат
                detected_lang = result.get('detected_language', language or 'unknown')
                self.logger.info(f"Транскрибация успешна с первой попытки. Язык: {detected_lang}")
                return text, detected_lang

            # Если первая попытка не удалась (например, был указан неверный язык),
            # пробуем еще раз в режиме автоопределения.
            self.logger.warning("Первая попытка не дала результата, пробуем в режиме автоопределения.")
            fallback_result = self._transcribe_sync(audio_file_path, None)
            fallback_text = fallback_result.get('text', '').strip()

            if fallback_result['success'] and fallback_text:
                detected_lang = fallback_result.get('detected_language', 'unknown')
                self.logger.info(f"Транскрибация успешна со второй попытки (fallback). Язык: {detected_lang}")
                return fallback_text, detected_lang
            else:
                error_msg = fallback_result.get('error', result.get('error', 'Unknown error'))
                return f"Ошибка транскрипции: {error_msg}", 'unknown'

        except Exception as e:
            self.logger.error(f"Критическая ошибка в transcribe_with_fallback: {e}", exc_info=True)
            return f"Ошибка транскрипции: {str(e)}", 'unknown'

    def _transcribe_sync(self, audio_path: str, language_hint: str = None) -> dict:
        """Синхронная версия транскрибации с подсказками (prompt)."""
        try:
            with open(audio_path, "rb") as audio_file:

                # 🔧 НОВОЕ: Добавляем подсказку (prompt) для кхмерского языка
                # Это значительно повышает шанс получения текста в кхмерском алфавите.
                prompt_text = None
                if language_hint == 'km':
                    prompt_text = "សួស្តី, ជំរាបសួរ, អរគុណ, សូម, បាទ, ចាស, ខ្ញុំ"
                    self.logger.info(f"Используем prompt для кхмерского языка: {prompt_text}")

                response = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language_hint if language_hint else None,
                    prompt=prompt_text,  # <--- ПЕРЕДАЕМ ПОДСКАЗКУ
                    response_format="verbose_json"  # Получаем больше данных, включая язык
                )

                detected_language = response.language
                transcribed_text = response.text.strip() if response.text else ''

                self.logger.info(f"OpenAI определил язык: {detected_language}. Текст: {transcribed_text[:100]}...")

                return {
                    'success': True,
                    'text': transcribed_text,
                    'detected_language': detected_language
                }

        except Exception as e:
            self.logger.error(f"Ошибка транскрибации в _transcribe_sync: {e}")
            return {'success': False, 'text': '', 'error': str(e)}