# services/downloader_service.py
import os
import requests
import tempfile
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# ПРИМЕР: Это базовый URL гипотетического сервиса. Вам нужно будет заменить его на реальный.
# Мы будем использовать сервис co.wuk.sh, так как он предоставляет простой и бесплатный API.
DOWNLOADER_API_BASE_URL = "https://co.wuk.sh/api/json"


class DownloaderService:
    def __init__(self):
        """
        Инициализация сервиса загрузки.
        Использует внешний API для получения прямых ссылок на аудио.
        """
        logger.info("DownloaderService initialized to use an external download API.")

    def download_audio(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Скачивает аудио с YouTube, получая прямую ссылку через внешний API.
        """
        logger.info(f"Requesting download link from external API for URL: {url}")

        # Параметры для запроса к API co.wuk.sh
        api_payload = {
            "url": url,
            "aFormat": "mp3",  # Запрашиваем формат mp3
            "isAudioOnly": True,
        }

        try:
            # Шаг 1: Обращаемся к внешнему API за ссылкой на скачивание.
            api_response = requests.post(DOWNLOADER_API_BASE_URL, json=api_payload, timeout=60)
            api_response.raise_for_status()

            response_data = api_response.json()

            if response_data.get("status") != "success":
                error_message = response_data.get("text", "Unknown API error")
                logger.error(f"External API returned an error: {error_message}")
                if "age restricted" in error_message.lower():
                    return None, 'LOGIN_REQUIRED'
                return None, 'DOWNLOAD_FAILED'

            stream_url = response_data.get("url")
            if not stream_url:
                logger.error("External API did not return a stream URL.")
                return None, 'DOWNLOAD_FAILED'

            logger.info("Successfully retrieved audio stream URL from external API.")

            # Шаг 2: Скачиваем аудио по полученной прямой ссылке.
            temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")

            with requests.get(stream_url, stream=True, timeout=300) as r:
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=8192):
                    temp_audio_file.write(chunk)

            temp_audio_file.close()
            logger.info(f"Audio successfully downloaded to: {temp_audio_file.name}")
            return temp_audio_file.name, None

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to communicate with the external download API: {e}", exc_info=True)
            return None, 'DOWNLOAD_FAILED'
        except Exception as e:
            logger.error(f"General error during audio download via external API: {e}", exc_info=True)
            return None, 'GENERAL_ERROR'
