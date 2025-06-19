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

            # Проверим что клиент работает
            # models = self.client.models.list()
            # self.logger.info("OpenAI подключение проверено")

        except Exception as e:
            self.logger.error(f"Ошибка инициализации OpenAI: {e}")
            raise

    def transcribe_audio(self, audio_file_path, language=None):
        """Транскрипция аудио файла через OpenAI Whisper API"""
        try:
            self.logger.info("Starting OpenAI transcription")

            # Проверяем существование файла
            if not os.path.exists(audio_file_path):
                raise FileNotFoundError(f"Аудио файл не найден: {audio_file_path}")

            # Открываем файл и отправляем на транскрипцию
            with open(audio_file_path, 'rb') as audio_file:
                transcript_params = {
                    'file': audio_file,
                    'model': 'whisper-1',
                    'response_format': 'text'
                }

                # Добавляем язык если указан
                if language and language != 'auto':
                    transcript_params['language'] = language

                # Выполняем транскрипцию
                transcript = self.client.audio.transcriptions.create(**transcript_params)

                # OpenAI возвращает строку при response_format='text'
                transcript_text = transcript if isinstance(transcript, str) else transcript.text

                self.logger.info(f"Transcription completed. Text length: {len(transcript_text)}")

                return {
                    'success': True,
                    'text': transcript_text.strip(),
                    'detected_language': language or 'auto'
                }

        except Exception as e:
            self.logger.error(f"Ошибка транскрипции: {e}")
            return {
                'success': False,
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