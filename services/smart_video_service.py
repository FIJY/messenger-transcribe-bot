# services/smart_video_service.py
import os
import re
import time
import hashlib
import logging
import tempfile
import asyncio
from typing import Optional, Dict, Any, Tuple, List
from concurrent.futures import ThreadPoolExecutor

# ==== Диагностика импортов ====
try:
    import yt_dlp

    _yt_dlp_ok = True
except Exception:
    yt_dlp = None
    _yt_dlp_ok = False

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

    _yta_ok = True
except Exception:
    YouTubeTranscriptApi = None
    NoTranscriptFound = Exception
    TranscriptsDisabled = Exception
    _yta_ok = False

try:
    import boto3
    from botocore.client import Config

    _boto_ok = True
except Exception:
    boto3 = None
    Config = None
    _boto_ok = False

try:
    import requests
    from stem import Signal
    from stem.control import Controller

    _tor_ok = True
except Exception:
    requests = None
    Signal = None
    Controller = None
    _tor_ok = False

logger = logging.getLogger(__name__)

# ==== Настройки ====
AUDIO_STORAGE_DIR = os.environ.get("AUDIO_STORAGE_DIR", "/tmp/youtube_audio")
MAX_FILE_AGE_SECONDS = int(os.environ.get("AUDIO_MAX_AGE_SEC", "86400"))  # 24h
USE_TOR = os.getenv("USE_TOR", "true").lower() == "true"
TOR_SOCKS_PORT = int(os.getenv("TOR_PORT", "9050"))
TOR_CONTROL_PORT = int(os.getenv("TOR_CONTROL_PORT", "9051"))
YT_PROXY = os.getenv("YT_PROXY", f"socks5://127.0.0.1:{TOR_SOCKS_PORT}")

# R2 окружение
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "")
R2_BUCKET = os.getenv("R2_BUCKET_NAME", "")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_PUBLIC_BASEURL = os.getenv("R2_PUBLIC_BASEURL", "")


class SmartVideoError(Exception): pass


class SubtitleNotFoundError(SmartVideoError): pass


class DownloadError(SmartVideoError): pass


class YouTubeBlockedError(SmartVideoError): pass


def setup_cookies_file():
    """Создать временный файл с куками из переменной окружения"""
    cookies_data = os.getenv('YT_COOKIES_DATA')
    if not cookies_data:
        return None

    try:
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write(cookies_data)
            logger.info(f"🍪 Куки созданы: {f.name}")
            return f.name
    except Exception as e:
        logger.error(f"❌ Ошибка создания кукков: {e}")
        return None


def get_yt_dlp_options(cookies_file=None):
    options = {
        'format': 'best[height<=720]/best',
        'noplaylist': True,
        'extract_flat': False,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['ru', 'en', 'auto'],
        'ignoreerrors': True,
        'no_warnings': False,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate'
        },
        'extractor_retries': 3,
        'fragment_retries': 3,
        'retry_sleep_functions': {
            'http': lambda n: min(2 ** n, 10),
            'fragment': lambda n: min(2 ** n, 10)
        }
    }

    if cookies_file and os.path.exists(cookies_file):
        options['cookiefile'] = cookies_file
        logger.info(f"🍪 Используем куки: {cookies_file}")

    if os.getenv('USE_TOR', 'false').lower() == 'true':
        options['proxy'] = os.getenv('YT_PROXY', 'socks5://127.0.0.1:9050')

    return options


