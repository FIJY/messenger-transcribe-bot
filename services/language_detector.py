import logging
from langdetect import detect, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException
import re
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Устанавливаем seed для стабильности результатов
DetectorFactory.seed = 0


class LanguageDetector:
    def __init__(self):
        """Инициализация детектора языка"""
        self.script_patterns = {
            'ru': re.compile(r'[а-яё]', re.IGNORECASE),
            'uk': re.compile(r'[іїєґ]', re.IGNORECASE),
            'ar': re.compile(r'[\u0600-\u06FF\u0750-\u077F]'),
            'zh': re.compile(r'[\u4e00-\u9fff]'),
            'ja': re.compile(r'[\u3040-\u309f\u30a0-\u30ff]'),
            'ko': re.compile(r'[\uac00-\ud7af]'),
            'th': re.compile(r'[\u0e00-\u0e7f]'),
            'hi': re.compile(r'[\u0900-\u097f]'),
            'he': re.compile(r'[\u0590-\u05ff]'),
            'en': re.compile(r'^[a-zA-Z\s\.\,\!\?\-\'\"\(\)0-9]+$')
        }

        self.confidence_threshold = 0.7
        logger.info("LanguageDetector успешно инициализирован")

    def detect_audio_language(self, audio_path: str) -> str:
        """Определение языка из аудио метаданных или названия"""
        try:
            # Простая проба транскрипции для определения языка
            with open(audio_path, "rb") as audio_file:
                response = self.openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="json"
                )

            # Если Whisper определил язык
            if hasattr(response, 'language'):
                return response.language

            return 'auto'
        except Exception as e:
            return 'auto'


    def analyze_language(self, text: str) -> Dict[str, Any]:
        """
        Анализ языка текста с использованием различных методов

        Args:
            text: Текст для анализа

        Returns:
            Dict с результатами анализа языка
        """
        if not text or not text.strip():
            return {
                "language": "en",
                "confidence": 0.5,
                "method": "default",
                "raw_text": text
            }

        try:
            # Очищаем текст для анализа
            clean_text = self._clean_text(text)

            if len(clean_text) < 3:
                return {
                    "language": "en",
                    "confidence": 0.3,
                    "method": "too_short",
                    "raw_text": text
                }

            # Метод 1: Анализ по скрипту/алфавиту
            script_result = self._detect_by_script(clean_text)
            if script_result and script_result["confidence"] > 0.8:
                logger.info(f"Язык определен по скрипту: {script_result['language']}")
                return {
                    **script_result,
                    "raw_text": text
                }

            # Метод 2: langdetect библиотека
            langdetect_result = self._detect_by_langdetect(clean_text)

            # Комбинируем результаты
            if script_result and langdetect_result:
                if script_result["language"] == langdetect_result["language"]:
                    # Оба метода согласны
                    confidence = min(script_result["confidence"] + langdetect_result["confidence"], 1.0)
                    return {
                        "language": script_result["language"],
                        "confidence": confidence,
                        "method": "combined",
                        "raw_text": text
                    }
                else:
                    # Методы не согласны, выбираем более уверенный
                    if script_result["confidence"] > langdetect_result["confidence"]:
                        return {**script_result, "raw_text": text}
                    else:
                        return {**langdetect_result, "raw_text": text}

            # Используем результат langdetect если он есть
            if langdetect_result:
                return {**langdetect_result, "raw_text": text}

            # Используем результат script анализа если он есть
            if script_result:
                return {**script_result, "raw_text": text}

            # Fallback
            return {
                "language": "en",
                "confidence": 0.4,
                "method": "fallback",
                "raw_text": text
            }

        except Exception as e:
            logger.error(f"Ошибка при анализе языка: {e}")
            return {
                "language": "en",
                "confidence": 0.3,
                "method": "error",
                "error": str(e),
                "raw_text": text
            }

    def _clean_text(self, text: str) -> str:
        """Очистка текста для анализа"""
        # Убираем лишние пробелы и символы
        clean = re.sub(r'\s+', ' ', text.strip())
        # Убираем числа и знаки препинания для лучшего анализа
        clean = re.sub(r'[0-9\.\,\!\?\-\'\"\(\)\[\]]+', ' ', clean)
        return clean.strip()

    def _detect_by_script(self, text: str) -> Optional[Dict[str, Any]]:
        """Определение языка по алфавиту/скрипту"""
        char_count = len(text.replace(' ', ''))
        if char_count == 0:
            return None

        script_scores = {}

        for lang, pattern in self.script_patterns.items():
            matches = len(pattern.findall(text))
            if matches > 0:
                script_scores[lang] = matches / char_count

        if not script_scores:
            return None

        # Находим язык с наибольшим скором
        best_lang = max(script_scores, key=script_scores.get)
        confidence = script_scores[best_lang]

        # Специальная логика для различения похожих языков
        if best_lang == 'ru' and 'uk' in script_scores:
            # Проверяем специфичные украинские символы
            uk_specific = len(self.script_patterns['uk'].findall(text))
            if uk_specific > 0:
                best_lang = 'uk'
                confidence = min(confidence + 0.2, 1.0)

        return {
            "language": best_lang,
            "confidence": min(confidence, 1.0),
            "method": "script_analysis"
        }

    def _detect_by_langdetect(self, text: str) -> Optional[Dict[str, Any]]:
        """Определение языка через langdetect библиотеку"""
        try:
            detected_lang = detect(text)

            # langdetect не возвращает confidence, оценим сами
            confidence = 0.6  # базовая уверенность

            # Увеличиваем уверенность для длинных текстов
            if len(text) > 50:
                confidence += 0.1
            if len(text) > 100:
                confidence += 0.1

            return {
                "language": detected_lang,
                "confidence": min(confidence, 1.0),
                "method": "langdetect"
            }

        except LangDetectException as e:
            logger.warning(f"LangDetect не смог определить язык: {e}")
            return None
        except Exception as e:
            logger.error(f"Ошибка в langdetect: {e}")
            return None

    def detect_language(self, text: str) -> str:
        """
        Простая функция для определения языка (обратная совместимость)

        Args:
            text: Текст для анализа

        Returns:
            Код языка (строка)
        """
        result = self.analyze_language(text)
        return result.get("language", "en")

    def get_supported_languages(self) -> list:
        """Возвращает список поддерживаемых языков"""
        return [
            'af', 'ar', 'bg', 'bn', 'ca', 'cs', 'cy', 'da', 'de', 'el', 'en', 'es', 'et',
            'fa', 'fi', 'fr', 'gu', 'he', 'hi', 'hr', 'hu', 'id', 'it', 'ja', 'kn', 'ko',
            'lt', 'lv', 'mk', 'ml', 'mr', 'ne', 'nl', 'no', 'pa', 'pl', 'pt', 'ro', 'ru',
            'sk', 'sl', 'so', 'sq', 'sv', 'sw', 'ta', 'te', 'th', 'tl', 'tr', 'uk', 'ur',
            'vi', 'zh'
        ]