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
        logger.info("DownloaderService initialized with new yt-dlp info extraction method.")

    def download_audio(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Скачивает аудио с YouTube, извлекая прямую ссылку через yt-dlp
        и загружая ее с помощью requests.
        """
        logger.info(f"Starting audio download for URL: {url}")

        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'nocheckcertificate': True,
            # Маскируемся под веб-клиент, чтобы обойти проверку на бота
            'extractor_args': {
                'youtube': {
                    'player_client': ['web'],
                }
            }
        }

        try:
            # Шаг 1: Извлекаем информацию о видео, включая прямые ссылки, НЕ скачивая его.
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            # Шаг 2: Находим наилучший аудио-формат из списка доступных.
            audio_format = next((f for f in info['formats'] if f.get('acodec') != 'none' and f.get('vcodec') == 'none'),
                                None)

            # Если нет чистого аудио, берем формат с видео, но лучшим звуком
            if not audio_format:
                audio_format = info

            if not audio_format or not audio_format.get('url'):
                logger.error(f"Could not find a valid audio stream URL for {url}")
                return None, 'DOWNLOAD_FAILED'

            stream_url = audio_format['url']
            logger.info("Successfully extracted audio stream URL.")

            # Шаг 3: Скачиваем аудио по прямой ссылке с помощью простого GET-запроса.
            temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")

            with requests.get(stream_url, stream=True, timeout=300) as r:
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

