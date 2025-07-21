# services/youtube_service.py
import logging
import tempfile
import os
import yt_dlp
from typing import Optional, Dict, Tuple

logger = logging.getLogger(__name__)


class YouTubeService:
    def __init__(self):
        """
        Инициализация сервиса для работы с YouTube.
        """
        # Общие, самые надежные опции вынесены в отдельный метод,
        # чтобы избежать дублирования кода.
        pass

    def _get_enhanced_ydl_options(self) -> Dict:
        """
        Возвращает словарь с расширенными опциями для yt-dlp,
        включая прокси и заголовки для обхода блокировок.
        """
        opts = {
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'nocheckcertificate': True,
            'socket_timeout': 60,
            'retries': 5,
            'fragment_retries': 5,
            'extractor_retries': 5,
            'extractor_args': {
                'youtube': {
                    'player_client': ['ios', 'android', 'web'],
                    'player_skip': ['webpage', 'configs'],
                    'skip': ['dash', 'hls'],
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1',
                'Accept-Language': 'en-US,en;q=0.9',
            }
        }

        proxy_url = os.getenv('YT_DLP_PROXY')
        if proxy_url:
            opts['proxy'] = proxy_url
        else:
            # Эта проверка осталась, но теперь она не будет прерывать работу
            logger.warning("YT_DLP_PROXY is not set. YouTube downloads may fail.")

        return opts

    def get_info(self, url: str) -> Optional[Dict]:
        """
        Извлекает информацию о видео, не скачивая его,
        используя расширенные опции для обхода блокировок.
        """
        logger.info(f"Извлекаем информацию для URL (с расширенными опциями): {url}")
        ydl_opts = self._get_enhanced_ydl_options()
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            return info
        except Exception as e:
            logger.error(f"Не удалось извлечь информацию для {url}: {e}")
            return None

    def download_subtitles(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Скачивает готовые субтитры (если есть) в формате .srt."""
        temp_srt_file = None
        try:
            temp_srt_file = tempfile.NamedTemporaryFile(delete=False, suffix=".srt", mode='w', encoding='utf-8')
            temp_srt_path = temp_srt_file.name
            temp_srt_file.close()

            ydl_opts = self._get_enhanced_ydl_options()
            ydl_opts.update({
                'writesubtitles': True,
                'subtitleslangs': ['en', 'ru'],
                'skip_download': True,
                'outtmpl': temp_srt_path.replace('.srt', ''),
            })

            logger.info(f"Начинаем скачивание субтитров с YouTube: {url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info.get('requested_subtitles'):
                    logger.warning(f"Для видео {url} не найдены подходящие субтитры.")
                    if os.path.exists(temp_srt_path): os.remove(temp_srt_path)
                    return None, "NO_SUBTITLES"

            final_srt_path = None
            # yt-dlp может добавить язык к имени файла, например, 'filename.en.srt'
            base_path = os.path.dirname(temp_srt_path)
            base_name = os.path.basename(temp_srt_path).replace('.srt', '')
            for file in os.listdir(base_path):
                if file.startswith(base_name) and file.endswith('.srt'):
                    final_srt_path = os.path.join(base_path, file)
                    break

            if final_srt_path and os.path.exists(final_srt_path):
                return final_srt_path, None
            else:
                return None, "NO_SUBTITLES"

        except Exception as e:
            logger.error(f"Ошибка при скачивании субтитров из {url}: {e}")
            if temp_srt_file and os.path.exists(temp_srt_file.name):
                try:
                    os.remove(temp_srt_file.name)
                except OSError:
                    pass
            return None, 'GENERAL_ERROR'

