# services/downloader_service.py
import os
import requests
import tempfile
import logging
from typing import Tuple, Optional
import yt_dlp

logger = logging.getLogger(__name__)


class DownloaderService:
    def __init__(self):
        """
        Инициализация сервиса загрузки.
        Использует yt-dlp с поддержкой прокси для максимальной надежности.
        """
        logger.info("DownloaderService initialized with full proxy support for yt-dlp.")

    def download_audio(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Скачивает аудио с YouTube, используя прокси-сервер для обхода блокировок.
        """
        logger.info(f"Starting audio download for URL: {url}")

        ydl_opts = {
            # ИЗМЕНЕНИЕ: Упрощаем запрос формата, чтобы он был более гибким.
            # Теперь yt-dlp будет сам выбирать лучший доступный аудио-формат.
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'nocheckcertificate': True,
            'socket_timeout': 60,
        }

        # Добавляем поддержку прокси из переменных окружения.
        proxy_url = os.getenv('YT_DLP_PROXY')
        if proxy_url:
            logger.info(f"Using proxy for yt-dlp...")
            ydl_opts['proxy'] = proxy_url
        else:
            logger.error("YT_DLP_PROXY is not set. YouTube downloads will fail.")
            return None, 'DOWNLOAD_FAILED'

        try:
            # Шаг 1: Извлекаем информацию о видео через прокси.
            logger.info("Step 1: Extracting video info with yt-dlp...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            logger.info("Step 1: Successfully extracted video info.")

            stream_url = info.get('url')

            if not stream_url:
                logger.error(f"Could not find a valid audio stream URL for {url}")
                return None, 'DOWNLOAD_FAILED'

            logger.info(f"Successfully extracted audio stream URL.")

            # Шаг 2: Скачиваем аудио по прямой ссылке, также через прокси.
            logger.info("Step 2: Downloading audio stream with requests...")
            file_extension = f".{info.get('ext', 'mp3')}"
            temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)

            proxies = {'http': proxy_url, 'https': proxy_url} if proxy_url else None

            with requests.get(stream_url, stream=True, timeout=120, proxies=proxies) as r:
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=8192):
                    temp_audio_file.write(chunk)

            temp_audio_file.close()
            logger.info(f"Step 2: Audio successfully downloaded to: {temp_audio_file.name}")
            return temp_audio_file.name, None

        except yt_dlp.utils.DownloadError as e:
            error_str = str(e).lower()
            logger.error(f"yt-dlp info extraction failed for {url}: {e}")
            if 'login required' in error_str or 'sign in to confirm' in error_str or 'age-restricted' in error_str:
                return None, 'LOGIN_REQUIRED'
            return None, 'DOWNLOAD_FAILED'
        except Exception as e:
            logger.error(f"General error during audio download: {e}", exc_info=True)
            return None, 'GENERAL_ERROR'
