# services/downloader_service.py
import os
import yt_dlp
import logging
from pathlib import Path


class DownloaderService:
    def __init__(self, download_dir="downloads"):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(exist_ok=True)

        # Настройка логирования
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def download_audio(self, url):
        """
        Скачивает аудио с YouTube/других сайтов
        Returns: (file_path, error)
        """
        try:
            # Проверяем, что это поддерживаемый URL
            if not self._is_supported_url(url):
                return None, "UNSUPPORTED_URL"

            # Настройки yt-dlp
            # Замените в вашем downloader_service.py:

            ydl_opts = {
                'format': 'worst[ext=mp4]/worst',  # Берем худшее качество (быстрее)
                'outtmpl': str(self.download_dir / '%(title)s.%(ext)s'),
                'extractaudio': True,
                'audioformat': 'mp3',
                'noplaylist': True,
                'quiet': False,  # Включаем логи для отладки
                'no_warnings': False,

                # Антибот настройки:
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                },
                'sleep_interval': 3,  # Пауза 3 секунды между запросами
                'socket_timeout': 30,
                'retries': 2,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Получаем информацию о видео
                self.logger.info(f"Извлекаем информацию: {url}")
                info = ydl.extract_info(url, download=False)

                if not info:
                    return None, "NO_VIDEO_INFO"

                # Формируем имя файла
                safe_title = self._sanitize_filename(info.get('title', 'audio'))
                audio_file = self.download_dir / f"{safe_title}.mp3"

                # Обновляем настройки с конкретным именем файла
                ydl_opts['outtmpl'] = str(audio_file.with_suffix('.%(ext)s'))

                # Скачиваем
                self.logger.info(f"Скачиваем: {info.get('title')}")
                with yt_dlp.YoutubeDL(ydl_opts) as ydl_download:
                    ydl_download.download([url])

                # Проверяем, что файл создался
                possible_files = [
                    audio_file,
                    audio_file.with_suffix('.m4a'),
                    audio_file.with_suffix('.webm'),
                    audio_file.with_suffix('.mp4')
                ]

                for file_path in possible_files:
                    if file_path.exists():
                        self.logger.info(f"✅ Файл сохранен: {file_path}")
                        return str(file_path), None

                return None, "FILE_NOT_FOUND"

        except yt_dlp.DownloadError as e:
            self.logger.error(f"Ошибка скачивания: {e}")
            return None, f"DOWNLOAD_ERROR: {str(e)}"

        except Exception as e:
            self.logger.error(f"Неожиданная ошибка: {e}")
            return None, f"UNEXPECTED_ERROR: {str(e)}"

    def _is_supported_url(self, url):
        """Проверяет, поддерживается ли URL"""
        supported_domains = [
            'youtube.com', 'youtu.be', 'vimeo.com',
            'soundcloud.com', 'twitch.tv'
        ]

        return any(domain in url.lower() for domain in supported_domains)

    def _sanitize_filename(self, filename):
        """Очищает имя файла от недопустимых символов"""
        import re
        # Удаляем/заменяем недопустимые символы
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # Ограничиваем длину
        return filename[:100] if len(filename) > 100 else filename

    def cleanup_old_files(self, max_age_hours=24):
        """Удаляет старые файлы"""
        import time
        current_time = time.time()

        for file_path in self.download_dir.glob('*'):
            if file_path.is_file():
                file_age = current_time - file_path.stat().st_mtime
                if file_age > (max_age_hours * 3600):
                    try:
                        file_path.unlink()
                        self.logger.info(f"Удален старый файл: {file_path}")
                    except Exception as e:
                        self.logger.warning(f"Не удалось удалить {file_path}: {e}")