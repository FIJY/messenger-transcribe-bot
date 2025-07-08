# services/media_handler.py
import os
import logging
from typing import Optional, Tuple, Dict, Any

from .audio_processor import AudioProcessor
from .transcription_service import TranscriptionService
from .native_script_service import NativeScriptService
from .correction_service import CorrectionService
from .google_stt_service import GoogleSTTService

logger = logging.getLogger(__name__)


class MediaHandler:
    def __init__(self, transcription_service: TranscriptionService, translation_service: Optional[Any] = None):
        self.audio_processor = AudioProcessor()
        self.native_script_service = NativeScriptService()
        self.correction_service = CorrectionService()
        self.transcription_service = transcription_service
        # self.translation_service = translation_service # Больше не используется напрямую
        try:
            self.google_stt_service = GoogleSTTService()
        except Exception as e:
            logger.error(f"Could not initialize GoogleSTTService. Khmer or Irish transcription will fail. Error: {e}")
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
                lang_code, lang_full_name = self.transcription_service.detect_language(audio_path)
                logger.info(f"Language auto-detected as '{lang_full_name}' (code: {lang_code}).")
                language_to_process = lang_code if lang_code != 'unknown' else None

            logger.info(f"Language pre-determined for processing: {language_to_process}")

            confidence = None
            alternatives = None
            text = ""
            detected_language = language_to_process

            if language_to_process in ['km', 'ga'] and self.google_stt_service:
                logger.info(f"Language '{language_to_process}' detected. Routing to Google STT.")
                converted_wav_path = self.audio_processor.convert_to_wav(audio_path)
                if not converted_wav_path:
                    raise Exception(f"Failed to convert audio to WAV for {language_to_process}")

                google_lang_code = 'km-KH' if language_to_process == 'km' else 'ga-IE'

                logger.info(f"Routing to Google STT with WAV file and language code {google_lang_code}.")
                google_result = self.google_stt_service.transcribe_audio(converted_wav_path,
                                                                         language_code=google_lang_code)

                text = google_result.get('transcript')
                confidence = google_result.get('confidence')
                alternatives = google_result.get('alternatives')
            else:
                logger.info(f"Routing to Whisper for language: {language_to_process} with original file.")
                result_dict = self.transcription_service._transcribe_sync(audio_path, language_hint=language_to_process)
                if not result_dict['success']:
                    raise result_dict['error']
                text = result_dict.get('text', '')
                detected_language = result_dict.get('detected_language_code')

            final_audio_path_for_duration = converted_wav_path if converted_wav_path else audio_path
            duration_seconds = self.audio_processor.get_media_duration(final_audio_path_for_duration)
            duration_minutes = (duration_seconds / 60) if duration_seconds else 0.0

            if not text or not text.strip():
                logger.warning(f"Transcription for language '{detected_language}' resulted in empty text.")
                return {'success': False, 'error': Exception('Transcription result was empty.'),
                        'duration_minutes': duration_minutes}

            final_text = text
            if detected_language == 'km':
                processed_text = self.correction_service.post_process_khmer_text(final_text)
                if processed_text: final_text = processed_text

            result = {
                'success': True,
                'transcription': final_text,
                'detected_language': detected_language,
                'language_info': self._get_language_info_safe(detected_language),
                'duration_minutes': duration_minutes,
                'confidence': confidence,
                'alternatives': alternatives,
            }
            return result
        except Exception as e:
            logger.error(f"Critical error in media processing: {e}", exc_info=True)
            return {'success': False, 'error': e}
        finally:
            if converted_wav_path:
                self.audio_processor.cleanup_temp_file(converted_wav_path)

    def _get_language_info_safe(self, detected_language: str) -> Dict[str, str]:
        language_names = {
            'km': {'name': 'Khmer', 'native': 'ខ្មែរ'}, 'en': {'name': 'English', 'native': 'English'},
            'ru': {'name': 'Russian', 'native': 'Русский'}, 'de': {'name': 'German', 'native': 'Deutsch'},
            'ga': {'name': 'Irish', 'native': 'Gaeilge'}, 'es': {'name': 'Spanish', 'native': 'Español'},
            'fr': {'name': 'French', 'native': 'Français'},
        }
        return language_names.get(detected_language, {'name': detected_language.upper(), 'native': ''})

    def validate_file(self, file_path: str, is_premium: bool = False) -> Tuple[bool, str]:
        return self.audio_processor.validate_audio_file(file_path, is_premium)