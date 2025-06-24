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
from .google_stt_service import GoogleSTTService

logger = logging.getLogger(__name__)

LANGUAGE_NAME_TO_CODE_MAP = {
    'khmer': 'km',
    'english': 'en',
    'russian': 'ru',
    'thai': 'th',
    'vietnamese': 'vi',
    'chinese': 'zh',
    'german': 'de',
    'japanese': 'ja',
    'korean': 'ko',
    'tagalog': 'tl',
    'lithuanian': 'lt',
    'belarusian': 'be',
    'french': 'fr',
    # ===> ИСПРАВЛЕНИЕ: Добавлен индонезийский язык <===
    'indonesian': 'id'
}


class MediaHandler:
    def __init__(self, transcription_service: TranscriptionService, translation_service: TranslationService):
        self.audio_processor = AudioProcessor()
        self.language_detector = LanguageDetector()
        self.native_script_service = NativeScriptService()
        self.correction_service = CorrectionService()
        self.transcription_service = transcription_service
        self.translation_service = translation_service
        try:
            self.google_stt_service = GoogleSTTService()
        except Exception as e:
            logger.error(f"Could not initialize GoogleSTTService. Khmer transcription will fail. Error: {e}")
            self.google_stt_service = None

    def process_media(self, file_path: str, user_preferences: Optional[Dict] = None) -> Dict[str, Any]:
        audio_path = None
        converted_wav_path = None
        user_prefs = user_preferences or {}
        try:
            expected_language = user_prefs.get('preferred_language')

            audio_path = self.audio_processor.process_file(file_path)
            if not audio_path:
                return {'success': False, 'error': Exception('Failed to process media file')}

            language_to_process = expected_language
            if not language_to_process:
                _, detected_by_whisper = self.transcription_service.transcribe_with_fallback(audio_path)

                normalized_lang_code = LANGUAGE_NAME_TO_CODE_MAP.get(detected_by_whisper.lower())
                if normalized_lang_code:
                    logger.info(
                        f"Normalized detected language '{detected_by_whisper}' to code '{normalized_lang_code}'.")
                    language_to_process = normalized_lang_code
                else:
                    logger.warning(
                        f"Could not map detected language '{detected_by_whisper}' to a known code. Using original value.")
                    language_to_process = detected_by_whisper

            logger.info(f"Language pre-determined for processing: {language_to_process}")

            if language_to_process == 'km' and self.google_stt_service:
                logger.info("Khmer language detected. Forcing conversion to WAV for Google STT.")
                converted_wav_path = self.audio_processor.convert_to_wav(audio_path)
                if not converted_wav_path:
                    raise Exception("Failed to convert audio to WAV for Google STT")

                logger.info("Routing to Google STT with WAV file.")
                text = self.google_stt_service.transcribe_audio(converted_wav_path, language_code='km-KH')
                detected_language = 'km'
            else:
                logger.info(f"Routing to Whisper for language: {language_to_process} with original file.")
                result_dict = self.transcription_service._transcribe_sync(audio_path, language_hint=language_to_process)
                if not result_dict['success']:
                    raise result_dict['error']
                text = result_dict.get('text', '')
                detected_language = result_dict.get('detected_language')

            if not text or not text.strip():
                logger.warning(
                    f"Transcription for language '{detected_language}' resulted in empty text. Treating as failure.")
                return {'success': False, 'error': Exception('Transcription result was empty.')}

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
        finally:
            if converted_wav_path:
                self.audio_processor.cleanup_temp_file(converted_wav_path)

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