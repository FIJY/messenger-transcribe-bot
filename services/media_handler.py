# services/media_handler.py - ПОЛНАЯ ВЕРСИЯ С ИНТЕГРАЦИЕЙ СЕРВИСА КОРРЕКЦИИ
import os
import logging
from typing import Optional, Tuple, Dict, Any

# Импорты ваших сервисов
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
        self.correction_service = CorrectionService()  # Инициализация нового сервиса

    def process_media(self, file_path: str, user_preferences: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Обрабатывает медиа файл, включая логику коррекции транслитерации.
        """
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

            # Новая логика коррекции
            final_text = text
            quality_analysis = self._analyze_transcription_quality(final_text, detected_language)

            # Если язык определен как кхмерский, но качество плохое (вероятно, латиница)
            if detected_language == 'km' and quality_analysis.get('quality') == 'poor':
                logger.info("Обнаружена некачественная транслитерация кхмерского. Запускаем GPT коррекцию...")

                # Вызываем наш новый сервис
                corrected_text = self.correction_service.correct_khmer_transliteration(final_text)

                if corrected_text:
                    final_text = corrected_text
                    # Повторно анализируем качество уже исправленного текста
                    quality_analysis = self._analyze_transcription_quality(final_text, detected_language)

            # Создаем финальный результат
            result = {
                'success': True,
                'transcription': final_text,  # Используем исправленный текст
                'detected_language': detected_language,
                'quality_analysis': quality_analysis,
                'language_info': self._get_language_info_safe(detected_language),
                'processed_audio_path': audio_path
            }

            logger.info(f"Обработка завершена. Результат: {final_text[:100]}...")
            return result

        except Exception as e:
            logger.error(f"Критическая ошибка при обработке медиа: {e}", exc_info=True)
            return {'success': False, 'error': 'Произошла внутренняя ошибка', 'processed_audio_path': audio_path}

    def _analyze_transcription_quality(self, text: str, language: str) -> Dict[str, Any]:
        """Анализирует качество транскрипции для нативных языков"""
        try:
            native_languages = ['km', 'th', 'zh', 'ja', 'ko', 'vi']

            if language in native_languages:
                # Используем специализированный сервис
                analysis = self.native_script_service.analyze_script_quality(text, language)

                # Добавляем форматированное сообщение
                if 'message' not in analysis:
                    analysis['formatted_message'] = self.native_script_service.format_quality_message(
                        analysis, language
                    )
                return analysis
            else:
                # Базовый анализ для других языков
                return {
                    'quality': 'good',
                    'native_ratio': 1.0,
                    'message': '✅ Транскрипция выполнена успешно',
                    'has_transliteration': False
                }

        except Exception as e:
            logger.error(f"Ошибка при анализе качества: {e}")
            return {
                'quality': 'unknown',
                'native_ratio': 0.0,
                'message': '⚠️ Не удалось проанализировать качество',
                'error': str(e)
            }

    def _get_language_info_safe(self, detected_language: str) -> Dict[str, str]:
        """Безопасно получает информацию о языке"""
        language_names = {
            'km': {'name': 'Khmer', 'native': 'ខ្មែរ'},
            'en': {'name': 'English', 'native': 'English'},
            'ru': {'name': 'Russian', 'native': 'Русский'},
            'th': {'name': 'Thai', 'native': 'ไทย'},
            'vi': {'name': 'Vietnamese', 'native': 'Tiếng Việt'},
            'zh': {'name': 'Chinese', 'native': '中文'},
            'ja': {'name': 'Japanese', 'native': '日本語'},
            'ko': {'name': 'Korean', 'native': '한국어'},
            'ar': {'name': 'Arabic', 'native': 'العربية'},
            'hi': {'name': 'Hindi', 'native': 'हिन्दी'},
            'fr': {'name': 'French', 'native': 'Français'},
            'es': {'name': 'Spanish', 'native': 'Español'},
            'de': {'name': 'German', 'native': 'Deutsch'},
            'it': {'name': 'Italian', 'native': 'Italiano'},
            'pt': {'name': 'Portuguese', 'native': 'Português'},
            'tl': {'name': 'Tagalog', 'native': 'Tagalog'}
        }
        return language_names.get(detected_language, {'name': detected_language.upper(), 'native': ''})

    def validate_file(self, file_path: str, is_premium: bool = False) -> Tuple[bool, str]:
        """Проверяет файл на соответствие ограничениям"""
        return self.audio_processor.validate_audio_file(file_path)