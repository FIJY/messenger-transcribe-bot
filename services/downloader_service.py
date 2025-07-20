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

        # Создаем временный файл, в который yt-dlp будет напрямую скачивать аудио.
        # Мы не указываем расширение, yt-dlp добавит его сам.
        temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix='.tmp')
        temp_audio_path = temp_audio_file.name
        temp_audio_file.close()  # Закрываем файл, чтобы yt-dlp мог в него писать

        ydl_opts = {
            # Указываем, что нужно скачать лучшее аудио и сохранить его в mp3.
            'format': 'bestaudio/best',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
            # Указываем путь для сохранения файла.
            'outtmpl': temp_audio_path,
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
            # Удаляем временный файл перед выходом
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
            return None, 'DOWNLOAD_FAILED'

        try:
            logger.info("Starting download process with yt-dlp...")
            # Теперь yt-dlp делает всю работу: и получает ссылку, и скачивает.
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            # yt-dlp сохранит файл с правильным расширением. Нам нужно найти его.
            # Обычно он просто заменяет .tmp на .mp3
            final_path = temp_audio_path.replace('.tmp', '.mp3')
            if not os.path.exists(final_path):
                # Если файл не найден, ищем его в той же директории
                # (на случай, если yt-dlp сгенерировал другое имя)
                temp_dir = os.path.dirname(temp_audio_path)
                found_files = [f for f in os.listdir(temp_dir) if
                               f.startswith(os.path.basename(temp_audio_path).replace('.tmp', ''))]
                if found_files:
                    final_path = os.path.join(temp_dir, found_files[0])
                else:
                    logger.error("Downloaded file not found after yt-dlp process.")
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
            # Очищаем временный .tmp файл, если он остался
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)