class TorService:
    """Сервис для УПРАВЛЕНИЯ Tor (запуск, смена IP)"""

    def __init__(self, tor_port: int, control_port: int):
        self.tor_port = tor_port
        self.control_port = control_port
        self.current_ip = None
        self.is_enabled = USE_TOR and _tor_ok
        self._is_running = False
        self._tor_process = None

    async def start_tor(self) -> bool:
        """Запускает Tor если он не запущен"""
        if not self.is_enabled:
            logger.warning("⚠️ Tor отключен в настройках")
            return False

        # Проверяем, не запущен ли уже
        if await self._check_tor_running():
            logger.info("✅ Tor уже запущен")
            self._is_running = True
            await self.get_current_ip()
            return True

        logger.info("🚀 Запускаем Tor...")
        try:
            # Проверяем наличие tor в системе
            try:
                result = subprocess.run(['which', 'tor'], capture_output=True, text=True)
                if result.returncode != 0:
                    logger.error("❌ Tor не установлен в системе")
                    return False
                tor_path = result.stdout.strip()
                logger.info(f"📍 Tor найден: {tor_path}")
            except Exception as e:
                logger.error(f"❌ Ошибка поиска Tor: {e}")
                return False

            # Создаем директорию для данных
            os.makedirs('/tmp/tor_data', exist_ok=True)

            # Запускаем Tor в фоне
            self._tor_process = subprocess.Popen([
                'tor',
                '--SocksPort', str(self.tor_port),
                '--ControlPort', str(self.control_port),
                '--DataDirectory', '/tmp/tor_data',
                '--quiet'
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            logger.info(f"🔄 Ждем запуска Tor (PID: {self._tor_process.pid})...")

            # Ждем запуска (до 30 секунд)
            for i in range(30):
                await asyncio.sleep(1)
                if await self._check_tor_running():
                    logger.info(f"✅ Tor запущен за {i + 1} секунд")
                    self._is_running = True
                    await self.get_current_ip()
                    return True

            logger.error("❌ Tor не смог запуститься за 30 секунд")
            if self._tor_process:
                self._tor_process.terminate()
                self._tor_process = None
            return False

        except FileNotFoundError:
            logger.error("❌ Команда 'tor' не найдена. Убедитесь что Tor установлен")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Tor: {e}")
            return False

    async def _check_tor_running(self) -> bool:
        """Проверяет, запущен ли Tor"""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection('127.0.0.1', self.tor_port),
                timeout=3
            )
            writer.close()
            await writer.wait_closed()
            return True
        except:
            return False

    async def initialize(self) -> bool:
        """Инициализация - проверяет или запускает Tor"""
        if not self.is_enabled:
            return False

        logger.info("🔍 Проверяем Tor...")

        # Сначала проверяем, не запущен ли уже
        if await self._check_tor_running():
            logger.info("✅ Tor уже запущен и доступен")
            self._is_running = True
            await self.get_current_ip()
            return True

        # Если нет - пытаемся запустить
        return await self.start_tor()

    async def get_current_ip(self) -> Optional[str]:
        """Получает текущий IP через Tor"""
        if not self.is_running():
            return None
        try:
            loop = asyncio.get_event_loop()
            proxies = {'http': YT_PROXY, 'https': YT_PROXY}
            response = await loop.run_in_executor(
                None,
                lambda: requests.get('https://api.ipify.org?format=json', proxies=proxies, timeout=15)
            )
            response.raise_for_status()
            self.current_ip = response.json().get("ip")
            logger.info(f"🌍 Текущий IP через Tor: {self.current_ip}")
            return self.current_ip
        except Exception as e:
            logger.warning(f"Не удалось получить IP через Tor: {e}")
            return None

    async def change_ip(self) -> bool:
        """Отправляет сигнал NEWNYM для смены IP (как в bash скрипте)"""
        if not self.is_running():
            return False
        logger.info("🔄 Запрашиваем новый IP у Tor...")
        try:
            # Используем тот же метод что и в bash скрипте
            proc = await asyncio.create_subprocess_shell(
                f'echo -e \'AUTHENTICATE ""\nSIGNAL NEWNYM\nQUIT\' | nc 127.0.0.1 {self.control_port}',
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await proc.wait()

            await asyncio.sleep(5)  # Ждем как в bash скрипте
            old_ip = self.current_ip
            await self.get_current_ip()

            if self.current_ip != old_ip:
                logger.info(f"✅ IP изменен: {old_ip} → {self.current_ip}")
                return True
            else:
                logger.warning("⚠️ IP не изменился")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка смены IP: {e}")
            return False

    async def stop(self):
        """Останавливает Tor процесс"""
        if self._tor_process:
            self._tor_process.terminate()
            self._tor_process = None
            self._is_running = False
            logger.info("🛑 Tor остановлен")

    def is_running(self) -> bool:
        return self._is_running


class SmartVideoService:
    def __init__(self):
        self.download_available = _yt_dlp_ok
        self.subtitles_available = _yta_ok
        self.s3 = self._init_r2_client()
        self.tor = TorService(TOR_SOCKS_PORT, TOR_CONTROL_PORT)
        self.executor = ThreadPoolExecutor(max_workers=2)
        if not self.download_available:
            logger.warning("yt-dlp не установлен. Загрузка аудио недоступна.")

    async def initialize(self):
        """Инициализирует сервис и запускает Tor"""
        if self.tor.is_enabled:
            # Пытаемся запустить Tor
            await self.tor.initialize()
            if self.tor.is_running():
                logger.info(f"🌐 Tor запущен. IP: {self.tor.current_ip}")
            else:
                logger.warning("⚠️ Tor не удалось запустить, работаем без прокси")

    def _init_r2_client(self):
        if not all([_boto_ok, R2_ACCOUNT_ID, R2_BUCKET, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY]):
            return None
        session = boto3.session.Session()
        return session.client(
            "s3",
            endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )

    @staticmethod
    def is_youtube_url(url: str) -> bool:
        youtube_patterns = [
            r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([^&\s]+)',
            r'(?:https?://)?(?:www\.)?youtu\.be/([^?\s]+)',
        ]
        for pattern in youtube_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        return False

    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        patterns = [r'(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})']
        for pattern in patterns:
            m = re.search(pattern, url)
            if m: return m.group(1)
        return None

    async def get_video_info(self, url: str) -> Dict[str, Any]:
        """
        ДОБАВЛЕННЫЙ МЕТОД: Получает информацию о видео через yt-dlp
        """
        if not self.download_available:
            raise DownloadError("yt-dlp не установлен")

        video_id = self.extract_video_id(url)
        if not video_id:
            raise SmartVideoError("Не удалось извлечь ID видео")

        cookies_file = setup_cookies_file()
        try:
            options = get_yt_dlp_options(cookies_file)
            options['skip_download'] = True  # Только получаем информацию

            def _extract_info():
                with yt_dlp.YoutubeDL(options) as ydl:
                    return ydl.extract_info(url, download=False)

            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(self.executor, _extract_info)

            if info:
                logger.info(f"✅ Информация получена: {info.get('title', 'Unknown')}")
                return info
            else:
                raise DownloadError("Не удалось получить информацию о видео")

        except Exception as e:
            logger.error(f"❌ Ошибка получения информации о видео: {e}")
            raise DownloadError(f"Ошибка получения информации: {e}")
        finally:
            if cookies_file and os.path.exists(cookies_file):
                try:
                    os.unlink(cookies_file)
                    logger.info("🧹 Временный файл кукков удален")
                except:
                    pass

    def _get_ytdlp_options(self, output_path: str = None, cookies_file: str = None) -> Dict:
        """Формирует опции для yt-dlp с поддержкой кукков"""
        opts = {
            "format": "bestaudio/best",
            "quiet": False,  # Включаем логи для отладки
            "noprogress": True,
            "no_warnings": False,
            "noplaylist": True,
            "retries": 3,
            "http_headers": {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate'
            },
            "extractor_retries": 3,
            "fragment_retries": 3,
        }

        if output_path:
            opts.update({
                "outtmpl": output_path.replace(".mp3", "") + ".%(ext)s",
                "postprocessors": [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })

        # Добавляем куки если есть
        if cookies_file and os.path.exists(cookies_file):
            opts['cookiefile'] = cookies_file
            logger.info(f"🍪 Используем куки для скачивания: {cookies_file}")

        # Добавляем прокси если Tor запущен
        if self.tor.is_running():
            opts["proxy"] = YT_PROXY
            logger.info(f"🌐 Используем Tor прокси: {YT_PROXY}")

        return opts

    async def get_transcript_text(self, video_id: str, languages: List[str]) -> str:
        """Получает текст субтитров"""
        if not self.subtitles_available:
            raise SubtitleNotFoundError("Библиотека для субтитров не установлена.")

        def _get_sync():
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript = None
            for lang in languages:
                try:
                    transcript = transcript_list.find_transcript([lang])
                    break
                except NoTranscriptFound:
                    continue
            if not transcript:
                raise NoTranscriptFound(video_id)

            transcript_data = transcript.fetch()
            text_parts = [item['text'] for item in transcript_data]
            return ' '.join(text_parts)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _get_sync)

    async def download_audio(self, url: str) -> str:
        """Скачивает аудио, используя Tor, со сменой IP при ошибке"""
        if not self.download_available:
            raise DownloadError("yt-dlp не установлен")

        video_id = self.extract_video_id(url)
        if not video_id:
            raise SmartVideoError("Не удалось извлечь ID видео")

        os.makedirs(AUDIO_STORAGE_DIR, exist_ok=True)
        local_path = os.path.join(AUDIO_STORAGE_DIR, f"{video_id}.mp3")

        if os.path.exists(local_path):
            logger.info(f"✅ Файл уже существует локально: {local_path}")
            return local_path

        loop = asyncio.get_event_loop()
        max_retries = 3

        for attempt in range(1, max_retries + 1):
            cookies_file = None
            try:
                # Создаем куки для каждой попытки
                cookies_file = setup_cookies_file()

                logger.info(
                    f"Попытка {attempt}/{max_retries} скачать аудио для {video_id} через IP: {self.tor.current_ip}")
                opts = self._get_ytdlp_options(local_path, cookies_file)

                def _download():
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        ydl.download([url])

                await loop.run_in_executor(self.executor, _download)

                final_path = os.path.splitext(local_path)[0] + ".mp3"
                if os.path.exists(final_path):
                    logger.info(f"✅ Аудио успешно скачано: {final_path}")
                    return final_path
                else:
                    raise DownloadError("Файл не был создан после скачивания.")

            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Ошибка при скачивании (попытка {attempt}): {error_msg}")

                # Если это ошибка аутентификации - пробуем запустить/переключить Tor
                if "Sign in to confirm" in error_msg or "bot" in error_msg.lower():
                    if not self.tor.is_running() and self.tor.is_enabled:
                        logger.info("🔄 Пытаемся запустить Tor для обхода блокировки...")
                        await self.tor.start_tor()
                    elif self.tor.is_running():
                        logger.info("🔄 Меняем IP через Tor...")
                        await self.tor.change_ip()
                    else:
                        logger.warning("⚠️ Tor недоступен, не можем обойти блокировку")

                if attempt == max_retries:
                    raise YouTubeBlockedError(
                        f"Не удалось скачать видео после {max_retries} попыток. YouTube требует аутентификацию. Последняя ошибка: {error_msg}")

                # Ждем между попытками
                await asyncio.sleep(2 * attempt)

            finally:
                # Очищаем временные куки
                if cookies_file and os.path.exists(cookies_file):
                    try:
                        os.unlink(cookies_file)
                    except:
                        pass

        raise DownloadError("Неизвестная ошибка скачивания.")

    async def enhanced_download_youtube_content(self, url: str) -> Dict[str, Any]:
        """
        ДОБАВЛЕННЫЙ МЕТОД: Расширенная загрузка контента YouTube
        Возвращает структурированный результат для обработчика
        """
        video_id = self.extract_video_id(url)
        logger.info(f"🎬 Начинаем обработку видео {video_id}: {url}")

        try:
            # Получаем информацию о видео
            logger.info(f"📋 Получаем информацию о видео {video_id}...")
            video_info = await self.get_video_info(url)
            logger.info(f"✅ Информация получена: '{video_info.get('title', 'Unknown')}'")

            # Проверяем наличие субтитров в полученной информации
            has_subtitles = bool(video_info.get('subtitles') or video_info.get('automatic_captions'))
            logger.info(f"📝 Субтитры доступны: {has_subtitles}")

            if has_subtitles:
                logger.info(f"📝 Обнаружены субтитры для {video_id}, пытаемся их получить...")
                try:
                    # Пытаемся получить контент
                    text, content_type, metadata = await self.get_text_smart(url)
                    logger.info(f"✅ Контент получен успешно. Тип: {content_type}")

                    return {
                        'success': True,
                        'video_id': video_id,
                        'title': video_info.get('title', 'Unknown'),
                        'duration': video_info.get('duration', 0),
                        'uploader': video_info.get('uploader', 'Unknown'),
                        'content_type': content_type,  # 'subtitles' или 'audio_file'
                        'content': text,  # Текст субтитров или путь к аудио файлу
                        'metadata': metadata,
                        'has_subtitles': has_subtitles,
                        'video_info': video_info
                    }
                except Exception as subtitle_error:
                    logger.warning(f"⚠️ Ошибка получения субтитров: {subtitle_error}")
                    logger.warning(f"⚠️ Тип ошибки: {type(subtitle_error).__name__}")
                    # Продолжаем к аудио

            # Если субтитров нет или не удалось их получить
            logger.info(f"🎵 Субтитров нет или не удалось получить, скачиваем аудио для {video_id}...")

            # Проверяем статус Tor перед скачиванием
            if self.tor.is_enabled and not self.tor.is_running():
                logger.info("🚀 Tor не запущен, пытаемся запустить...")
                await self.tor.start_tor()

            # Пытаемся скачать аудио напрямую
            try:
                logger.info(f"⬬ Начинаем скачивание аудио для {video_id}...")
                local_audio_path = await self.download_audio(url)
                logger.info(f"✅ Аудио скачано: {local_audio_path}")

                metadata = {
                    'method': 'audio_download',
                    'video_id': video_id,
                    'audio_path': local_audio_path,
                    'tor_used': self.tor.is_running(),
                    'current_ip': self.tor.current_ip
                }

                return {
                    'success': True,
                    'video_id': video_id,
                    'title': video_info.get('title', 'Unknown'),
                    'duration': video_info.get('duration', 0),
                    'uploader': video_info.get('uploader', 'Unknown'),
                    'content_type': 'audio_file',
                    'content': local_audio_path,
                    'metadata': metadata,
                    'has_subtitles': has_subtitles,
                    'video_info': video_info
                }
            except YouTubeBlockedError as blocked_error:
                logger.error(f"🚫 YouTube заблокировал доступ: {blocked_error}")
                # Специальная обработка блокировки YouTube
                return {
                    'success': False,
                    'error': f"YouTube заблокировал доступ: {str(blocked_error)}",
                    'error_type': 'YouTubeBlockedError',
                    'video_id': video_id,
                    'title': video_info.get('title', 'Unknown'),
                    'url': url,
                    'suggestion': 'Попробуйте позже или используйте другое видео'
                }
            except Exception as download_error:
                logger.error(f"❌ Ошибка скачивания аудио: {download_error}")
                logger.error(f"❌ Тип ошибки: {type(download_error).__name__}")
                raise download_error  # Пробрасываем дальше

        except Exception as e:
            logger.error(f"❌ КРИТИЧЕСКАЯ ошибка в enhanced_download_youtube_content для {video_id}")
            logger.error(f"❌ Ошибка: {str(e)}")
            logger.error(f"❌ Тип ошибки: {type(e).__name__}")

            # Логируем полный стэк трейс для отладки
            import traceback
            logger.error(f"❌ Полный стэк трейс:")
            logger.error(traceback.format_exc())

            return {
                'success': False,
                'error': str(e),
                'error_type': type(e).__name__,
                'video_id': video_id,
                'url': url,
                'debug_info': {
                    'tor_enabled': self.tor.is_enabled,
                    'tor_running': self.tor.is_running(),
                    'current_ip': self.tor.current_ip,
                    'download_available': self.download_available,
                    'subtitles_available': self.subtitles_available
                }
            }

    async def get_text_smart(self, url: str) -> Tuple[str, str, Dict[str, Any]]:
        """
        Главный метод: сначала пытается получить субтитры, если не удается - скачивает аудио.
        """
        video_id = self.extract_video_id(url)
        if not video_id:
            raise SmartVideoError("Не удалось извлечь ID видео")

        # 1. Попытка получить субтитры
        try:
            text = await self.get_transcript_text(video_id, languages=['ru', 'en'])
            logger.info(f"✅ Субтитры для {video_id} успешно получены.")
            metadata = {'method': 'subtitles', 'video_id': video_id}
            return text, 'subtitles', metadata
        except (NoTranscriptFound, TranscriptsDisabled):
            logger.info(f"Субтитры для {video_id} не найдены, переходим к скачиванию аудио.")
        except Exception as e:
            logger.warning(f"Ошибка при получении субтитров для {video_id}: {e}. Переходим к аудио.")

        # 2. Если субтитры не найдены - скачиваем аудио
        local_audio_path = await self.download_audio(url)
        metadata = {
            'method': 'audio_download',
            'video_id': video_id,
            'audio_path': local_audio_path,
            'tor_used': self.tor.is_running(),
            'current_ip': self.tor.current_ip
        }
        return local_audio_path, 'audio_file', metadata

    def get_capabilities(self) -> Dict[str, bool]:
        """Возвращает информацию о возможностях сервиса"""
        return {
            'subtitles': self.subtitles_available,
            'audio_download': self.download_available,
            'tor_available': self.tor.is_enabled,
            'tor_running': self.tor.is_running()
        }


def cleanup_old_audio_files():
    """Удаляет локальные аудиофайлы старше MAX_FILE_AGE_SECONDS."""
    now = time.time()
    os.makedirs(AUDIO_STORAGE_DIR, exist_ok=True)
    for filename in os.listdir(AUDIO_STORAGE_DIR):
        filepath = os.path.join(AUDIO_STORAGE_DIR, filename)
        try:
            if os.path.isfile(filepath):
                file_age = now - os.path.getmtime(filepath)
                if file_age > MAX_FILE_AGE_SECONDS:
                    os.remove(filepath)
                    logger.info(f"🗑️ Удален старый файл: {filepath}")
        except Exception as e:
            logger.warning(f"Не удалось удалить {filepath}: {e}")


# Удобная функция для инициализации
async def create_smart_video_service() -> SmartVideoService:
    """Создает и инициализирует SmartVideoService"""
    service = SmartVideoService()
    await service.initialize()
    return service


async def diagnose_system() -> Dict[str, Any]:
    """Диагностика системы для отладки проблем"""
    diagnosis = {
        'python_imports': {
            'yt_dlp': _yt_dlp_ok,
            'youtube_transcript_api': _yta_ok,
            'boto3': _boto_ok,
            'tor_libs': _tor_ok,
        },
        'system_commands': {},
        'environment': {},
        'tor_status': {},
        'errors': []
    }

    # Проверяем системные команды
    commands_to_check = ['tor', 'nc', 'ffmpeg', 'which']
    for cmd in commands_to_check:
        try:
            result = subprocess.run(['which', cmd], capture_output=True, text=True, timeout=5)
            diagnosis['system_commands'][cmd] = {
                'available': result.returncode == 0,
                'path': result.stdout.strip() if result.returncode == 0 else None
            }
        except Exception as e:
            diagnosis['system_commands'][cmd] = {'available': False, 'error': str(e)}

    # Проверяем переменные окружения
    env_vars = ['USE_TOR', 'YT_PROXY', 'YT_COOKIES_DATA', 'TOR_PORT', 'TOR_CONTROL_PORT']
    for var in env_vars:
        value = os.getenv(var)
        diagnosis['environment'][var] = {
            'set': value is not None,
            'value': value if var != 'YT_COOKIES_DATA' else ('***hidden***' if value else None)
        }

    # Проверяем Tor
    try:
        service = SmartVideoService()
        if service.tor.is_enabled:
            diagnosis['tor_status']['enabled'] = True
            diagnosis['tor_status']['can_start'] = await service.tor.start_tor()
            diagnosis['tor_status']['running'] = service.tor.is_running()
            diagnosis['tor_status']['ip'] = service.tor.current_ip
            await service.tor.stop()
        else:
            diagnosis['tor_status']['enabled'] = False
    except Exception as e:
        diagnosis['errors'].append(f"Tor check failed: {e}")

    return diagnosis