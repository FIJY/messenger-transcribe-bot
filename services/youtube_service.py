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
        logger.info("YouTubeService initialized with resilient settings.")

    def _get_ydl_options(self) -> dict:
        """
        Собирает опции для yt-dlp, нацеленные на отказоустойчивое скачивание через прокси.
        """
        opts = {
            'quiet': True,
            'no_warnings': True,
            'forceipv4': True,
            'noplaylist': True,
            'nocheckcertificate': True,
            'socket_timeout': 15,  # Уменьшаем таймаут, чтобы быстрее отбрасывать плохие IP
            'retries': 2,  # ИЗМЕНЕНИЕ: Уменьшаем кол-во попыток, чтобы не ждать слишком долго при проблемах с прокси
            'cachedir': False,
        }
        # ВАЖНО: Эта функция не добавляет прокси. Прокси добавляется в вызывающем методе.
        return opts

    def get_info(self, url: str) -> Optional[Dict]:
        """
        Извлекает информацию о видео, используя отказоустойчивые настройки и только прокси.
        """
        logger.info(f"Извлекаем информацию для URL (с отказоустойчивыми настройками): {url}")

        ydl_opts = self._get_ydl_options()

        proxy_url = os.getenv('YT_DLP_PROXY')
        if not proxy_url:
            logger.error("YT_DLP_PROXY environment variable is not set. Cannot get video info.")
            return None

        ydl_opts['proxy'] = proxy_url

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            return info
        except Exception as e:
            # ИЗМЕНЕНИЕ: Добавляем более конкретное сообщение об ошибке
            error_message = str(e)
            logger.error(f"Не удалось извлечь информацию для {url}: {error_message}")
            if 'timed out' in error_message or 'ConnectTimeoutError' in error_message:
                logger.error(
                    "ОШИБКА: Тайм-аут при подключении к прокси-серверу. Проверьте настройки вашего прокси или выберите другой регион.")
            return None

    def download_subtitles(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Скачивает готовые субтитры (если есть) в формате .srt.
        """
        temp_srt_file = None
        try:
            temp_srt_file = tempfile.NamedTemporaryFile(delete=False, suffix=".srt", mode='w', encoding='utf-8')
            temp_srt_path = temp_srt_file.name
            temp_srt_file.close()

            # Используем те же отказоустойчивые настройки
            ydl_opts = self._get_ydl_options()
            ydl_opts.update({
                'writesubtitles': True,
                'subtitleslangs': ['en', 'ru'],
                'skip_download': True,
                'outtmpl': temp_srt_path.replace('.srt', ''),
            })

            proxy_url = os.getenv('YT_DLP_PROXY')
            if not proxy_url:
                logger.error("YT_DLP_PROXY environment variable is not set. Cannot download subtitles.")
                return None, "PROXY_NOT_CONFIGURED"

            ydl_opts['proxy'] = proxy_url

            logger.info(f"Начинаем скачивание субтитров с YouTube: {url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info.get('requested_subtitles'):
                    logger.warning(f"Для видео {url} не найдены подходящие субтитры.")
                    if os.path.exists(temp_srt_path): os.remove(temp_srt_path)
                    return None, "NO_SUBTITLES"

            final_srt_path = None
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
            # ИЗМЕНЕНИЕ: Добавляем более конкретное сообщение об ошибке
            error_message = str(e)
            logger.error(f"Ошибка при скачивании субтитров из {url}: {error_message}")
            if 'timed out' in error_message or 'ConnectTimeoutError' in error_message:
                logger.error(
                    "ОШИБКА: Тайм-аут при подключении к прокси-серверу. Проверьте настройки вашего прокси или выберите другой регион.")
            if temp_srt_file and os.path.exists(temp_srt_file.name):
                try:
                    os.remove(temp_srt_file.name)
                except OSError:
                    pass
            return None, 'GENERAL_ERROR'
