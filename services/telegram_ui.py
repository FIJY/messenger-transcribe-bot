# services/downloader_service.py
import os
import yt_dlp
import instaloader
import tempfile
import logging
from typing import Tuple, Optional
import subprocess

logger = logging.getLogger(__name__)


class DownloaderService:
    def __init__(self):
        self.L = instaloader.Instaloader()

    def _download_with_yt_dlp(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Скачивает аудио с помощью yt-dlp."""
        temp_audio_file = None
        try:
            temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            temp_audio_path = temp_audio_file.name
            temp_audio_file.close()

            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': temp_audio_path,
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
                'quiet': True, 'no_warnings': True, 'noplaylist': True, 'nocheckcertificate': True,
            }

            logger.info(f"Начинаем скачивание (yt-dlp) по ссылке: {url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            return temp_audio_path, None
        except yt_dlp.utils.DownloadError as e:
            logger.error(f"yt-dlp download error for {url}: {e}")
            if temp_audio_file and os.path.exists(temp_audio_file.name): os.remove(temp_audio_file.name)
            if 'login required' in str(e) or 'sign in to confirm' in str(e) or 'age-restricted' in str(e):
                return None, 'LOGIN_REQUIRED'
            return None, 'DOWNLOAD_FAILED'
        except Exception as e:
            logger.error(f"Общая ошибка при скачивании (yt-dlp) из {url}: {e}", exc_info=True)
            if temp_audio_file and os.path.exists(temp_audio_file.name): os.remove(temp_audio_file.name)
            return None, 'GENERAL_ERROR'

    def _download_with_instaloader(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Скачивает видео/аудио из Instagram и конвертирует в mp3."""
        video_temp_file = None
        audio_temp_file = None
        try:
            logger.info(f"Начинаем скачивание (instaloader) по ссылке: {url}")
            shortcode = url.split("/reel/")[1].split("/")[0]
            post = instaloader.Post.from_shortcode(self.L.context, shortcode)

            if not post.is_video:
                return None, 'NOT_A_VIDEO'

            video_temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            self.L.download_post(post, target=os.path.dirname(video_temp_file.name))
            # instaloader сохраняет файл с именем YYYY-MM-DD_HH-MM-SS_UTC.mp4, нужно его найти
            downloaded_video_path = None
            for f in os.listdir(os.path.dirname(video_temp_file.name)):
                if f.endswith('.mp4'):
                    downloaded_video_path = os.path.join(os.path.dirname(video_temp_file.name), f)
                    break

            if not downloaded_video_path:
                raise Exception("Не удалось найти скачанный файл Instagram")

            # Конвертируем видео в аудио
            audio_temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            command = ['ffmpeg', '-i', downloaded_video_path, '-vn', '-q:a', '0', '-y', audio_temp_file.name]
            subprocess.run(command, check=True, capture_output=True)

            os.remove(downloaded_video_path)  # Удаляем исходное видео
            return audio_temp_file.name, None

        except Exception as e:
            logger.error(f"Ошибка при скачивании (instaloader) из {url}: {e}", exc_info=True)
            if video_temp_file and os.path.exists(video_temp_file.name): os.remove(video_temp_file.name)
            if audio_temp_file and os.path.exists(audio_temp_file.name): os.remove(audio_temp_file.name)
            return None, 'LOGIN_REQUIRED'  # Ошибки инстаграма чаще всего связаны с доступом

    def download_audio(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        if "instagram.com/reel/" in url:
            return self._download_with_instaloader(url)
        else:
            return self._download_with_yt_dlp(url)