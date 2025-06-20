# services/media_handler.py - ВЕРСИЯ С УЧЕТОМ НЕПРАВИЛЬНОГО ОПРЕДЕЛЕНИЯ КАК TAGALOG
import os
import logging
from typing import Optional, Tuple, Dict, Any

from .audio_processor import AudioProcessor
from .language_detector import LanguageDetector
from .transcription_service import TranscriptionService
from .translation_service import TranslationService
from .native_script_service import NativeScriptService
from .correction_service import CorrectionService

logger = logging.getLogger(__name__)


class MediaHandler:
    def __init__(self, transcription_service: TranscriptionService, translation_service: TranslationService):
        self.audio_processor = AudioProcessor()
        self.language_detector = LanguageDetector()
        self.native_script_service = NativeScriptService()
        self.transcription_service = transcription_service
        self.translation_service = translation_service
        self.correction_service = CorrectionService()

    def process_media(self, file_path: str, user_preferences: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Полный цикл обработки: транскрипция -> исправление -> пост-обработка.
        """
        # ... (начало метода без изменений)
        audio_path = None
        user_prefs = user_preferences or {}
        try:
            logger.info(f"Начинаем обработку файла: {file_path}")
            expected_language = user_prefs.get('preferred_language')
            audio_path = self.audio_processor.process_file(file_path)
            if not audio_path:
                return {'success': False, 'error': 'Не удалось обработать медиа файл'}

            text, detected_language = self.transcription_service.transcribe_with_fallback(
                audio_path, expected_language
            )

            if text.startswith("Ошибка"):
                return {'success': False, 'error': text, 'processed_audio_path': audio_path}

            final_text = text

            # 🔧 НОВАЯ ЛОГИКА: Проверяем на ошибочное определение как Tagalog
            if detected_language == 'tl' and self._is_likely_khmer_transliteration(final_text):
                logger.warning(f"Язык определен как 'tl', но текст похож на кхмерский. Принудительно меняем на 'km'.")
                detected_language = 'km'

            # Этап 1: Исправление транслитерации (если нужно)
            quality_analysis = self._analyze_transcription_quality(final_text, detected_language)
            if detected_language == 'km' and quality_analysis.get('quality') == 'poor':
                logger.info("Обнаружена некачественная транслитерация. Запускаем GPT коррекцию...")
                corrected_text = self.correction_service.correct_khmer_transliteration(final_text)
                if corrected_text:
                    final_text = corrected_text

            # ЭТАП 2: Финальная пост-обработка текста
            if detected_language == 'km':
                logger.info("Запускаем финальную пост-обработку кхмерского текста...")
                processed_text = self.correction_service.post_process_khmer_text(final_text)
                if processed_text:
                    final_text = processed_text

            final_quality_analysis = self._analyze_transcription_quality(final_text, detected_language)

            result = {
                'success': True,
                'transcription': final_text,
                'detected_language': detected_language,
                'quality_analysis': final_quality_analysis,
                'language_info': self._get_language_info_safe(detected_language),
                'processed_audio_path': audio_path
            }
            logger.info(f"Обработка полностью завершена. Финальный текст: {final_text[:100]}...")
            return result
        except Exception as e:
            logger.error(f"Критическая ошибка при обработке медиа: {e}", exc_info=True)
            return {'success': False, 'error': 'Произошла внутренняя ошибка', 'processed_audio_path': audio_path}

    def _is_likely_khmer_transliteration(self, text: str) -> bool:
        """Простая проверка на наличие кхмерских слов в латинице."""
        text_lower = text.lower()
        # Ключевые слова, которые редко встречаются в тагальском, но часто в транслитерации кхмерского
        khmer_keywords = ['bong', 'sosay', 'arkun', 'chom', 'neng', 'thlai', 'phnom']
        found_count = sum(1 for keyword in khmer_keywords if keyword in text_lower)
        return found_count >= 2  # Считаем кхмерским, если нашлось хотя бы 2 слова

    # Остальные методы (_analyze_transcription_quality, и т.д.) остаются без изменений
    def _analyze_transcription_quality(self, text: str, language: str) -> Dict[str, Any]:
        try:
            native_languages = ['km', 'th', 'zh', 'ja', 'ko', 'vi']
            if language in native_languages:
                analysis = self.native_script_service.analyze_script_quality(text, language)
                if 'message' not in analysis:
                    analysis['formatted_message'] = self.native_script_service.format_quality_message(
                        analysis, language
                    )
                return analysis
            else:
                return {'quality': 'good', 'native_ratio': 1.0, 'message': '✅ Транскрипция выполнена успешно',
                        'has_transliteration': False}
        except Exception as e:
            logger.error(f"Ошибка при анализе качества: {e}")
            return {'quality': 'unknown', 'native_ratio': 0.0, 'message': '⚠️ Не удалось проанализировать качество',
                    'error': str(e)}

    def _get_language_info_safe(self, detected_language: str) -> Dict[str, str]:
        language_names = {
            'km': {'name': 'Khmer', 'native': 'ខ្មែរ'}, 'en': {'name': 'English', 'native': 'English'},
            'ru': {'name': 'Russian', 'native': 'Русский'}, 'th': {'name': 'Thai', 'native': 'ไทย'},
            'vi': {'name': 'Vietnamese', 'native': 'Tiếng Việt'}, 'tl': {'name': 'Tagalog', 'native': 'Tagalog'}
        }
        return language_names.get(detected_language, {'name': detected_language.upper(), 'native': ''})

    def validate_file(self, file_path: str, is_premium: bool = False) -> Tuple[bool, str]:
        return self.audio_processor.validate_audio_file(file_path)