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
        # Инициализируем Instaloader без входа в аккаунт
        self.L = instaloader.Instaloader(
            download_pictures=False,
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False
        )

    def _download_with_yt_dlp(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Скачивает аудио с помощью yt-dlp с улучшенными опциями."""
        temp_audio_file = None
        try:
            temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            temp_audio_path = temp_audio_file.name
            temp_audio_file.close()

            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': temp_audio_path,
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
                'nocheckcertificate': True,
                # ДОБАВЛЕНО: Маскируемся под обычный браузер
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
                }
            }

            logger.info(f"Начинаем скачивание (yt-dlp) по ссылке: {url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            return temp_audio_path, None

        except yt_dlp.utils.DownloadError as e:
            logger.error(f"yt-dlp download error for {url}: {e}")
            if temp_audio_file and os.path.exists(temp_audio_file.name): os.remove(temp_audio_file.name)

            error_string = str(e).lower()
            if 'login required' in error_string or 'sign in to confirm' in error_string or 'age-restricted' in error_string:
                return None, 'LOGIN_REQUIRED'
            return None, 'DOWNLOAD_FAILED'

        except Exception as e:
            logger.error(f"Общая ошибка при скачивании (yt-dlp) из {url}: {e}", exc_info=True)
            if temp_audio_file and os.path.exists(temp_audio_file.name): os.remove(temp_audio_file.name)
            return None, 'GENERAL_ERROR'

    def _download_with_instaloader(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Скачивает видео/аудио из Instagram и конвертирует в mp3."""
        video_temp_dir = None
        try:
            logger.info(f"Начинаем скачивание (instaloader) по ссылке: {url}")
            shortcode = re.search(r"(?:/p/|/reel/)([\w-]+)", url)
            if not shortcode:
                return None, 'INVALID_URL'

            post = instaloader.Post.from_shortcode(self.L.context, shortcode.group(1))

            if not post.is_video:
                return None, 'NOT_A_VIDEO'

            video_temp_dir = tempfile.mkdtemp()
            self.L.download_post(post, target=video_temp_dir)

            downloaded_video_path = None
            for f in os.listdir(video_temp_dir):
                if f.endswith('.mp4'):
                    downloaded_video_path = os.path.join(video_temp_dir, f)
                    break

            if not downloaded_video_path:
                raise Exception("Не удалось найти скачанный файл Instagram")

            audio_temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            audio_path = audio_temp_file.name
            audio_temp_file.close()

            command = ['ffmpeg', '-i', downloaded_video_path, '-vn', '-q:a', '0', '-y', audio_path]
            subprocess.run(command, check=True, capture_output=False)

            return audio_path, None

        except Exception as e:
            logger.error(f"Ошибка при скачивании (instaloader) из {url}: {e}", exc_info=True)
            return None, 'LOGIN_REQUIRED'
        finally:
            if video_temp_dir and os.path.exists(video_temp_dir):
                import shutil
                shutil.rmtree(video_temp_dir)

    def download_audio(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        if "instagram.com/" in url:
            return self._download_with_instaloader(url)
        else:
            return self._download_with_yt_dlp(url)