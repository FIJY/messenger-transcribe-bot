# services/audio_processor.py
import os
import subprocess
import logging
from typing import Optional
import tempfile

logger = logging.getLogger(__name__)


class AudioProcessor:
    def __init__(self):
        self.supported_audio_formats = ['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac', '.oga']
        self.supported_video_formats = ['.mp4', '.avi', 'mov', '.mkv', '.webm']

    def process_file(self, file_path: str) -> Optional[str]:
        if not os.path.exists(file_path):
            logger.error(f"Файл не найден: {file_path}")
            return None

        file_ext = os.path.splitext(file_path)[1].lower()

        if file_ext == '.tmp' and '/tmp/' in file_path:
            logger.info(f"Обрабатываем Facebook .tmp файл как mp4: {file_path}")
            file_ext = '.mp4'

        if file_ext in self.supported_audio_formats:
            logger.info(f"Файл уже в аудио формате: {file_ext}")
            return file_path

        if file_ext in self.supported_video_formats:
            logger.info(f"Извлекаем аудио из видео файла: {file_ext}")
            return self._extract_audio_from_video(file_path)

        logger.error(f"Неподдерживаемый формат файла: {file_ext}")
        return None

    @staticmethod
    def _extract_audio_from_video(video_path: str) -> Optional[str]:
        try:
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_audio:
                audio_path = temp_audio.name

            # ===> ИЗМЕНЕНИЕ: Команда ffmpeg сделана более надежной <===
            command = [
                'ffmpeg', '-i', video_path,
                '-vn',  # Отключить видео
                '-q:a', '0',  # Максимальное качество аудио
                '-map', 'a',  # Выбрать все аудиодорожки
                '-y', audio_path
            ]
            logger.info(f"Выполняем команду: {' '.join(command)}")

            result = subprocess.run(command, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                logger.info(f"Аудио успешно извлечено: {audio_path}")
                return audio_path
            else:
                logger.error(f"Ошибка ffmpeg: {result.stderr}")
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка при извлечении аудио: {e}")
            return None

    @staticmethod
    def cleanup_temp_file(file_path: str):
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Временный файл удален: {file_path}")
        except Exception as e:
            logger.warning(f"Не удалось удалить временный файл {file_path}: {e}")

    def convert_to_wav(self, input_path: str) -> Optional[str]:
        try:
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_audio:
                output_path = temp_audio.name

            command = [
                'ffmpeg', '-i', input_path, '-vn', '-acodec', 'pcm_s16le',
                '-ar', '16000', '-ac', '1', '-y', output_path
            ]
            logger.info(f"Выполняем принудительную конвертацию в WAV: {' '.join(command)}")

            result = subprocess.run(command, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                logger.info(f"Файл успешно сконвертирован в WAV: {output_path}")
                return output_path
            else:
                logger.error(f"Ошибка ffmpeg при конвертации в WAV: {result.stderr}")
                if os.path.exists(output_path):
                    os.remove(output_path)
                return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка при конвертации в WAV: {e}")
            return None

    @staticmethod
    def get_media_duration(file_path: str) -> Optional[float]:
        try:
            command = ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of',
                       'default=noprint_wrappers=1:nokey=1', file_path]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                duration_str = result.stdout.strip()
                if duration_str and duration_str != 'N/A':
                    return float(duration_str)
            return None
        except Exception as e:
            logger.error(f"Ошибка при определении длительности: {e}")
            return None

    def validate_audio_file(self, file_path: str, max_size_mb: int = 20) -> tuple[bool, str]:
        if not os.path.exists(file_path): return False, "Файл не найден"
        file_ext = os.path.splitext(file_path)[1].lower()
        if file_ext == '.tmp' and '/tmp/' in file_path: file_ext = '.mp4'
        if file_ext not in (self.supported_audio_formats + self.supported_video_formats):
            return False, f"Неподдерживаемый формат файла. Поддерживаются: {', '.join(self.supported_audio_formats + self.supported_video_formats)}"
        try:
            file_size = os.path.getsize(file_path)
            max_size_bytes = max_size_mb * 1024 * 1024
            if file_size > max_size_bytes: return False, f"Файл слишком большой ({file_size / (1024 * 1024):.1f}MB). Максимум: {max_size_mb}MB"
            if file_size == 0: return False, "Файл пустой"
        except Exception as e:
            return False, f"Ошибка при проверке размера файла: {e}"
        return True, "Файл валиден"