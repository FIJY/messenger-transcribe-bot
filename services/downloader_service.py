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
        Использует yt-dlp с расширенной конфигурацией и поддержкой прокси.
        """
        logger.info("DownloaderService initialized with enhanced configuration.")

    def download_audio(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Скачивает и конвертирует аудио с YouTube, используя все известные методы обхода блокировок.
        """
        logger.info(f"Starting audio download for URL: {url}")

        # Создаем временный файл без расширения. yt-dlp добавит .wav после конвертации.
        temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix='.tmp')
        temp_audio_path = temp_audio_file.name
        temp_audio_file.close()

        # Расширенная конфигурация для максимальной надежности
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': temp_audio_path,  # Сохраняем во временный файл без расширения
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'nocheckcertificate': True,
            'socket_timeout': 60,
            'retries': 5,  # Больше попыток
            'fragment_retries': 5,
            'extractor_retries': 5,

            # Конвертируем аудио в WAV 16kHz - идеальный формат для Whisper
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '16000',
            }],

            # Самые продвинутые аргументы для обхода блокировок
            'extractor_args': {
                'youtube': {
                    'player_client': ['ios', 'android', 'web'],
                    'player_skip': ['webpage', 'configs'],
                    'skip': ['dash', 'hls'],
                }
            },

            # Детальные HTTP заголовки для имитации iPhone
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1',
                'Accept-Language': 'en-US,en;q=0.9',
            }
        }

        proxy_url = os.getenv('YT_DLP_PROXY')
        if proxy_url:
            logger.info(f"Using proxy for yt-dlp...")
            ydl_opts['proxy'] = proxy_url
        else:
            logger.warning("YT_DLP_PROXY is not set. This may cause download failures.")

        try:
            logger.info("Starting download process with yt-dlp (enhanced configuration)...")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            # yt-dlp должен был создать файл .wav
            final_path = temp_audio_path + '.wav'

            if not os.path.exists(final_path):
                logger.error(f"Downloaded file not found. Expected at: {final_path}")
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
            # Очищаем временный .tmp файл, если он остался
            if os.path.exists(temp_audio_path):
                try:
                    os.remove(temp_audio_path)
                except OSError:
                    pass

