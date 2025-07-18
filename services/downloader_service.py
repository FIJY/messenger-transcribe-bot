# services/downloader_service.py
import os
import requests
import tempfile
import logging
from typing import Tuple, Optional
import yt_dlp
import instaloader
import re
import subprocess

logger = logging.getLogger(__name__)


class DownloaderService:
    def __init__(self):
        self.rapidapi_key = os.getenv('RAPIDAPI_KEY')
        self.rapidapi_host = 'youtube-downloader6.p.rapidapi.com'
        self.L = instaloader.Instaloader(
            download_pictures=False,
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False
        )
        if not self.rapidapi_key:
            logger.warning("RAPIDAPI_KEY не установлен. Скачивание с YouTube будет отключено.")

    def _download_with_youtube_api(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Скачивает аудио с YouTube через RapidAPI."""
        if not self.rapidapi_key:
            return None, "API_KEY_MISSING"

        api_url = f"https://{self.rapidapi_host}/dl"
        querystring = {"url": url}
        headers = {
            "x-rapidapi-key": self.rapidapi_key,
            "x-rapidapi-host": self.rapidapi_host
        }

        temp_audio_file = None
        try:
            logger.info(f"Отправляем запрос на RapidAPI для YouTube URL: {url}")
            api_response = requests.get(api_url, headers=headers, params=querystring, timeout=60)
            api_response.raise_for_status()

            data = api_response.json()
            # Ищем ссылку на аудио-файл в формате m4a (самый частый для аудио)
            audio_link = None
            if data.get('formats'):
                audio_formats = [f for f in data['formats'] if f.get('mimeType') and 'audio' in f['mimeType']]
                if audio_formats:
                    audio_link = audio_formats[0].get('url')  # Берем первый доступный аудиоформат

            if not audio_link and data.get('link'):
                audio_link = data.get('link')

            if not audio_link:
                logger.error(f"API не вернул ссылку на скачивание аудио для {url}. Ответ: {data}")
                return None, "DOWNLOAD_FAILED"

            logger.info("Получена ссылка, начинаем скачивание...")
            audio_response = requests.get(audio_link, stream=True, timeout=300)
            audio_response.raise_for_status()

            temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            with open(temp_audio_file.name, 'wb') as f:
                for chunk in audio_response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info(f"Аудио с YouTube успешно скачано: {temp_audio_file.name}")
            return temp_audio_file.name, None

        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка сети при обращении к API или скачивании файла: {e}")
            return None, "DOWNLOAD_FAILED"
        except Exception as e:
            logger.error(f"Общая ошибка при скачивании через API из {url}: {e}", exc_info=True)
            if temp_audio_file and os.path.exists(temp_audio_file.name):
                os.remove(temp_audio_file.name)
            return None, 'GENERAL_ERROR'

    def _download_with_yt_dlp(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Скачивает аудио с помощью yt-dlp (для всех остальных сайтов)."""
        temp_audio_file = None
        try:
            temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            temp_audio_path = temp_audio_file.name
            temp_audio_file.close()

            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': temp_audio_path,
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
                'quiet': True, 'no_warnings': True, 'noplaylist': True, 'nocheckcertificate': True
            }

            logger.info(f"Начинаем скачивание (yt-dlp) по ссылке: {url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            return temp_audio_path, None
        except yt_dlp.utils.DownloadError as e:
            logger.error(f"yt-dlp ошибка скачивания для {url}: {e}")
            if temp_audio_file and os.path.exists(temp_audio_file.name): os.remove(temp_audio_file.name)
            if 'login required' in str(e) or 'sign in to confirm' in str(e) or 'age-restricted' in str(e):
                return None, 'LOGIN_REQUIRED'
            return None, 'DOWNLOAD_FAILED'
        except Exception as e:
            logger.error(f"Общая ошибка при скачивании (yt-dlp) из {url}: {e}", exc_info=True)
            if temp_audio_file and os.path.exists(temp_audio_file.name): os.remove(temp_audio_file.name)
            return None, 'GENERAL_ERROR'

    def download_audio(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Главный метод, который решает, какой загрузчик использовать."""
        # Проверяем, является ли ссылка на YouTube
        if re.search(r'(?:youtube\.com|youtu\.be)', url):
            return self._download_with_youtube_api(url)
        else:
            # Для всех остальных ссылок используем yt-dlp
            return self._download_with_yt_dlp(url)