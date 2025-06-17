import os
import tempfile
import logging
import requests
from config.constants import MAX_FILE_SIZE, MAX_AUDIO_DURATION_FREE, MAX_AUDIO_DURATION_PREMIUM

logger = logging.getLogger(__name__)


class AudioProcessor:
    """Базовый класс для обработки аудио/видео файлов"""

    def __init__(self):
        self.supported_formats = [
            'audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/ogg',
            'audio/m4a', 'audio/aac', 'video/mp4', 'video/mpeg'
        ]

    def download_media(self, url):
        """Скачивание медиа файла"""
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()

            # Проверяем размер до полной загрузки
            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > MAX_FILE_SIZE:
                raise ValueError(f"File too large. Maximum {MAX_FILE_SIZE // (1024 * 1024)}MB allowed.")

            # Загружаем в память
            media_data = response.content

            # Дополнительная проверка размера
            if len(media_data) > MAX_FILE_SIZE:
                raise ValueError(f"File too large. Maximum {MAX_FILE_SIZE // (1024 * 1024)}MB allowed.")

            logger.info(f"Downloaded media file: {len(media_data)} bytes")
            return media_data

        except requests.RequestException as e:
            logger.error(f"Failed to download media: {e}")
            raise ValueError("Failed to download media file")

    def create_temp_file(self, media_data, media_type='audio'):
        """Создание временного файла"""
        try:
            # Определяем расширение
            suffix = '.mp4' if media_type == 'video' else '.mp3'

            # Создаем временный файл
            temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            temp_file.write(media_data)
            temp_file.close()

            logger.info(f"Created temp file: {temp_file.name}")
            return temp_file.name

        except Exception as e:
            logger.error(f"Failed to create temp file: {e}")
            raise ValueError("Failed to create temporary file")

    def cleanup_temp_file(self, file_path):
        """Удаление временного файла"""
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
                logger.info(f"Cleaned up temp file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup temp file {file_path}: {e}")

    def estimate_duration(self, file_size_bytes):
        """Примерная оценка длительности по размеру файла"""
        # Грубая оценка: 1MB ≈ 1 минута для сжатого аудио
        estimated_minutes = file_size_bytes / (1024 * 1024)
        return int(estimated_minutes * 60)  # в секундах

    def check_duration_limits(self, estimated_duration, user_subscription='free'):
        """Проверка лимитов времени"""
        max_duration = (MAX_AUDIO_DURATION_PREMIUM
                        if user_subscription == 'premium'
                        else MAX_AUDIO_DURATION_FREE)

        if estimated_duration > max_duration:
            max_minutes = max_duration // 60
            raise ValueError(
                f"File too long. Maximum {max_minutes} minutes "
                f"allowed for {user_subscription} subscription."
            )

        return True

    def validate_media_file(self, media_data, media_type, user_subscription='free'):
        """Полная валидация медиа файла"""
        # Проверка размера
        if len(media_data) > MAX_FILE_SIZE:
            raise ValueError(f"File too large. Maximum {MAX_FILE_SIZE // (1024 * 1024)}MB allowed.")

        # Проверка длительности
        estimated_duration = self.estimate_duration(len(media_data))
        self.check_duration_limits(estimated_duration, user_subscription)

        logger.info(f"Media file validated: {len(media_data)} bytes, ~{estimated_duration}s")
        return estimated_duration