# services/media_handler.py
import os
import logging
from typing import Optional, Tuple, Dict, Any
from .audio_processor import AudioProcessor
from .language_detector import LanguageDetector
from .transcription_service import TranscriptionService
from .translation_service import TranslationService
from .native_script_service import NativeScriptService

logger = logging.getLogger(__name__)


class MediaHandler:
    def __init__(self, transcription_service: TranscriptionService, translation_service: TranslationService):
        self.audio_processor = AudioProcessor()
        self.language_detector = LanguageDetector()
        self.transcription_service = transcription_service
        self.translation_service = translation_service
        self.native_script_service = NativeScriptService()

    def process_media(self, file_path: str, user_preferences: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Обрабатывает медиа файл (аудио/видео) и возвращает результат.
        """
        audio_path = None
        user_prefs = user_preferences or {}

        try:
            logger.info(f"Начинаем обработку файла: {file_path}")

            # 1. Получаем предпочтения пользователя
            expected_language = user_prefs.get('preferred_language')
            target_language = user_prefs.get('target_language', 'en')
            auto_translate = user_prefs.get('auto_translate', False)

            logger.info(f"User preferences: expected_language={expected_language}, target_language={target_language}")

            # 2. Конвертируем в аудио если нужно
            audio_path = self.audio_processor.process_file(file_path)
            if not audio_path:
                return {'success': False, 'error': 'Не удалось обработать медиа файл'}

            # 3. Транскрибируем аудио с умным определением языка
            text, detected_language = self.transcription_service.transcribe_with_fallback(
                audio_path,
                expected_language  # Передаем язык, указанный пользователем
            )

            if text.startswith("Ошибка"):
                return {'success': False, 'error': text}

            # 4. Дополнительный анализ языка, если он не был задан принудительно
            if not expected_language:
                language_analysis = self.language_detector.analyze_language(text)
                final_language = self._choose_best_language(
                    detected_language,
                    language_analysis.get('language'),
                    language_analysis.get('confidence', 0)
                )
                # 🔧 УЛУЧШЕННОЕ определение кхмерского языка
                final_language = self._improve_khmer_detection(text, final_language)
            else:
                final_language = expected_language

            # 5. Анализ качества транскрипции
            quality_analysis = self._analyze_transcription_quality(text, final_language)

            # 6. Создаем результат
            result = {
                'success': True,
                'transcription': text,
                'detected_language': final_language,
                'quality_analysis': quality_analysis,
                'language_info': self._get_language_info_safe(final_language),
                'translation': None
            }

            # 7. Переводим, если нужно
            if auto_translate and target_language and target_language != final_language:
                translation_result = self.translation_service.translate_text(
                    text, target_language, final_language
                )
                if translation_result.get('success'):
                    result['translation'] = translation_result.get('translated_text')
                    result['translation_target'] = target_language

            logger.info(f"Обработка завершена. Язык: {final_language}. Результат: {text[:100]}")
            return result

        except Exception as e:
            logger.error(f"Критическая ошибка при обработке медиа: {e}", exc_info=True)
            return {'success': False, 'error': f'Произошла внутренняя ошибка: {str(e)}'}
        finally:
            # 8. Очищаем временные файлы
            if audio_path and audio_path != file_path:
                self.audio_processor.cleanup_temp_file(audio_path)
            self.audio_processor.cleanup_temp_file(file_path)

    def _choose_best_language(self, whisper_lang: str, detector_lang: str, confidence: float) -> str:
        """Выбирает наиболее вероятный язык из разных источников."""
        if whisper_lang and whisper_lang != 'auto':
            # Whisper часто точнее, особенно если он уверен
            return whisper_lang
        if confidence > 0.7:
            return detector_lang
        return whisper_lang if whisper_lang != 'auto' else detector_lang

    # 🔧 --- НОВЫЙ МЕТОД --- 🔧
    def _improve_khmer_detection(self, text: str, detected_language: str) -> str:
        """
        Улучшенное определение кхмерского языка путем анализа транслитерированного текста.
        """
        if not text or detected_language == 'km':
            return detected_language

        text_lower = text.lower()
        khmer_keywords = [
            'bong', 'avan', 'kue', 'vie', 'mien', 'dak', 'chun', 'neng',
            'phnom penh', 'arkun', 'chum reap suor', 'som tos', 'ot te',
            'siem reap', 'battambang', 'kampong', 'susuday', 'ksabay',
            'preah', 'wat', 'nak', 'knhom', 'srey', 'pros', 'chea', 'thlai',
            'khmer', 'cambodia'
        ]

        khmer_word_count = sum(1 for keyword in khmer_keywords if keyword in text_lower)
        total_words = len(text_lower.split())

        if total_words == 0:
            return detected_language

        # Логика принятия решения
        # Если Whisper определил тагальский ('tl') или вьетнамский ('vi'), но есть кхмерские слова - меняем на кхмерский.
        if detected_language in ['tl', 'vi'] and khmer_word_count > 0:
            logger.info(f"Обнаружены кхмерские слова. Меняем язык с '{detected_language}' на 'km'.")
            return 'km'

        # Если язык определен как английский, но есть признаки кхмерского.
        if detected_language == 'en' and total_words > 0:
            khmer_ratio = khmer_word_count / total_words
            # Если более 15% слов - кхмерские, это почти наверняка кхмерский
            if khmer_ratio > 0.15:
                logger.info(f"Обнаружено {khmer_ratio:.0%} кхмерских слов. Меняем язык с 'en' на 'km'.")
                return 'km'
            # Даже одно ключевое слово в очень коротком тексте - сильный сигнал
            if khmer_word_count >= 1 and total_words <= 5:
                logger.info(f"Короткий текст с кхмерским словом. Меняем язык с 'en' на 'km'.")
                return 'km'

        return detected_language

    def _analyze_transcription_quality(self, text: str, language: str) -> Dict[str, Any]:
        """Анализирует качество транскрипции для нативных языков"""
        # ... (код без изменений)
        try:
            native_languages = ['km', 'th', 'zh', 'ja', 'ko', 'vi']
            if language in native_languages:
                analysis = self.native_script_service.analyze_script_quality(text, language)
                analysis['formatted_message'] = self.native_script_service.format_quality_message(
                    analysis, language
                )
                return analysis
            else:
                return {
                    'quality': 'good',
                    'native_ratio': 1.0,
                    'message': '✅ Транскрипция выполнена успешно.',
                    'has_transliteration': False
                }
        except Exception as e:
            logger.error(f"Ошибка при анализе качества: {e}")
            return {'quality': 'unknown', 'message': '⚠️ Не удалось проанализировать качество.'}

    def _get_language_info_safe(self, detected_language: str) -> Dict[str, str]:
        """Безопасно получает информацию о языке"""
        # ... (код без изменений)
        language_names = {
            'km': {'name': 'Khmer', 'native': 'ខ្មែរ'},
            'en': {'name': 'English', 'native': 'English'},
            'ru': {'name': 'Russian', 'native': 'Русский'},
            'th': {'name': 'Thai', 'native': 'ไทย'},
            'vi': {'name': 'Vietnamese', 'native': 'Tiếng Việt'},
            'zh': {'name': 'Chinese', 'native': '中文'},
            'ja': {'name': 'Japanese', 'native': '日本語'},
            'ko': {'name': 'Korean', 'native': '한국어'},
            'tl': {'name': 'Tagalog', 'native': 'Tagalog'}
        }
        return language_names.get(detected_language,
                                  {'name': detected_language.upper(), 'native': detected_language.upper()})

    def validate_file(self, file_path: str, is_premium: bool = False) -> Tuple[bool, str]:
        """Проверяет файл на соответствие ограничениям"""
        return self.audio_processor.validate_audio_file(file_path)