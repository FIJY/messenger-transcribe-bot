# services/downloader_service.py
import os
import yt_dlp
import tempfile
import logging

logger = logging.getLogger(__name__)


class DownloaderService:
    def download_audio(self, url: str) -> str | None:
        """
        Скачивает аудио по URL (включая YouTube) с помощью yt-dlp и сохраняет во временный mp3-файл.
        Возвращает путь к файлу или None в случае ошибки.
        """
        temp_audio_file = None
        try:
            # Создаем временный файл, в который будем скачивать аудио
            temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            temp_audio_path = temp_audio_file.name
            temp_audio_file.close()

            # Настройки для yt-dlp: скачиваем лучшее аудио и конвертируем в mp3
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': temp_audio_path,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
            }

            logger.info(f"Начинаем скачивание аудио по ссылке: {url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            logger.info(f"Аудио успешно скачано и сохранено в: {temp_audio_path}")
            return temp_audio_path

        except Exception as e:
            logger.error(f"Ошибка при скачивании аудио из {url}: {e}", exc_info=True)
            # Если произошла ошибка, удаляем временный файл, если он был создан
            if temp_audio_file and os.path.exists(temp_audio_file.name):
                os.remove(temp_audio_file.name)
            return None