# services/downloader_service.py
import os
import requests
import tempfile
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# ИЗМЕНЕНИЕ: Используем правильный хост и URL для того API,
# на который вы подписаны (согласно вашему скриншоту).
DOWNLOADER_API_HOST = "youtube-videos-downloader.p.rapidapi.com"
DOWNLOADER_API_URL = f"https://{DOWNLOADER_API_HOST}/download"


class DownloaderService:
    def __init__(self):
        """
        Инициализация сервиса загрузки.
        Использует профессиональный внешний API для получения прямых ссылок на аудио.
        """
        self.rapidapi_key = os.getenv('RAPIDAPI_KEY')
        if not self.rapidapi_key:
            logger.error("RAPIDAPI_KEY is not set. DownloaderService cannot function.")
            raise ValueError("RAPIDAPI_KEY is not set in environment variables.")

        self.headers = {
            "x-rapidapi-key": self.rapidapi_key,
            "x-rapidapi-host": DOWNLOADER_API_HOST
        }
        logger.info("DownloaderService initialized to use the correct RapidAPI endpoint.")

    def download_audio(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Скачивает аудио с YouTube, получая прямую ссылку через внешний API.
        """
        logger.info(f"Requesting download link from RapidAPI for URL: {url}")

        querystring = {"url": url}

        try:
            # Шаг 1: Обращаемся к API за информацией о видео и ссылками.
            api_response = requests.get(DOWNLOADER_API_URL, headers=self.headers, params=querystring, timeout=90)
            api_response.raise_for_status()

            response_data = api_response.json()

            # ИЗМЕНЕНИЕ: Ищем аудиоформат в новой структуре ответа.
            # Нам нужен объект, где 'quality' равно 'Audio'.
            audio_stream = next((item for item in response_data.get("links", []) if item.get("quality") == "Audio"),
                                None)

            if not audio_stream:
                logger.error("RapidAPI response did not contain an 'Audio' quality stream.")
                return None, 'DOWNLOAD_FAILED'

            stream_url = audio_stream.get("link")
            if not stream_url:
                logger.error("RapidAPI audio stream did not contain a 'link'.")
                return None, 'DOWNLOAD_FAILED'

            logger.info("Successfully retrieved audio stream URL from RapidAPI.")

            # Шаг 2: Скачиваем аудио по полученной прямой ссылке.
            # API возвращает mp3, поэтому используем это расширение.
            temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")

            with requests.get(stream_url, stream=True, timeout=300) as r:
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=8192):
                    temp_audio_file.write(chunk)

            temp_audio_file.close()
            logger.info(f"Audio successfully downloaded to: {temp_audio_file.name}")
            return temp_audio_file.name, None

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error from RapidAPI: {e.response.text}")
            return None, 'DOWNLOAD_FAILED'
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to communicate with the RapidAPI: {e}", exc_info=True)
            return None, 'DOWNLOAD_FAILED'
        except Exception as e:
            logger.error(f"General error during audio download via RapidAPI: {e}", exc_info=True)
            return None, 'GENERAL_ERROR'
