# services/youtube_service.py
import logging
import tempfile
import yt_dlp
from typing import Optional, Dict, Any
import re

logger = logging.getLogger(__name__)


class YouTubeService:
    def __init__(self):
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{tempfile.gettempdir()}/%(id)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'logger': logger,
            'progress_hooks': [self._on_download_progress],
            'max_filesize': 20 * 1024 * 1024,  # Ограничение 20MB
            'noplaylist': True,
            'quiet': True,
        }
        logger.info("YouTubeService initialized.")

    def _on_download_progress(self, d):
        if d['status'] == 'downloading':
            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
            if total_bytes and total_bytes > self.ydl_opts['max_filesize']:
                raise yt_dlp.utils.DownloadError("File size exceeds the 20MB limit.")

    def is_youtube_link(self, text: str) -> bool:
        """Проверяет, является ли текст ссылкой на YouTube."""
        youtube_regex = (
            r'(https?://)?(www\.)?'
            r'(youtube\.com/watch\?v=|youtu\.be/|googleusercontent\.com/youtube\.com/)'
        )
        return bool(re.search(youtube_regex, text))

    def download_audio(self, url: str) -> Dict[str, Any]:
        """
        Скачивает аудио с YouTube, конвертирует в mp3 и возвращает путь и метаданные.
        """
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                logger.info(f"Starting to download audio from YouTube URL: {url}")
                info = ydl.extract_info(url, download=True)
                downloaded_path = ydl.prepare_filename(info).rsplit('.', 1)[0] + '.mp3'

                result = {
                    "local_path": downloaded_path,
                    "title": info.get('title', 'YouTube Video'),
                    "duration": info.get('duration', 0)
                }
                logger.info(f"Successfully downloaded and converted audio: {result}")
                return result
        except yt_dlp.utils.DownloadError as de:
            logger.error(f"YouTube download error for URL {url}: {de}")
            if "File size exceeds" in str(de):
                return {"error": "The video is too large (over 20MB). Please try a shorter video."}
            return {
                "error": "Failed to download this video. It might be private, age-restricted, or otherwise unavailable."}
        except Exception as e:
            logger.error(f"Unexpected error in YouTubeService for URL {url}: {e}", exc_info=True)
            return {"error": "An unexpected error occurred while processing the YouTube link."}