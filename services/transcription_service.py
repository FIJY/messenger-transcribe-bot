# services/transcription_service.py
import openai
import os
import logging
import tempfile


class TranscriptionService:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        api_key = os.getenv('OPENAI_API_KEY')

        if not api_key:
            raise ValueError("OPENAI_API_KEY не найден в переменных окружения")

        try:
            # Упрощенная инициализация без проблемных параметров
            self.client = openai.OpenAI(api_key=api_key)
            self.logger.info("OpenAI клиент успешно инициализирован")

        except Exception as e:
            self.logger.error(f"Ошибка инициализации OpenAI: {e}")
            raise

    async def transcribe_audio(self, audio_path: str, language_hint: str = None) -> dict:
        """Транскрибирует аудио файл"""
        try:
            with open(audio_path, "rb") as audio_file:
                # Для кхмерского языка принудительно устанавливаем язык
                if language_hint == 'km':
                    self.logger.info("Транскрибация с принудительным кхмерским языком")
                    response = self.client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language="km",  # Принудительно кхмерский
                        response_format="text"
                    )
                else:
                    self.logger.info(f"Транскрибация с языком: {language_hint or 'auto'}")
                    response = self.client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language=language_hint if language_hint else None,
                        response_format="text"
                    )

                # ✅ ИСПРАВЛЕНИЕ: Возвращаем результат!
                return {
                    'success': True,
                    'text': response.strip() if response else '',
                    'detected_language': language_hint if language_hint else 'auto'
                }

        except Exception as e:
            self.logger.error(f"Ошибка транскрибации: {e}")
            return {
                'success': False,
                'text': '',
                'error': str(e)
            }

    def transcribe_with_language_detection(self, audio_file_path):
        """Транскрипция с автоопределением языка"""
        try:
            # Сначала пробуем без указания языка (автоопределение)
            result = self.transcribe_audio(audio_file_path)

            if result['success']:
                # Пытаемся определить язык по тексту
                text = result['text']
                if text:
                    try:
                        from langdetect import detect
                        detected_lang = detect(text)
                        result['detected_language'] = detected_lang
                        self.logger.info(f"Transcription completed. Detected language: {detected_lang}")
                    except:
                        result['detected_language'] = 'unknown'
                        self.logger.info("Transcription completed. Language detection failed")

            return result

        except Exception as e:
            self.logger.error(f"Ошибка транскрипции с определением языка: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def transcribe_with_fallback(self, audio_file_path, language=None):
        """
        Транскрипция с дополнительными попытками для сложных языков
        Специально для кхмерского языка и других азиатских языков

        Returns:
            tuple: (transcription_text, detected_language)
        """
        try:
            self.logger.info(f"Transcribe with fallback for language: {language}")

            # ✅ ИСПРАВЛЕНИЕ: Делаем синхронный вызов
            # Первая попытка с указанным языком
            if language == 'km':
                # Для кхмерского сначала пробуем с принудительным языком
                result = self._transcribe_sync(audio_file_path, 'km')
                if result['success'] and result['text'].strip():
                    text = result['text'].strip()
                    self.logger.info(f"Кхмерская транскрипция успешна: {text[:100]}...")
                    return text, 'km'

                # Если не получилось, пробуем без языка
                self.logger.info("Кхмерская транскрипция не удалась, пробуем автоопределение")
                result = self._transcribe_sync(audio_file_path, None)
            else:
                # Для других языков стандартная логика
                result = self._transcribe_sync(audio_file_path, language)

            if result['success'] and result['text'].strip():
                text = result['text'].strip()
                detected_lang = result.get('detected_language', language or 'unknown')

                # Для кхмерского проверяем качество транскрипции
                if language == 'km' or detected_lang == 'km':
                    # Проверяем есть ли кхмерские символы
                    khmer_chars = sum(1 for char in text if '\u1780' <= char <= '\u17FF')
                    total_chars = len([char for char in text if char.isalpha()])

                    if total_chars > 0:
                        khmer_ratio = khmer_chars / total_chars
                        self.logger.info(f"Khmer characters ratio: {khmer_ratio:.2f}")

                        if khmer_ratio < 0.1:
                            # Мало кхмерских символов, пробуем без указания языка
                            self.logger.info("Low Khmer ratio, trying without language specification")
                            fallback_result = self._transcribe_sync(audio_file_path, None)
                            if fallback_result['success'] and fallback_result['text'].strip():
                                text = fallback_result['text'].strip()
                                # Пытаемся определить язык заново
                                try:
                                    from langdetect import detect
                                    detected_lang = detect(text)
                                except:
                                    detected_lang = 'unknown'

                return text, detected_lang
            else:
                # Если первая попытка не удалась, пробуем без языка
                self.logger.info("First attempt failed, trying without language")
                fallback_result = self._transcribe_sync(audio_file_path, None)
                if fallback_result['success'] and fallback_result['text'].strip():
                    text = fallback_result['text'].strip()
                    detected_lang = fallback_result.get('detected_language', 'unknown')

                    # Пытаемся определить язык
                    try:
                        from langdetect import detect
                        detected_lang = detect(text)
                    except:
                        detected_lang = 'unknown'

                    return text, detected_lang
                else:
                    error_msg = fallback_result.get('error', result.get('error', 'Unknown error'))
                    return f"Ошибка транскрипции: {error_msg}", 'unknown'

        except Exception as e:
            self.logger.error(f"Error in transcribe_with_fallback: {e}")
            return f"Ошибка транскрипции: {str(e)}", 'unknown'

    def _transcribe_sync(self, audio_path: str, language_hint: str = None) -> dict:
        """Синхронная версия транскрибации"""
        try:
            with open(audio_path, "rb") as audio_file:
                if language_hint == 'km':
                    self.logger.info("Транскрибация с принудительным кхмерским языком")
                    response = self.client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language="km",
                        response_format="text"
                    )
                else:
                    self.logger.info(f"Транскрибация с языком: {language_hint or 'auto'}")
                    response = self.client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language=language_hint if language_hint else None,
                        response_format="text"
                    )

                return {
                    'success': True,
                    'text': response.strip() if response else '',
                    'detected_language': language_hint if language_hint else 'auto'
                }

        except Exception as e:
            self.logger.error(f"Ошибка транскрибации: {e}")
            return {
                'success': False,
                'text': '',
                'error': str(e)
            }

    def get_supported_languages(self) -> list:
        """Возвращает список поддерживаемых языков"""
        return [
            'af', 'am', 'ar', 'as', 'az', 'ba', 'be', 'bg', 'bn', 'bo', 'br', 'bs', 'ca',
            'cs', 'cy', 'da', 'de', 'el', 'en', 'es', 'et', 'eu', 'fa', 'fi', 'fo', 'fr',
            'gl', 'gu', 'ha', 'haw', 'he', 'hi', 'hr', 'ht', 'hu', 'hy', 'id', 'is', 'it',
            'ja', 'jw', 'ka', 'kk', 'km', 'kn', 'ko', 'la', 'lb', 'ln', 'lo', 'lt', 'lv',
            'mg', 'mi', 'mk', 'ml', 'mn', 'mr', 'ms', 'mt', 'my', 'ne', 'nl', 'nn', 'no',
            'oc', 'pa', 'pl', 'ps', 'pt', 'ro', 'ru', 'sa', 'sd', 'si', 'sk', 'sl', 'sn',
            'so', 'sq', 'sr', 'su', 'sv', 'sw', 'ta', 'te', 'tg', 'th', 'tk', 'tl', 'tr',
            'tt', 'uk', 'ur', 'uz', 'vi', 'yi', 'yo', 'zh'
        ]