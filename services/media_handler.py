# services/media_handler.py
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
        audio_path = None
        user_prefs = user_preferences or {}
        try:
            # Получаем язык, если это ретрай по кнопке
            expected_language = user_prefs.get('preferred_language')

            audio_path = self.audio_processor.process_file(file_path)
            if not audio_path:
                return {'success': False, 'error': 'Не удалось обработать медиа файл'}

            # ===> НАЧАЛО НОВОЙ ЛОГИКИ <===
            if expected_language:
                # --- ЭТО ЛОГИКА ДЛЯ РЕТРАЯ (КОГДА ЯЗЫК УКАЗАН) ---
                logger.info(f"Выполняется принудительная транскрипция для языка: {expected_language}")
                # Вызываем транскрипцию с подсказкой
                result_dict = self.transcription_service._transcribe_sync(audio_path, language_hint=expected_language)
                text = result_dict.get('text', '')

                # ВАЖНО: Мы полностью доверяем пользователю и ИГНОРИРУЕМ язык от Whisper.
                # Мы сами присваиваем тот язык, который выбрал пользователь.
                detected_language = expected_language
                logger.info(f"Язык от Whisper проигнорирован. Принудительно установлен язык: {detected_language}")

            else:
                # --- ЭТО СТАНДАРТНАЯ ЛОГИКА (ДЛЯ ПЕРВОЙ ЗАГРУЗКИ) ---
                logger.info("Выполняется стандартная транскрипция с автоопределением.")
                text, detected_language = self.transcription_service.transcribe_with_fallback(audio_path)

            # ===> КОНЕЦ НОВОЙ ЛОГИКИ <===

            if text.startswith("Ошибка"):
                return {'success': False, 'error': text, 'processed_audio_path': audio_path}

            final_text = text

            # Проверяем на ошибочное определение как английский или тагальский (актуально для первого прогона)
            if not expected_language and detected_language in ['tl', 'en'] and self._is_likely_khmer_transliteration(
                    final_text):
                logger.warning(f"Язык определен как '{detected_language}', но похож на кхмерский. Меняем на 'km'.")
                detected_language = 'km'

            # Применяем коррекцию и постобработку, особенно для кхмерского
            if detected_language == 'km':
                # Сначала пытаемся исправить транслитерацию
                quality_analysis = self._analyze_transcription_quality(final_text, detected_language)
                if quality_analysis.get('quality') == 'poor':
                    corrected_text = self.correction_service.correct_khmer_transliteration(final_text)
                    if corrected_text:
                        final_text = corrected_text
                        logger.info("Транслитерация исправлена с помощью GPT.")

                # Затем "причесываем" результат
                processed_text = self.correction_service.post_process_khmer_text(final_text)
                if processed_text:
                    final_text = processed_text
                    logger.info("Текст на кхмерском прошел постобработку GPT.")

            final_quality_analysis = self._analyze_transcription_quality(final_text, detected_language)

            result = {
                'success': True,
                'transcription': final_text,
                'detected_language': detected_language,
                'quality_analysis': final_quality_analysis,
                'language_info': self._get_language_info_safe(detected_language),
                'processed_audio_path': audio_path,
                'original_file_path': file_path
            }
            return result
        except Exception as e:
            logger.error(f"Критическая ошибка при обработке медиа: {e}", exc_info=True)
            return {'success': False, 'error': 'Произошла внутренняя ошибка', 'processed_audio_path': audio_path}

    def _is_likely_khmer_transliteration(self, text: str) -> bool:
        text_lower = text.lower()
        khmer_keywords = ['bong', 'sosay', 'arkun', 'chom', 'neng', 'thlai', 'phnom', 'kath', 'knhom', 'sok', 'sabay']
        return sum(1 for keyword in khmer_keywords if keyword in text_lower) >= 2

    def _analyze_transcription_quality(self, text: str, language: str) -> Dict[str, Any]:
        native_languages = ['km', 'th', 'zh', 'ja', 'ko', 'vi']
        if language in native_languages:
            return self.native_script_service.analyze_script_quality(text, language)
        elif language == 'en':
            if self._is_likely_khmer_transliteration(text):
                return {'quality': 'poor', 'message': '⚠️ Похоже, кхмерский был распознан как английский.'}
            else:
                return {'quality': 'good', 'message': '✅ Транскрипция выполнена успешно'}
        else:
            return {'quality': 'good', 'message': '✅ Анализ качества для этого языка не требуется'}

    def _get_language_info_safe(self, detected_language: str) -> Dict[str, str]:
        language_names = {
            'km': {'name': 'Khmer', 'native': 'ខ្មែរ'}, 'en': {'name': 'English', 'native': 'English'},
            'ru': {'name': 'Russian', 'native': 'Русский'}, 'th': {'name': 'Thai', 'native': 'ไทย'},
            'vi': {'name': 'Vietnamese', 'native': 'Tiếng Việt'}, 'tl': {'name': 'Tagalog', 'native': 'Tagalog'},
            'zh': {'name': 'Chinese', 'native': '中文'}, 'de': {'name': 'German', 'native': 'Deutsch'}
        }
        return language_names.get(detected_language, {'name': detected_language.upper(), 'native': ''})

    def validate_file(self, file_path: str, is_premium: bool = False) -> Tuple[bool, str]:
        return self.audio_processor.validate_audio_file(file_path, is_premium)