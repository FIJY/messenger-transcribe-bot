# services/google_stt_service.py
import logging
import os
from google.cloud import speech

logger = logging.getLogger(__name__)

class GoogleSTTService:
    def __init__(self):
        # Библиотека Google автоматически найдет ключ, если установлена
        # переменная окружения GOOGLE_APPLICATION_CREDENTIALS.
        try:
            self.client = speech.SpeechClient()
            logger.info("Google Speech-to-Text client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Google STT client: {e}", exc_info=True)
            # Если мы не смогли инициализировать клиент, дальнейшая работа невозможна.
            # Лучше всего "упасть" здесь, чтобы сразу увидеть проблему в логах.
            raise

    def transcribe_audio(self, audio_file_path: str, language_code: str = "km-KH") -> str:
        """
        Transcribes an audio file using Google Cloud Speech-to-Text.
        :param audio_file_path: Path to the local audio file.
        :param language_code: BCP-47 language code (e.g., 'km-KH' for Khmer).
        :return: The transcribed text.
        """
        logger.info(f"Sending audio to Google STT with language code: {language_code}")
        try:
            with open(audio_file_path, "rb") as audio_file:
                content = audio_file.read()

            audio = speech.RecognitionAudio(content=content)
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                language_code=language_code,
                # Включаем автоматическую пунктуацию для лучшего результата
                enable_automatic_punctuation=True,
            )

            response = self.client.recognize(config=config, audio=audio)

            if response.results:
                transcript = response.results[0].alternatives[0].transcript
                logger.info(f"Google STT transcription successful. Transcript length: {len(transcript)}")
                return transcript
            else:
                logger.warning("Google STT returned no results.")
                return ""

        except Exception as e:
            logger.error(f"Error during Google STT transcription: {e}", exc_info=True)
            # В случае ошибки возвращаем пустую строку, чтобы не ломать основной процесс.
            return ""