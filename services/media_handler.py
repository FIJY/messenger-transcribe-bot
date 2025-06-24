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
from .google_stt_service import GoogleSTTService  # <== НОВЫЙ ИМПОРТ

logger = logging.getLogger(__name__)


class MediaHandler:
    def __init__(self, transcription_service: TranscriptionService, translation_service: TranslationService):
        self.audio_processor = AudioProcessor()
        self.language_detector = LanguageDetector()
        self.native_script_service = NativeScriptService()
        self.correction_service = CorrectionService()

        # Сохраняем сервисы, которые нам передали
        self.transcription_service = transcription_service
        self.translation_service = translation_service

        # ===> ИНИЦИАЛИЗИРУЕМ НОВЫЙ СЕРВИС GOOGLE <===
        try:
            self.google_stt_service = GoogleSTTService()
        except Exception as e:
            logger.error(f"Could not initialize GoogleSTTService. Khmer transcription will fail. Error: {e}")
            self.google_stt_service = None

    def process_media(self, file_path: str, user_preferences: Optional[Dict] = None) -> Dict[str, Any]:
        audio_path = None
        user_prefs = user_preferences or {}
        try:
            expected_language = user_prefs.get('preferred_language')

            audio_path = self.audio_processor.process_file(file_path)
            if not audio_path:
                return {'success': False, 'error': Exception('Failed to process media file')}

            # ===> НАЧАЛО ЛОГИКИ "УМНОГО ПЕРЕКЛЮЧАТЕЛЯ" <===

            # Шаг 1: Определяем язык, с которым будем работать.
            language_to_process = expected_language
            if not language_to_process:
                # Если язык не указан пользователем, делаем быстрое автоопределение с помощью Whisper
                _, detected_by_whisper = self.transcription_service.transcribe_with_fallback(audio_path)
                language_to_process = detected_by_whisper

            logger.info(f"Language pre-determined for processing: {language_to_process}")

            # Шаг 2: Выбираем движок в зависимости от языка.
            if language_to_process == 'km' and self.google_stt_service:
                # --- Используем Google для кхмерского языка ---
                logger.info("Routing to Google STT for Khmer language.")
                # Google требует BCP-47 код, например 'km-KH'
                text = self.google_stt_service.transcribe_audio(audio_path, language_code='km-KH')
                detected_language = 'km'
            else:
                # --- Используем Whisper для всех остальных языков ---
                logger.info(f"Routing to Whisper for language: {language_to_process}")
                result_dict = self.transcription_service._transcribe_sync(audio_path, language_hint=language_to_process)
                if not result_dict['success']:
                    raise result_dict['error']
                text = result_dict.get('text', '')
                detected_language = result_dict.get('detected_language')

            # ===> КОНЕЦ ЛОГИКИ "УМНОГО ПЕРЕКЛЮЧАТЕЛЯ" <===

            if not text or not text.strip():
                logger.warning(
                    f"Transcription for language '{detected_language}' resulted in empty text. Treating as failure.")
                return {'success': False, 'error': Exception('Transcription result was empty.')}

            # Постобработка и коррекция остаются без изменений.
            # Теперь они будут применяться к гораздо более качественному тексту от Google для кхмерского.
            final_text = text
            if detected_language == 'km':
                quality_analysis = self._analyze_transcription_quality(final_text, detected_language)
                if quality_analysis.get('quality') == 'poor':
                    corrected_text = self.correction_service.correct_khmer_transliteration(final_text)
                    if corrected_text: final_text = corrected_text

                processed_text = self.correction_service.post_process_khmer_text(final_text)
                if processed_text: final_text = processed_text

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
            logger.error(f"Critical error in media processing: {e}", exc_info=True)
            return {'success': False, 'error': e, 'processed_audio_path': audio_path}

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
                return {'quality': 'poor', 'message': '⚠️ Looks like Khmer was recognized as English.'}
            else:
                return {'quality': 'good', 'message': '✅ Transcription successful'}
        else:
            return {'quality': 'good', 'message': '✅ Quality analysis not required for this language'}

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