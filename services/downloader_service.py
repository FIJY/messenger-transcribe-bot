# services/downloader_service.py
import os
import requests
import tempfile
import logging
from typing import Tuple, Optional
import yt_dlp
import re

logger = logging.getLogger(__name__)


class DownloaderService:
    def __init__(self):
        """
        Инициализация сервиса загрузки.
        Убрана зависимость от RapidAPI, так как он перестал работать.
        """
        logger.info("DownloaderService initialized to use yt-dlp for all downloads.")

    def _download_with_yt_dlp(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Основной метод скачивания аудио с любого поддерживаемого сайта с помощью yt-dlp.
        """
        temp_audio_file = None
        try:
            # Создаем временный файл с правильным расширением .mp3
            temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            temp_audio_path = temp_audio_file.name
            temp_audio_file.close()  # Закрываем файл, чтобы yt-dlp мог в него писать

            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': temp_audio_path,
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
                'nocheckcertificate': True,
                # ИЗМЕНЕНИЕ: Добавляем аргументы, чтобы обойти проверку на бота от YouTube.
                # yt-dlp будет пытаться маскироваться под веб-клиент или клиент Android.
                'extractor_args': {
                    'youtube': {
                        'player_client': ['web', 'android'],
                    }
                }
            }

            logger.info(f"Starting download (yt-dlp) for URL: {url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            logger.info(f"Audio successfully downloaded via yt-dlp to: {temp_audio_path}")
            return temp_audio_path, None

        except yt_dlp.utils.DownloadError as e:
            logger.error(f"yt-dlp download error for {url}: {e}")
            if temp_audio_file and os.path.exists(temp_audio_file.name):
                os.remove(temp_audio_file.name)
            if 'login required' in str(e).lower() or 'sign in to confirm' in str(e).lower() or 'age-restricted' in str(
                    e).lower():
                return None, 'LOGIN_REQUIRED'
            return None, 'DOWNLOAD_FAILED'
        except Exception as e:
            logger.error(f"General error during yt-dlp download from {url}: {e}", exc_info=True)
            if temp_audio_file and os.path.exists(temp_audio_file.name):
                os.remove(temp_audio_file.name)
            return None, 'GENERAL_ERROR'

    def download_audio(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Главный метод-обертка для скачивания аудио.
        Теперь всегда использует yt-dlp.
        """
        return self._download_with_yt_dlp(url)
