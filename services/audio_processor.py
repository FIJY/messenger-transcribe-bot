import os
import subprocess
import logging
from typing import Optional
import tempfile

logger = logging.getLogger(__name__)


class AudioProcessor:
    def __init__(self):
        self.supported_audio_formats = ['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac']
        self.supported_video_formats = ['.mp4', '.avi', '.mov', '.mkv', '.webm']

    def process_file(self, file_path: str) -> Optional[str]:
        """
        Обрабатывает медиа файл и возвращает путь к аудио файлу

        Args:
            file_path: путь к исходному файлу

        Returns:
            путь к обработанному аудио файлу или None при ошибке
        """
        if not os.path.exists(file_path):
            logger.error(f"Файл не найден: {file_path}")
            return None

        file_ext = os.path.splitext(file_path)[1].lower()

        # Если это уже аудио файл в поддерживаемом формате
        if file_ext in self.supported_audio_formats:
            logger.info(f"Файл уже в аудио формате: {file_ext}")
            return file_path

        # Если это видео файл, извлекаем аудио
        if file_ext in self.supported_video_formats:
            logger.info(f"Извлекаем аудио из видео файла: {file_ext}")
            return self._extract_audio_from_video(file_path)

        logger.error(f"Неподдерживаемый формат файла: {file_ext}")
        return None

    def _extract_audio_from_video(self, video_path: str) -> Optional[str]:
        """
        Извлекает аудио из видео файла используя ffmpeg

        Args:
            video_path: путь к видео файлу

        Returns:
            путь к извлеченному аудио файлу или None при ошибке
        """
        try:
            # Создаем временный файл для аудио
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_audio:
                audio_path = temp_audio.name

            # Команда ffmpeg для извлечения аудио
            command = [
                'ffmpeg',
                '-i', video_path,
                '-vn',  # Отключаем видео
                '-acodec', 'pcm_s16le',  # Используем несжатый аудио кодек
                '-ar', '16000',  # Частота дискретизации 16kHz (оптимально для Whisper)
                '-ac', '1',  # Моно
                '-y',  # Перезаписываем выходной файл если существует
                audio_path
            ]

            logger.info(f"Выполняем команду: {' '.join(command)}")

            # Выполняем команду
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300  # Таймаут 5 минут
            )

            if result.returncode == 0:
                logger.info(f"Аудио успешно извлечено: {audio_path}")
                return audio_path
            else:
                logger.error(f"Ошибка ffmpeg: {result.stderr}")
                # Удаляем временный файл при ошибке
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                return None

        except subprocess.TimeoutExpired:
            logger.error("Таймаут при извлечении аудио")
            return None
        except FileNotFoundError:
            logger.error("ffmpeg не найден. Убедитесь что ffmpeg установлен в системе")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка при извлечении аудио: {e}")
            return None

    def get_media_duration(self, file_path: str) -> Optional[float]:
        """
        Получает длительность медиа файла в секундах

        Args:
            file_path: путь к медиа файлу

        Returns:
            длительность в секундах или None при ошибке
        """
        try:
            command = [
                'ffprobe',
                '-v', 'quiet',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                file_path
            ]

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                duration_str = result.stdout.strip()
                if duration_str and duration_str != 'N/A':
                    duration = float(duration_str)
                    logger.info(f"Длительность файла {file_path}: {duration:.2f} секунд")
                    return duration

            logger.warning(f"Не удалось определить длительность файла: {file_path}")
            return None

        except (subprocess.TimeoutExpired, ValueError, FileNotFoundError) as e:
            logger.error(f"Ошибка при определении длительности: {e}")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка при определении длительности: {e}")
            return None

    def get_media_info(self, file_path: str) -> dict:
        """
        Получает информацию о медиа файле

        Args:
            file_path: путь к медиа файлу

        Returns:
            словарь с информацией о файле
        """
        info = {
            'file_path': file_path,
            'file_size': 0,
            'duration': None,
            'format': None,
            'has_audio': False,
            'has_video': False
        }

        try:
            # Размер файла
            if os.path.exists(file_path):
                info['file_size'] = os.path.getsize(file_path)

            # Формат файла
            file_ext = os.path.splitext(file_path)[1].lower()
            info['format'] = file_ext

            # Проверяем тип медиа
            info['has_audio'] = file_ext in self.supported_audio_formats
            info['has_video'] = file_ext in self.supported_video_formats

            # Длительность
            info['duration'] = self.get_media_duration(file_path)

            return info

        except Exception as e:
            logger.error(f"Ошибка при получении информации о файле: {e}")
            return info

    def validate_audio_file(self, file_path: str) -> tuple[bool, str]:
        """
        Проверяет, является ли файл валидным аудио/видео файлом

        Args:
            file_path: путь к файлу

        Returns:
            (is_valid, error_message)
        """
        if not os.path.exists(file_path):
            return False, "Файл не найден"

        file_ext = os.path.splitext(file_path)[1].lower()

        if file_ext not in (self.supported_audio_formats + self.supported_video_formats):
            supported_formats = ', '.join(self.supported_audio_formats + self.supported_video_formats)
            return False, f"Неподдерживаемый формат файла. Поддерживаются: {supported_formats}"

        # Проверяем размер файла (максимум 50MB)
        try:
            file_size = os.path.getsize(file_path)
            max_size = 50 * 1024 * 1024  # 50MB

            if file_size > max_size:
                return False, f"Файл слишком большой ({file_size / (1024 * 1024):.1f}MB). Максимум: {max_size / (1024 * 1024)}MB"

            if file_size == 0:
                return False, "Файл пустой"

        except Exception as e:
            return False, f"Ошибка при проверке размера файла: {e}"

        # Проверяем длительность
        duration = self.get_media_duration(file_path)
        if duration:
            max_duration = 3600  # 60 минут максимум
            if duration > max_duration:
                return False, f"Файл слишком длинный ({duration / 60:.1f} мин). Максимум: {max_duration / 60} минут"

        return True, "Файл валиден"

    def cleanup_temp_file(self, file_path: str):
        """
        Удаляет временный файл

        Args:
            file_path: путь к файлу для удаления
        """
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Временный файл удален: {file_path}")
        except Exception as e:
            logger.warning(f"Не удалось удалить временный файл {file_path}: {e}")

    def get_supported_formats(self) -> dict:
        """
        Возвращает список поддерживаемых форматов

        Returns:
            словарь с поддерживаемыми форматами
        """
        return {
            'audio': [fmt.lstrip('.') for fmt in self.supported_audio_formats],
            'video': [fmt.lstrip('.') for fmt in self.supported_video_formats],
            'all': [fmt.lstrip('.') for fmt in (self.supported_audio_formats + self.supported_video_formats)]
        }