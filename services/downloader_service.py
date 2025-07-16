# services/downloader_service.py
import os
import yt_dlp
import tempfile
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


class DownloaderService:
    def download_audio(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Скачивает аудио по URL.
        Возвращает кортеж (путь_к_файлу, тип_ошибки).
        В случае успеха тип_ошибки будет None.
        """
        temp_audio_file = None
        try:
            temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            temp_audio_path = temp_audio_file.name
            temp_audio_file.close()

            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': temp_audio_path,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
                'nocheckcertificate': True,
            }

            logger.info(f"Начинаем скачивание аудио по ссылке: {url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            logger.info(f"Аудио успешно скачано и сохранено в: {temp_audio_path}")
            return temp_audio_path, None

        except yt_dlp.utils.DownloadError as e:
            logger.error(f"yt-dlp download error for {url}: {e}")
            if temp_audio_file and os.path.exists(temp_audio_file.name):
                os.remove(temp_audio_file.name)

            if 'Sign in to confirm' in str(e) or 'age-restricted' in str(e):
                return None, 'YOUTUBE_AUTH'
            return None, 'DOWNLOAD_FAILED'

        except Exception as e:
            logger.error(f"Ошибка при скачивании аудио из {url}: {e}", exc_info=True)
            if temp_audio_file and os.path.exists(temp_audio_file.name):
                os.remove(temp_audio_file.name)
            return None, 'GENERAL_ERROR'