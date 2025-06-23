# services/language_detector.py
import logging
from langdetect import detect, detect_langs
from langdetect.lang_detect_exception import LangDetectException

logger = logging.getLogger(__name__)

class LanguageDetector:
    def analyze_language(self, text: str) -> dict:
        """
        Анализирует текст для определения языка и уверенности.
        Возвращает словарь, например: {'language': 'km', 'confidence': 0.99}
        """
        if not text or not text.strip():
            logger.warning("Передан пустой текст для определения языка.")
            return {'language': 'unknown', 'confidence': 0.0}

        try:
            # detect_langs возвращает список языков с вероятностями
            langs = detect_langs(text)
            if not langs:
                raise LangDetectException(0, "Langdetect вернул пустой список")

            # Берем самый вероятный язык
            best_match = langs[0]
            language_code = best_match.lang
            confidence = best_match.prob

            logger.info(f"Язык определен как '{language_code}' с уверенностью {confidence:.2f}")

            return {
                'language': language_code,
                'confidence': confidence
            }
        except LangDetectException:
            logger.warning(f"Не удалось определить язык для текста: '{text[:70]}...'")
            return {'language': 'unknown', 'confidence': 0.0}