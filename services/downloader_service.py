# services/downloader_service.py
import os
import tempfile
import logging
from typing import Tuple, Optional
import yt_dlp

logger = logging.getLogger(__name__)


class DownloaderService:
    def __init__(self):
        """
        Инициализация сервиса загрузки.
        """
        logger.info("DownloaderService initialized with simplified configuration.")

    def _get_ydl_options(self) -> dict:
        """
        Собирает и возвращает полный набор опций для yt-dlp.
        Эта версия использует упрощенный набор опций для повышения стабильности.
        """
        opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'forceipv4': True, # Принудительно используем IPv4 для стабильности
            'noplaylist': True,
            'nocheckcertificate': True,
            'socket_timeout': 60,
            'retries': 5,
            'fragment_retries': 5,
            'extractor_retries': 5,
            'cachedir': False,
            # УБРАНЫ АГРЕССИВНЫЕ ОПЦИИ (extractor_args и http_headers)
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
            }],
            'postprocessor_args': [
                '-ar', '16000'
            ],
        }
        proxy_url = os.getenv('YT_DLP_PROXY')
        if proxy_url:
            opts['proxy'] = proxy_url
        return opts

    def download_audio(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Скачивает и конвертирует аудио, используя все известные методы обхода блокировок
        и механизм отката при ошибке прокси.
        """
        logger.info(f"Starting audio download for URL: {url}")

        temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix='.tmp')
        temp_audio_path = temp_audio_file.name
        temp_audio_file.close()

        ydl_opts = self._get_ydl_options()
        ydl_opts['outtmpl'] = temp_audio_path

        final_path = None
        try:
            logger.info("Starting download process with yt-dlp (simplified configuration)...")

            # --- Блок с повторной попыткой без прокси ---
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
            except yt_dlp.utils.DownloadError as e:
                if 'proxy' in str(e).lower() and 'proxy' in ydl_opts:
                    logger.warning(f"Proxy error on audio download: {e}. Retrying without proxy...")
                    del ydl_opts['proxy']
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])
                else:
                    raise e
            # --- Конец блока ---

            final_path = temp_audio_path + '.wav'
            if not os.path.exists(final_path) or os.path.getsize(final_path) == 0:
                logger.error(f"Downloaded file not found or is empty. Expected at: {final_path}")
                # Дополнительно логируем, что находится в папке, если файл не найден
                files_in_dir = os.listdir(os.path.dirname(final_path))
                logger.error(f"Files found in temp dir: {files_in_dir}")
                return None, 'DOWNLOAD_FAILED'

            logger.info(f"Audio successfully downloaded and converted to: {final_path}")
            return final_path, None

        except yt_dlp.utils.DownloadError as e:
            error_str = str(e).lower()
            logger.error(f"yt-dlp download failed for {url}: {e}")

            if 'login required' in error_str or 'sign in to confirm' in error_str:
                return None, 'LOGIN_REQUIRED'
            elif 'age-restricted' in error_str:
                return None, 'AGE_RESTRICTED'
            elif 'private video' in error_str:
                return None, 'PRIVATE_VIDEO'
            elif 'video unavailable' in error_str:
                return None, 'VIDEO_UNAVAILABLE'
            elif 'player response' in error_str:
                return None, 'PLAYER_RESPONSE_ERROR'
            else:
                return None, 'DOWNLOAD_FAILED'

        except Exception as e:
            logger.error(f"General error during audio download: {e}", exc_info=True)
            return None, 'GENERAL_ERROR'

        finally:
            if os.path.exists(temp_audio_path):
                try:
                    os.remove(temp_audio_path)
                except OSError:
                    pass
