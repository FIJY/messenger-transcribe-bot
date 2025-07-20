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
        Использует yt-dlp для извлечения информации и requests для скачивания.
        """
        logger.info("DownloaderService initialized with proxy support.")

    def download_audio(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Скачивает аудио с YouTube, используя продвинутые методы для обхода блокировок.
        """
        logger.info(f"Starting audio download for URL: {url}")

        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'nocheckcertificate': True,
            # ПОСЛЕДНЯЯ ПОПЫТКА: Имитируем клиент Smart TV / встроенного плеера.
            # Этот метод иногда обходит блокировки, когда другие клиенты (web, android) не справляются.
            'extractor_args': {
                'youtube': {
                    'player_client': ['TV_EMBEDDED'],
                    'client': ['TV_EMBEDDED'],
                }
            },
        }

        # Мы оставляем код для прокси. Если и этот метод не сработает,
        # использование прокси останется единственным надежным решением.
        proxy_url = os.getenv('YT_DLP_PROXY')
        if proxy_url:
            logger.info(f"Using proxy for yt-dlp: {proxy_url}")
            ydl_opts['proxy'] = proxy_url
        else:
            logger.warning("YT_DLP_PROXY is not set. YouTube downloads might be blocked.")

        try:
            # Шаг 1: Извлекаем информацию о видео, включая прямые ссылки.
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            stream_url = info.get('url')

            if not stream_url:
                logger.error(f"Could not find a valid audio stream URL for {url}")
                return None, 'DOWNLOAD_FAILED'

            logger.info(f"Successfully extracted audio stream URL using TV_EMBEDDED client.")

            # Шаг 2: Скачиваем аудио по прямой ссылке.
            file_extension = f".{info.get('ext', 'm4a')}"
            temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)

            proxies = {'http': proxy_url, 'https': proxy_url} if proxy_url else None

            with requests.get(stream_url, stream=True, timeout=300, proxies=proxies) as r:
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=8192):
                    temp_audio_file.write(chunk)

            temp_audio_file.close()
            logger.info(f"Audio successfully downloaded to: {temp_audio_file.name}")
            return temp_audio_file.name, None

        except yt_dlp.utils.DownloadError as e:
            error_str = str(e).lower()
            logger.error(f"yt-dlp info extraction failed for {url}: {e}")
            if 'login required' in error_str or 'sign in to confirm' in error_str or 'age-restricted' in error_str:
                return None, 'LOGIN_REQUIRED'
            return None, 'DOWNLOAD_FAILED'
        except Exception as e:
            logger.error(f"General error during audio download from {url}: {e}", exc_info=True)
            return None, 'GENERAL_ERROR'
