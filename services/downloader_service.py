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
        Скачивает аудио с YouTube, используя yt-dlp для всего процесса,
        чтобы обеспечить максимальную надежность при работе через прокси.
        """
        logger.info(f"Starting audio download for URL: {url}")

        temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix='.tmp')
        temp_audio_path = temp_audio_file.name
        temp_audio_file.close()

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{temp_audio_path}.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'nocheckcertificate': True,
            'socket_timeout': 60,
            # ФИНАЛЬНАЯ ПОПЫТКА: Добавляем автоматические повторы и имитируем iOS клиент.
            'extractor_retries': 3,  # Попробовать 3 раза, если не получится с первого
            'extractor_args': {
                'youtube': {
                    'player_client': ['IOS', 'ANDROID', 'WEB'],  # Пробуем разные клиенты, начиная с iOS
                }
            },
        }

        proxy_url = os.getenv('YT_DLP_PROXY')
        if proxy_url:
            logger.info(f"Using proxy for yt-dlp...")
            ydl_opts['proxy'] = proxy_url
        else:
            logger.error("YT_DLP_PROXY is not set. YouTube downloads will fail.")
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
            return None, 'DOWNLOAD_FAILED'

        try:
            logger.info("Starting download process with yt-dlp (with retries)...")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                meta = ydl.extract_info(url, download=True)
                final_path = ydl.prepare_filename(meta)

            if not os.path.exists(final_path):
                logger.error(f"Downloaded file not found at expected path: {final_path}")
                return None, 'DOWNLOAD_FAILED'

            logger.info(f"Audio successfully downloaded by yt-dlp to: {final_path}")
            return final_path, None

        except yt_dlp.utils.DownloadError as e:
            error_str = str(e).lower()
            logger.error(f"yt-dlp download failed for {url}: {e}")
            if 'login required' in error_str or 'sign in to confirm' in error_str or 'age-restricted' in error_str:
                return None, 'LOGIN_REQUIRED'
            return None, 'DOWNLOAD_FAILED'
        except Exception as e:
            logger.error(f"General error during audio download: {e}", exc_info=True)
            return None, 'GENERAL_ERROR'
        finally:
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
