import os
import logging
import openai
from typing import Optional, Dict, Any
import tempfile
import requests

logger = logging.getLogger(__name__)


class TranscriptionService:
    def __init__(self):
        """Инициализация сервиса транскрипции"""
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY не установлен в переменных окружения")

        # Убираем параметр proxies, который вызывает ошибку
        self.client = openai.OpenAI(api_key=api_key)
        logger.info("TranscriptionService успешно инициализирован")

    async def transcribe_audio(self, file_url: str, language: Optional[str] = None) -> Dict[str, Any]:
        """
        Транскрибация аудио файла через OpenAI Whisper API

        Args:
            file_url: URL аудио файла
            language: Код языка для транскрипции (опционально)

        Returns:
            Dict с результатом транскрипции
        """
        try:
            logger.info(f"Начинаем транскрипцию файла: {file_url}")

            # Скачиваем файл
            response = requests.get(file_url, timeout=30)
            response.raise_for_status()

            # Создаем временный файл
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_file:
                temp_file.write(response.content)
                temp_file_path = temp_file.name

            try:
                # Открываем файл для транскрипции
                with open(temp_file_path, 'rb') as audio_file:
                    # Подготавливаем параметры для Whisper API
                    transcription_params = {
                        "file": audio_file,
                        "model": "whisper-1",
                        "response_format": "verbose_json"
                    }

                    # Добавляем язык если указан
                    if language:
                        transcription_params["language"] = language
                        logger.info(f"Используем язык: {language}")

                    # Выполняем транскрипцию
                    result = self.client.audio.transcriptions.create(**transcription_params)

                    logger.info("Транскрипция успешно завершена")

                    return {
                        "success": True,
                        "text": result.text,
                        "language": result.language if hasattr(result, 'language') else language,
                        "duration": result.duration if hasattr(result, 'duration') else None,
                        "segments": getattr(result, 'segments', None)
                    }

            finally:
                # Удаляем временный файл
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    logger.warning(f"Не удалось удалить временный файл: {e}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при скачивании файла: {e}")
            return {
                "success": False,
                "error": f"Не удалось скачать аудио файл: {str(e)}"
            }

        except openai.APIError as e:
            logger.error(f"Ошибка OpenAI API: {e}")
            return {
                "success": False,
                "error": f"Ошибка транскрипции: {str(e)}"
            }

        except Exception as e:
            logger.error(f"Неожиданная ошибка при транскрипции: {e}")
            return {
                "success": False,
                "error": f"Внутренняя ошибка: {str(e)}"
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