# services/downloader_service.py
import os
import tempfile
import logging
import subprocess
import shutil
from typing import Tuple, Optional

import yt_dlp

logger = logging.getLogger(__name__)


class DownloaderService:
    def __init__(self):
        """
        Инициализация сервиса загрузки.
        """
        logger.info("DownloaderService initialized with a proxy-only, two-step download/convert process.")

    def _get_ydl_options(self, out_template: str) -> dict:
        """
        Собирает опции для yt-dlp, нацеленные ТОЛЬКО на скачивание лучшего аудио.
        """
        opts = {
            'format': 'bestaudio/best',
            'outtmpl': out_template,
            'quiet': True,
            'no_warnings': True,
            'forceipv4': True,
            'noplaylist': True,
            'nocheckcertificate': True,
            'socket_timeout': 60,
            'retries': 5,
            'cachedir': False,
        }
        return opts

    def _convert_to_mp3(self, source_path: str) -> Optional[str]:
        """
        Конвертирует скачанный аудиофайл в MP3 16kHz с помощью ffmpeg.
        """
        if not os.path.exists(source_path) or os.path.getsize(source_path) == 0:
            logger.error(f"Source file for conversion does not exist or is empty: {source_path}")
            return None

        mp3_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        mp3_path = mp3_file.name
        mp3_file.close()

        logger.info(f"Starting conversion: {source_path} -> {mp3_path}")
        command = [
            'ffmpeg', '-y', '-i', source_path,
            '-vn', '-ar', '16000', '-ac', '1',
            '-codec:a', 'libmp3lame', '-q:a', '2', mp3_path
        ]

        try:
            process = subprocess.run(command, check=True, capture_output=True, text=True)
            logger.info("ffmpeg stdout: " + process.stdout)
            logger.error("ffmpeg stderr: " + process.stderr)
            logger.info(f"Successfully converted file to {mp3_path}")
            return mp3_path
        except subprocess.CalledProcessError as e:
            logger.error(f"ffmpeg conversion failed for {source_path}!")
            logger.error("ffmpeg return code: " + str(e.returncode))
            logger.error("ffmpeg stdout: " + e.stdout)
            logger.error("ffmpeg stderr: " + e.stderr)
            if os.path.exists(mp3_path): os.remove(mp3_path)
            return None
        except FileNotFoundError:
            logger.error("ffmpeg not found. Please ensure ffmpeg is installed and in the system's PATH.")
            return None

    def download_audio(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Шаг 1: Скачивает аудиофайл, используя ТОЛЬКО прокси.
        Шаг 2: Конвертирует его в MP3.
        """
        logger.info(f"Starting proxy-only, two-step audio download for URL: {url}")

        temp_dir = tempfile.mkdtemp()
        source_audio_path = None
        final_mp3_path = None

        try:
            out_template = os.path.join(temp_dir, '%(id)s.%(ext)s')
            ydl_opts = self._get_ydl_options(out_template)
            info = None

            # --- НОВАЯ ЛОГИКА: Используем только прокси, без прямых попыток ---
            proxy_url = os.getenv('YT_DLP_PROXY')
            if not proxy_url:
                logger.error("YT_DLP_PROXY environment variable is not set. Cannot proceed.")
                return None, 'PROXY_NOT_CONFIGURED'

            logger.info("Step 1: Downloading audio via proxy...")
            ydl_opts['proxy'] = proxy_url

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
            # --- КОНЕЦ НОВОЙ ЛОГИКИ ---

            if info and 'requested_downloads' in info and info['requested_downloads']:
                source_audio_path = info['requested_downloads'][0].get('filepath')
            else:
                # Резервный метод на случай, если информация о скачанном файле отсутствует
                files_in_dir = os.listdir(temp_dir)
                if files_in_dir:
                    logger.warning("Could not find 'requested_downloads' in info. Using first file found in temp dir.")
                    source_audio_path = os.path.join(temp_dir, files_in_dir[0])
                else:
                    logger.error("Download seemed to succeed, but no file was found in the temp directory.")
                    source_audio_path = None

            if not source_audio_path or not os.path.exists(source_audio_path) or os.path.getsize(
                    source_audio_path) == 0:
                logger.error(f"Download failed: file not found or is empty. Path: {source_audio_path}")
                return None, 'DOWNLOAD_FAILED'

            logger.info(f"Step 1 successful. Downloaded file: {source_audio_path}")

            logger.info("Step 2: Converting to MP3...")
            final_mp3_path = self._convert_to_mp3(source_audio_path)

            if not final_mp3_path:
                logger.error("Conversion to MP3 failed.")
                return None, 'CONVERSION_FAILED'

            logger.info(f"Step 2 successful. Final MP3 path: {final_mp3_path}")
            return final_mp3_path, None

        except yt_dlp.utils.DownloadError as e:
            logger.error(f"yt-dlp download failed for {url}: {e}")
            return None, 'DOWNLOAD_FAILED'
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}", exc_info=True)
            return None, 'GENERAL_ERROR'
        finally:
            # Очищаем временную папку со всеми скачанными файлами
            if os.path.exists(temp_dir):
                logger.info(f"Cleaning up temporary directory: {temp_dir}")
                shutil.rmtree(temp_dir)
