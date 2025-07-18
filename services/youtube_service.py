# services/youtube_service.py
import logging
import tempfile
import os
import yt_dlp
from typing import Optional, Dict, Tuple

logger = logging.getLogger(__name__)


class YouTubeService:
    def __init__(self):
        self.base_options = {
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'nocheckcertificate': True,
        }

    def get_info(self, url: str) -> Optional[Dict]:
        """Извлекает информацию о видео, не скачивая его."""
        try:
            logger.info(f"Извлекаем информацию для URL: {url}")
            with yt_dlp.YoutubeDL(self.base_options) as ydl:
                info = ydl.extract_info(url, download=False)
            return info
        except Exception as e:
            logger.error(f"Не удалось извлечь информацию для {url}: {e}")
            return None

    def download_audio(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Скачивает аудио из видео и сохраняет во временный mp3-файл."""
        temp_audio_file = None
        try:
            temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            temp_audio_path = temp_audio_file.name
            temp_audio_file.close()

            ydl_opts = {
                **self.base_options,
                'format': 'bestaudio/best',
                'outtmpl': temp_audio_path,
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
            }

            logger.info(f"Начинаем скачивание аудио с YouTube: {url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            return temp_audio_path, None
        except yt_dlp.utils.DownloadError as e:
            logger.error(f"yt-dlp ошибка скачивания аудио для {url}: {e}")
            if temp_audio_file and os.path.exists(temp_audio_file.name): os.remove(temp_audio_file.name)
            if 'login required' in str(e) or 'sign in to confirm' in str(e) or 'age-restricted' in str(e):
                return None, 'LOGIN_REQUIRED'
            return None, 'DOWNLOAD_FAILED'
        except Exception as e:
            logger.error(f"Общая ошибка при скачивании аудио из {url}: {e}")
            if temp_audio_file and os.path.exists(temp_audio_file.name): os.remove(temp_audio_file.name)
            return None, 'GENERAL_ERROR'

    def download_subtitles(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Скачивает готовые субтитры (если есть) в формате .srt."""
        temp_srt_file = None
        try:
            temp_srt_file = tempfile.NamedTemporaryFile(delete=False, suffix=".srt", mode='w', encoding='utf-8')
            temp_srt_path = temp_srt_file.name
            temp_srt_file.close()

            ydl_opts = {
                **self.base_options,
                'writesubtitles': True,
                'subtitleslangs': ['en', 'ru'],  # Скачиваем английские или русские субтитры
                'skip_download': True,  # Не скачиваем само видео
                'outtmpl': temp_srt_path.replace('.srt', ''),  # yt-dlp сам добавит расширение
            }

            logger.info(f"Начинаем скачивание субтитров с YouTube: {url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # Проверяем, были ли субтитры реально скачаны
                if not info.get('requested_subtitles'):
                    logger.warning(f"Для видео {url} не найдены подходящие субтитры.")
                    os.remove(temp_srt_path)
                    return None, "NO_SUBTITLES"

            # yt-dlp может создавать несколько файлов, нам нужен только .srt
            final_srt_path = None
            for file in os.listdir(os.path.dirname(temp_srt_path)):
                if file.endswith('.srt'):
                    final_srt_path = os.path.join(os.path.dirname(temp_srt_path), file)
                    break

            if final_srt_path:
                return final_srt_path, None
            else:
                return None, "NO_SUBTITLES"

        except Exception as e:
            logger.error(f"Ошибка при скачивании субтитров из {url}: {e}")
            if temp_srt_file and os.path.exists(temp_srt_file.name): os.remove(temp_srt_file.name)
            return None, 'GENERAL_ERROR'