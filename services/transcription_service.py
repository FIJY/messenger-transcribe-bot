import openai
import os
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class TranscriptionService:
    def __init__(self):
        """Инициализация сервиса транскрипции"""
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")

        self.client = openai.OpenAI(api_key=api_key)
        logger.info("TranscriptionService initialized with OpenAI API")

    def transcribe_audio(self, audio_file_path: str, detected_language: Optional[str] = None) -> Tuple[str, str]:
        """
        Транскрибирует аудио файл используя OpenAI Whisper API

        Args:
            audio_file_path: путь к аудио файлу
            detected_language: код языка (например 'km' для кхмерского)

        Returns:
            Tuple[text, language]: транскрибированный текст и определенный язык
        """
        try:
            with open(audio_file_path, 'rb') as audio_file:
                # Параметры для OpenAI Whisper API
                transcription_params = {
                    'file': audio_file,
                    'model': 'whisper-1',
                    'response_format': 'verbose_json',  # Получаем подробную информацию
                    'temperature': 0.0,  # Низкая температура для стабильности
                }

                # Если язык определен, передаем его в API
                if detected_language:
                    # Маппинг наших кодов языков в коды OpenAI
                    language_mapping = {
                        'khmer': 'km',
                        'km': 'km',
                        'thai': 'th',
                        'th': 'th',
                        'vietnamese': 'vi',
                        'vi': 'vi',
                        'english': 'en',
                        'en': 'en',
                        'russian': 'ru',
                        'ru': 'ru',
                        'chinese': 'zh',
                        'zh': 'zh'
                    }

                    openai_language = language_mapping.get(detected_language.lower(), detected_language)
                    transcription_params['language'] = openai_language

                    logger.info(f"Транскрибируем с языком: {openai_language}")

                # Выполняем транскрипцию
                response = self.client.audio.transcriptions.create(**transcription_params)

                # Извлекаем результаты
                if hasattr(response, 'text'):
                    transcribed_text = response.text.strip()
                else:
                    transcribed_text = response.get('text', '').strip()

                # Получаем определенный язык
                if hasattr(response, 'language'):
                    detected_lang = response.language
                elif isinstance(response, dict) and 'language' in response:
                    detected_lang = response['language']
                else:
                    detected_lang = detected_language or 'unknown'

                if not transcribed_text:
                    logger.warning("Получен пустой текст транскрипции")
                    return "Не удалось распознать речь в аудио.", detected_lang

                # Специальная обработка для кхмерского языка
                if detected_lang == 'km' or detected_language in ['km', 'khmer']:
                    transcribed_text = self._improve_khmer_output(transcribed_text)

                logger.info(f"Успешная транскрипция: длина {len(transcribed_text)} символов, язык: {detected_lang}")
                return transcribed_text, detected_lang

        except openai.OpenAIError as e:
            logger.error(f"Ошибка OpenAI API: {e}")
            return f"Ошибка транскрипции: {str(e)}", "unknown"
        except FileNotFoundError:
            logger.error(f"Аудио файл не найден: {audio_file_path}")
            return "Файл не найден.", "unknown"
        except Exception as e:
            logger.error(f"Неожиданная ошибка при транскрипции: {e}")
            return "Произошла ошибка при обработке аудио.", "unknown"

    def transcribe_with_fallback(self, audio_file_path: str, detected_language: Optional[str] = None) -> Tuple[
        str, str]:
        """
        Транскрипция с fallback стратегией для проблемных языков
        """
        # Сначала пробуем с определенным языком
        text, lang = self.transcribe_audio(audio_file_path, detected_language)

        # Специальная обработка для кхмерского языка
        if detected_language in ['khmer', 'km'] and self._is_poor_khmer_transcription(text):
            logger.warning("Плохая транскрипция кхмерского языка, пробуем альтернативные стратегии")

            # Попытка 1: без указания языка
            text_no_lang, lang_no_lang = self.transcribe_audio(audio_file_path, None)

            # Попытка 2: с английским как fallback (иногда помогает)
            text_en, lang_en = self.transcribe_audio(audio_file_path, 'en')

            # Выбираем лучший результат
            results = [
                (text, lang, self._calculate_khmer_score(text)),
                (text_no_lang, lang_no_lang, self._calculate_khmer_score(text_no_lang)),
                (text_en, lang_en, self._calculate_khmer_score(text_en))
            ]

            # Сортируем по качеству кхмерского текста
            results.sort(key=lambda x: x[2], reverse=True)
            best_text, best_lang, best_score = results[0]

            if best_score > 0:
                logger.info(f"Выбран лучший результат с оценкой: {best_score}")
                return best_text, 'km'  # Принудительно устанавливаем km для кхмерского
            else:
                # Если все попытки неудачны, возвращаем с предупреждением
                warning = "⚠️ Система не смогла корректно распознать кхмерскую речь.\n"
                warning += "Рекомендации:\n"
                warning += "• Говорите четче и медленнее\n"
                warning += "• Записывайте в тихом месте\n"
                warning += "• Используйте качественный микрофон\n\n"
                warning += f"Попытка распознавания:\n{text}"
                return warning, 'km'

        return text, lang

    @staticmethod
    def _calculate_khmer_score(text: str) -> float:
        """
        Вычисляет оценку качества кхмерского текста
        """
        if not text:
            return 0.0

        # Считаем кхмерские символы
        khmer_chars = sum(1 for char in text if '\u1780' <= char <= '\u17FF')
        total_chars = len([char for char in text if char.isalpha()])

        if total_chars == 0:
            return 0.0

        # Базовая оценка по соотношению кхмерских символов
        khmer_ratio = khmer_chars / total_chars

        # Бонусы за длину (более длинный текст обычно лучше)
        length_bonus = min(len(text) / 100, 1.0)

        # Штраф за слишком короткий текст
        if len(text.strip()) < 10:
            length_bonus *= 0.5

        return khmer_ratio * 0.8 + length_bonus * 0.2

    @staticmethod
    def _improve_khmer_output(text: str) -> str:
        """
        Улучшает вывод для кхмерского языка
        """
        if not text:
            return text

        # Проверяем соотношение кхмерских символов
        khmer_chars = sum(1 for char in text if '\u1780' <= char <= '\u17FF')
        total_chars = len([char for char in text if char.isalpha()])

        if total_chars > 0:
            khmer_ratio = khmer_chars / total_chars

            # Если очень мало кхмерских символов (возможна транслитерация)
            if khmer_ratio < 0.1:
                warning = "⚠️ Получена транслитерация вместо кхмерского скрипта.\n"
                warning += "Возможные причины:\n"
                warning += "• Плохое качество аудио\n"
                warning += "• Смешение языков в речи\n"
                warning += "• Ограничения системы распознавания\n\n"
                warning += "Транслитерированный текст:\n"
                return warning + text
            elif khmer_ratio < 0.5:
                return "⚠️ Частичное распознавание кхмерского языка:\n\n" + text

        return text

    @staticmethod
    def _is_poor_khmer_transcription(text: str) -> bool:
        """
        Проверяет, является ли транскрипция кхмерского языка некачественной
        """
        if not text:
            return True

        # Проверяем наличие кхмерских символов
        khmer_chars = sum(1 for char in text if '\u1780' <= char <= '\u17FF')
        total_chars = len([char for char in text if char.isalpha()])

        if total_chars == 0:
            return True

        # Если менее 50% символов кхмерские, считаем транскрипцию плохой
        khmer_ratio = khmer_chars / total_chars
        return khmer_ratio < 0.5

    @staticmethod
    def get_supported_languages() -> list:
        """
        Возвращает список поддерживаемых языков
        """
        return [
            'af', 'ar', 'hy', 'az', 'be', 'bs', 'bg', 'ca', 'zh', 'hr', 'cs', 'da', 'nl',
            'en', 'et', 'fi', 'fr', 'gl', 'de', 'el', 'he', 'hi', 'hu', 'is', 'id', 'it',
            'ja', 'kn', 'kk', 'ko', 'lv', 'lt', 'mk', 'ms', 'ml', 'mt', 'mi', 'mr', 'ne',
            'no', 'fa', 'pl', 'pt', 'ro', 'ru', 'sr', 'sk', 'sl', 'es', 'sw', 'sv', 'tl',
            'ta', 'th', 'tr', 'uk', 'ur', 'vi', 'cy', 'km'  # km = кхмерский
        ]