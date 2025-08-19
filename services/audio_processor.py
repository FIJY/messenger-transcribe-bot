# services/audio_processor.py - ИСПРАВЛЕННАЯ версия с лучшей проверкой файлов
import os
import asyncio
import logging
from typing import Optional, Tuple
import tempfile
import aiofiles

logger = logging.getLogger(__name__)


class AudioProcessor:
    def __init__(self):
        self.supported_audio_formats = ['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac', '.oga']
        self.supported_video_formats = ['.mp4', '.avi', '.mov', '.mkv', '.webm']

    async def validate_audio_file(self, file_path: str, max_size_mb: int = 2048) -> tuple[bool, str]:
        """ИСПРАВЛЕННАЯ валидация для файлов до 2GB"""

        # Ждем появления файла (может быть большим и долго скачиваться)
        for attempt in range(10):  # Увеличено до 10 попыток для больших файлов
            if await asyncio.to_thread(os.path.exists, file_path):
                break
            logger.info(f"Ожидание большого файла {file_path}, попытка {attempt + 1}/10")
            await asyncio.sleep(5)  # Увеличено до 5 секунд

        if not await asyncio.to_thread(os.path.exists, file_path):
            return False, "Файл не найден после ожидания"

        file_ext = os.path.splitext(file_path)[1].lower()

        # Для .tmp файлов считаем их валидными (Telegram файлы)
        if file_ext == '.tmp' and '/tmp/' in file_path:
            file_ext = '.oga'

        # Проверяем формат
        all_formats = self.supported_audio_formats + self.supported_video_formats
        if file_ext not in all_formats and file_ext != '.tmp':
            logger.warning(f"Неизвестный формат {file_ext}, но попробуем обработать")

        try:
            file_size = await asyncio.to_thread(os.path.getsize, file_path)
            max_size_bytes = max_size_mb * 1024 * 1024

            if file_size > max_size_bytes:
                return False, f"Файл слишком большой ({file_size / (1024 * 1024):.1f}MB). Максимум: {max_size_mb}MB"

            if file_size == 0:
                return False, "Файл пустой"

            # Дополнительная проверка для гигантских файлов
            file_size_gb = file_size / (1024 * 1024 * 1024)
            if file_size_gb > 2:
                return False, f"Файл слишком большой ({file_size_gb:.1f}GB). Максимум: 2GB"

            logger.info(f"Файл прошел валидацию: {file_path} ({file_size / (1024 * 1024):.1f}MB)")
            return True, "Файл валиден"

        except Exception as e:
            return False, f"Ошибка при проверке размера файла: {e}"

    async def process_file(self, file_path: str) -> Optional[str]:
        """ИСПРАВЛЕННАЯ обработка файла с лучшей проверкой существования"""

        # Проверяем существование файла с задержкой (файл может еще скачиваться)
        for attempt in range(5):  # 5 попыток с интервалом
            if await asyncio.to_thread(os.path.exists, file_path):
                break
            logger.info(f"Файл {file_path} не найден, попытка {attempt + 1}/5...")
            await asyncio.sleep(1)  # Ждем 1 секунду

        if not await asyncio.to_thread(os.path.exists, file_path):
            logger.error(f"Файл не найден после всех попыток: {file_path}")
            return None

        # Проверяем размер файла (убеждаемся что файл не пустой)
        try:
            file_size = await asyncio.to_thread(os.path.getsize, file_path)
            if file_size == 0:
                logger.error(f"Файл пустой: {file_path}")
                return None
            logger.info(f"Файл найден, размер: {file_size} байт")
        except Exception as e:
            logger.error(f"Ошибка при проверке размера файла {file_path}: {e}")
            return None

        file_ext = os.path.splitext(file_path)[1].lower()

        if file_ext == '.tmp' and '/tmp/' in file_path:
            logger.info(f"Обрабатываем Telegram .tmp файл как аудио: {file_path}")
            # Пробуем определить тип по содержимому или считаем аудио
            file_ext = '.oga'  # Большинство голосовых сообщений Telegram в OGA

        if file_ext in self.supported_audio_formats:
            logger.info(f"Файл уже в поддерживаемом аудио формате: {file_ext}")
            return file_path

        if file_ext in self.supported_video_formats:
            logger.info(f"Извлекаем аудио из видео файла: {file_ext}")
            return await self._extract_audio_from_video(file_path)

        logger.warning(f"Неизвестный формат файла: {file_ext}, пробуем обработать как аудио")
        return file_path  # Пробуем обработать как есть

    @staticmethod
    async def _extract_audio_from_video(video_path: str) -> Optional[str]:
        """ИСПРАВЛЕННОЕ извлечение аудио с проверкой ffmpeg"""
        try:
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False, dir='/tmp') as temp_audio:
                audio_path = temp_audio.name

            # Проверяем наличие ffmpeg
            try:
                process = await asyncio.create_subprocess_exec(
                    'ffmpeg', '-version',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.communicate()
                if process.returncode != 0:
                    logger.error("ffmpeg не найден в системе")
                    return video_path  # Возвращаем исходный файл
            except FileNotFoundError:
                logger.error("ffmpeg не установлен, пропускаем конвертацию видео")
                return video_path

            command = [
                'ffmpeg', '-i', video_path,
                '-vn',  # Без видео
                '-q:a', '0',  # Лучшее качество аудио
                '-map', '0:a:0?',  # Первый аудио поток (если есть)
                '-y', audio_path  # Перезаписать файл
            ]

            logger.info(f"Выполняем команду: {' '.join(command)}")

            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info(f"Аудио успешно извлечено: {audio_path}")
                return audio_path
            else:
                logger.error(f"Ошибка ffmpeg: {stderr.decode()}")
                if await asyncio.to_thread(os.path.exists, audio_path):
                    await asyncio.to_thread(os.remove, audio_path)
                return video_path  # Возвращаем исходный файл для попытки обработать как аудио

        except Exception as e:
            logger.error(f"Неожиданная ошибка при извлечении аудио: {e}")
            return video_path

    @staticmethod
    async def cleanup_temp_file(file_path: str):
        """УЛУЧШЕННАЯ очистка временных файлов"""
        if not file_path:
            return

        try:
            if await asyncio.to_thread(os.path.exists, file_path):
                await asyncio.to_thread(os.remove, file_path)
                logger.debug(f"Временный файл удален: {file_path}")
        except Exception as e:
            logger.warning(f"Не удалось удалить временный файл {file_path}: {e}")

    async def convert_to_wav(self, input_path: str) -> Optional[str]:
        """ИСПРАВЛЕННАЯ конвертация в WAV"""
        try:
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False, dir='/tmp') as temp_audio:
                output_path = temp_audio.name

            # Проверяем ffmpeg
            try:
                process = await asyncio.create_subprocess_exec(
                    'ffmpeg', '-version',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.communicate()
                if process.returncode != 0:
                    logger.error("ffmpeg недоступен для конвертации в WAV")
                    return input_path
            except FileNotFoundError:
                logger.error("ffmpeg не найден, возвращаем исходный файл")
                return input_path

            command = [
                'ffmpeg', '-i', input_path, '-vn', '-acodec', 'pcm_s16le',
                '-ar', '16000', '-ac', '1', '-y', output_path
            ]

            logger.info(f"Конвертируем в WAV: {' '.join(command)}")

            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info(f"Файл успешно сконвертирован в WAV: {output_path}")
                return output_path
            else:
                logger.error(f"Ошибка ffmpeg при конвертации в WAV: {stderr.decode()}")
                if await asyncio.to_thread(os.path.exists, output_path):
                    await asyncio.to_thread(os.remove, output_path)
                return input_path

        except Exception as e:
            logger.error(f"Неожиданная ошибка при конвертации в WAV: {e}")
            return input_path

    @staticmethod
    async def get_media_duration(file_path: str) -> Optional[float]:
        """Получение длительности медиа файла"""
        try:
            # Проверяем наличие ffprobe
            try:
                process = await asyncio.create_subprocess_exec(
                    'ffprobe', '-version',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.communicate()
                if process.returncode != 0:
                    return None
            except FileNotFoundError:
                logger.warning("ffprobe не найден, не можем определить длительность")
                return None

            command = ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of',
                       'default=noprint_wrappers=1:nokey=1', file_path]

            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                duration_str = stdout.decode().strip()
                if duration_str and duration_str != 'N/A':
                    return float(duration_str)
            return None

        except Exception as e:
            logger.error(f"Ошибка при определении длительности: {e}")
            return None