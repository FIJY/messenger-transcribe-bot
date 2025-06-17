import os
import tempfile
import logging
import requests
from config.constants import MAX_FILE_SIZE, MAX_AUDIO_DURATION_FREE, MAX_AUDIO_DURATION_PREMIUM

logger = logging.getLogger(__name__)


class AudioProcessor:
    """Базовый класс для обработки аудио/видео файлов"""

    def __init__(self):
        self.max_file_size = MAX_FILE_SIZE

    def download_media(self, media_url):
        """
        Скачивание медиа файла по URL

        Args:
            media_url: URL медиа файла

        Returns:
            bytes: Содержимое файла или None при ошибке
        """
        try:
            response = requests.get(media_url, timeout=30)
            response.raise_for_status()

            file_data = response.content
            logger.info(f"Downloaded media file: {len(file_data)} bytes")

            return file_data

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download media: {str(e)}")
            return None

    def validate_media(self, file_data, media_type='audio', user_subscription='free'):
        """
        Валидация медиа файла

        Args:
            file_data: Содержимое файла
            media_type: Тип медиа ('audio' или 'video')
            user_subscription: Тип подписки пользователя

        Returns:
            dict: Результат валидации
        """
        # Проверка размера
        file_size = len(file_data)
        if file_size > self.max_file_size:
            return {
                'is_valid': False,
                'error': f'File too large. Maximum size: {self.max_file_size // (1024 * 1024)}MB'
            }

        if file_size < 1000:  # Минимум 1KB
            return {
                'is_valid': False,
                'error': 'File too small or corrupted'
            }

        # Приблизительная оценка длительности
        # Аудио: ~1MB = 1 минута, Видео: ~5MB = 1 минута
        bytes_per_minute = 1024 * 1024 if media_type == 'audio' else 5 * 1024 * 1024
        estimated_duration = (file_size / bytes_per_minute) * 60  # в секундах

        # Проверка лимитов длительности
        max_duration = MAX_AUDIO_DURATION_FREE if user_subscription == 'free' else MAX_AUDIO_DURATION_PREMIUM

        if estimated_duration > max_duration:
            max_minutes = max_duration // 60
            return {
                'is_valid': False,
                'error': f'Media too long. Maximum duration: {max_minutes} minutes for {user_subscription} users'
            }

        logger.info(f"Media file validated: {file_size} bytes, ~{int(estimated_duration)}s")

        return {
            'is_valid': True,
            'file_size': file_size,
            'estimated_duration': int(estimated_duration)
        }

    def save_temp_file(self, file_data, extension='mp3'):
        """
        Сохранение данных во временный файл

        Args:
            file_data: Содержимое файла
            extension: Расширение файла

        Returns:
            str: Путь к временному файлу
        """
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{extension}') as tmp_file:
                tmp_file.write(file_data)
                temp_path = tmp_file.name

            logger.info(f"Created temp file: {temp_path}")
            return temp_path

        except Exception as e:
            logger.error(f"Failed to create temp file: {str(e)}")
            return None

    def cleanup_temp_file(self, file_path):
        """
        Удаление временного файла

        Args:
            file_path: Путь к файлу
        """
        try:
            if file_path and os.path.exists(file_path):
                os.unlink(file_path)
                logger.info(f"Cleaned up temp file: {file_path}")
        except Exception as e:
            logger.error(f"Failed to cleanup temp file: {str(e)}")

    def estimate_duration_from_size(self, file_size, media_type='audio'):
        """
        Оценка длительности по размеру файла

        Args:
            file_size: Размер файла в байтах
            media_type: Тип медиа

        Returns:
            int: Приблизительная длительность в секундах
        """
        # Приблизительные битрейты
        # Аудио: 128 kbps, Видео: 500 kbps
        bitrate = 128 * 1024 / 8 if media_type == 'audio' else 500 * 1024 / 8
        duration = file_size / bitrate

        return int(duration)