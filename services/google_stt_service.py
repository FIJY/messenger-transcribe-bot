# services/google_stt_service.py
import logging
import os
from google.cloud import speech

logger = logging.getLogger(__name__)


class GoogleSTTService:
    def __init__(self):
        try:
            self.client = speech.SpeechClient()
            logger.info("Google Speech-to-Text client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Google STT client: {e}", exc_info=True)
            raise

    def transcribe_audio(self, audio_file_path: str, language_code: str = "km-KH") -> dict:
        """
        Transcribes an audio file and returns a dictionary with the main transcript,
        confidence score, and alternatives.
        """
        logger.info(f"Sending audio to Google STT with language code: {language_code}")
        result = {
            'transcript': "",
            'confidence': 0.0,
            'alternatives': []
        }
        try:
            with open(audio_file_path, "rb") as audio_file:
                content = audio_file.read()

            audio = speech.RecognitionAudio(content=content)
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                language_code=language_code,
                enable_automatic_punctuation=True,
                # ===> ИЗМЕНЕНИЕ: Запрашиваем альтернативы <===
                max_alternatives=3,
            )

            response = self.client.recognize(config=config, audio=audio)

            if response.results:
                # Берем список всех альтернатив для первого результата
                alternatives = response.results[0].alternatives

                # Основной результат - первый в списке
                main_alternative = alternatives[0]
                result['transcript'] = main_alternative.transcript
                result['confidence'] = main_alternative.confidence

                # Собираем тексты остальных альтернатив
                result['alternatives'] = [alt.transcript for alt in alternatives]

                logger.info(f"Google STT transcription successful. Confidence: {result['confidence']:.2f}")
            else:
                logger.warning("Google STT returned no results.")

            return result

        except Exception as e:
            logger.error(f"Error during Google STT transcription: {e}", exc_info=True)
            return result  # Возвращаем пустой result в случае ошибки