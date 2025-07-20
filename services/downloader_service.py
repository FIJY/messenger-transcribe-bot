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
        Скачивает аудио с YouTube, используя продвинутые методы для обхода блокировок,
        найденные в open-source проектах.
        """
        logger.info(f"Starting audio download for URL: {url}")

        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            # ИЗМЕНЕНИЕ: Используем самый надежный метод, найденный на GitHub.
            # Принудительно используем клиент 'ANDROID' для доступа к внутреннему API '/youtubei/v1/player',
            # который менее подвержен блокировкам на серверах.
            'extractor_args': {
                'youtube': {
                    'player_client': ['ANDROID'],
                    'client': ['ANDROID'],
                }
            },
            # Добавляем User-Agent от мобильного клиента для полной маскировки.
            'http_headers': {
                'User-Agent': 'com.google.android.youtube/19.09.37 (Linux; U; Android 12; en_US) gzip',
            }
        }

        try:
            # Шаг 1: Извлекаем информацию о видео, включая прямые ссылки.
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            # Шаг 2: Находим наилучший аудио-формат из списка доступных.
            # Формат m4a часто бывает наилучшего качества.
            stream_url = info.get('url')

            if not stream_url:
                logger.error(f"Could not find a valid audio stream URL for {url}")
                return None, 'DOWNLOAD_FAILED'

            logger.info(f"Successfully extracted audio stream URL using ANDROID client.")

            # Шаг 3: Скачиваем аудио по прямой ссылке.
            # Используем расширение из полученной информации, по умолчанию .m4a
            file_extension = f".{info.get('ext', 'm4a')}"
            temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)

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
