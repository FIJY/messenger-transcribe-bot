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
    import requests
    from stem import Signal
    from stem.control import Controller
    _tor_ok = True
except Exception:
    requests = None
    Signal = None
    Controller = None
    _tor_ok = False



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
        logger.error(f"❌ Ошибка создания куков: {e}")
        return None


# Обновите функцию get_yt_dlp_options():
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


# Обновите основную функцию загрузки:
async def download_youtube_with_cookies(video_url: str):
    cookies_file = setup_cookies_file()
    try:
        options = get_yt_dlp_options(cookies_file)
        options_info = options.copy()
        options_info['skip_download'] = True
        with yt_dlp.YoutubeDL(options_info) as ydl:
            info = ydl.extract_info(video_url, download=False)
            if info:
                logger.info(f"✅ Информация получена: {info.get('title', 'Unknown')}")
                has_subtitles = bool(info.get('subtitles') or info.get('automatic_captions'))
                if has_subtitles:
                    logger.info("📝 Субтитры найдены!")
                    return info
                else:
                    logger.info("🎵 Субтитров нет, скачиваем аудио")
                    return info
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки с куками: {e}")
        return None
    finally:
        if cookies_file and os.path.exists(cookies_file):
            try:
                os.unlink(cookies_file)
                logger.info("🧹 Временный файл куков удален")
            except:
                pass
    return None


# ==== Диагностика импортов (мягкая, без падения) ====
try:
    import yt_dlp

    _yt_dlp_ok = True
except Exception as _e:
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

# ==== Cloudflare R2 (S3 совместимый) ====
try:
    import boto3
    from botocore.client import Config

    _boto_ok = True
except Exception:
    boto3 = None
    Config = None
    _boto_ok = False

# ==== Tor support ====
try:
    import requests
    from stem import Signal
    from stem.control import Controller
    import subprocess

    _tor_ok = True
except Exception:
    requests = None
    Signal = None
    Controller = None
    subprocess = None
    _tor_ok = False

logger = logging.getLogger(__name__)

# ==== Хранилище для локальных аудио (временное) ====
AUDIO_STORAGE_DIR = os.environ.get("AUDIO_STORAGE_DIR", "/tmp/youtube_audio")
MAX_FILE_AGE_SECONDS = int(os.environ.get("AUDIO_MAX_AGE_SEC", "86400"))  # 24h
USE_TOR = os.getenv("USE_TOR", "true").lower() == "true"
TOR_SOCKS_PORT = int(os.getenv("TOR_PORT", "9050"))
TOR_CONTROL_PORT = int(os.getenv("TOR_CONTROL_PORT", "9051"))
YT_PROXY = os.getenv("YT_PROXY", f"socks5://127.0.0.1:{TOR_SOCKS_PORT}")


# ==== R2 окружение ====
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "")
R2_BUCKET = os.getenv("R2_BUCKET_NAME", "")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL", "")
R2_PUBLIC_BASEURL = os.getenv("R2_PUBLIC_BASEURL", "")

# ==== YouTube окружение / настройки ====
YT_PROXY = os.getenv("YT_PROXY", "").strip()
# Умная логика с поддержкой переменных окружения
YT_COOKIES_FILE = ""
cookies_data = os.getenv("YT_COOKIES_DATA", "")
use_cookies = os.getenv("USE_COOKIES", "true").lower() == "true"

if cookies_data and use_cookies:
    # Создаем временный файл из переменной
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(cookies_data)
        YT_COOKIES_FILE = f.name
else:
    # Fallback на локальный файл для разработки
    local_cookies = os.getenv("YT_COOKIES_FILE", "cookies.txt")
    if os.path.exists(local_cookies):
        YT_COOKIES_FILE = local_cookies
YT_DLP_UA = os.getenv("YT_DLP_UA", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

# ==== Tor настройки ====
USE_TOR = os.getenv("USE_TOR", "false").lower() == "true"
TOR_PORT = int(os.getenv("TOR_PORT", "9050"))
TOR_CONTROL_PORT = int(os.getenv("TOR_CONTROL_PORT", "9051"))

# Invidious инстансы (для резервных попыток)
invid_env = os.getenv("YT_INVIDIOUS_INSTANCES", "")
if invid_env.strip():
    YT_INVIDIOUS_INSTANCES = [x.strip() for x in invid_env.split(",") if x.strip()]
else:
    YT_INVIDIOUS_INSTANCES = [
        "https://yewtu.be",
        "https://invidious.io",
        "https://invidious.fdn.fr",
        "https://invidious.privacydev.net",
        "https://piped.video",
        "https://piped.kavin.rocks",
        "https://inv.riverside.rocks",
        "https://invidious.snopyta.org",
    ]


class SmartVideoError(Exception):
    pass


class SubtitleNotFoundError(SmartVideoError):
    pass


class DownloadError(SmartVideoError):
    pass


class YouTubeBlockedError(SmartVideoError):
    pass


class TorService:
    """Сервис для УПРАВЛЕНИЯ уже запущенным Tor"""

    def __init__(self, tor_port: int, control_port: int):
        self.tor_port = tor_port
        self.control_port = control_port
        self.current_ip = None
        self.is_enabled = USE_TOR and _tor_ok
        self._is_running = False

    async def initialize(self) -> bool:
        """Проверяет, запущен ли Tor, и получает IP"""
        if not self.is_enabled:
            return False

        logger.info("Проверяем доступность Tor...")
        try:
            # Проверяем, открыт ли SOCKS порт
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection('127.0.0.1', self.tor_port),
                timeout=5
            )
            writer.close()
            await writer.wait_closed()
            logger.info(f"✅ Tor SOCKS порт {self.tor_port} доступен.")
            self._is_running = True
            await self.get_current_ip() # Получаем начальный IP
            return True
        except (ConnectionRefusedError, asyncio.TimeoutError):
            logger.error(f"❌ Tor SOCKS порт {self.tor_port} недоступен. Убедитесь, что Tor запущен.")
            self._is_running = False
            return False
        except Exception as e:
            logger.error(f"Неизвестная ошибка при проверке Tor: {e}")
            self._is_running = False
            return False

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
            logger.info(f"🌐 Текущий IP через Tor: {self.current_ip}")
            return self.current_ip
        except Exception as e:
            logger.warning(f"Не удалось получить IP через Tor: {e}")
            return None

    async def change_ip(self) -> bool:
        """Отправляет сигнал NEWNYM для смены IP"""
        if not self.is_running():
            return False
        logger.info("🔄 Запрашиваем новый IP у Tor...")
        try:
            with Controller.from_port(port=self.control_port) as controller:
                controller.authenticate()
                controller.signal(Signal.NEWNYM)
            await asyncio.sleep(10) # Даем время на смену цепочки
            await self.get_current_ip()
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка смены IP: {e}")
            return False

    def is_running(self) -> bool:
        return self._is_running


def _r2_enabled() -> bool:
    return all([_boto_ok, R2_ACCOUNT_ID, R2_BUCKET, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY])


def _init_r2_client():
    if not _r2_enabled():
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

# ==== Диагностика импортов (мягкая, без падения) ====
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
USE_TOR = os.getenv("USE_TOR", "true").lower() == "true"
TOR_SOCKS_PORT = int(os.getenv("TOR_PORT", "9050"))
TOR_CONTROL_PORT = int(os.getenv("TOR_CONTROL_PORT", "9051"))
YT_PROXY = os.getenv("YT_PROXY", f"socks5://127.0.0.1:{TOR_SOCKS_PORT}")

R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "")
R2_BUCKET = os.getenv("R2_BUCKET_NAME", "")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_PUBLIC_BASEURL = os.getenv("R2_PUBLIC_BASEURL", "")

class SmartVideoError(Exception): pass
class SubtitleNotFoundError(SmartVideoError): pass
class DownloadError(SmartVideoError): pass
class YouTubeBlockedError(SmartVideoError): pass

class TorService:
    """Сервис для УПРАВЛЕНИЯ уже запущенным Tor"""

    def __init__(self, tor_port: int, control_port: int):
        self.tor_port = tor_port
        self.control_port = control_port
        self.current_ip = None
        self.is_enabled = USE_TOR and _tor_ok
        self._is_running = False

    async def initialize(self) -> bool:
        """Проверяет, запущен ли Tor, и получает IP"""
        if not self.is_enabled:
            return False

        logger.info("Проверяем доступность Tor...")
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection('127.0.0.1', self.tor_port),
                timeout=10
            )
            writer.close()
            await writer.wait_closed()
            logger.info(f"✅ Tor SOCKS порт {self.tor_port} доступен.")
            self._is_running = True
            await self.get_current_ip()
            return True
        except (ConnectionRefusedError, asyncio.TimeoutError):
            logger.error(f"❌ Tor SOCKS порт {self.tor_port} недоступен. Убедитесь, что Tor запущен в Docker.")
            self._is_running = False
            return False
        except Exception as e:
            logger.error(f"Неизвестная ошибка при проверке Tor: {e}")
            self._is_running = False
            return False

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
            logger.info(f"🌐 Текущий IP через Tor: {self.current_ip}")
            return self.current_ip
        except Exception as e:
            logger.warning(f"Не удалось получить IP через Tor: {e}")
            return None

    async def change_ip(self) -> bool:
        """Отправляет сигнал NEWNYM для смены IP"""
        if not self.is_running():
            return False
        logger.info("🔄 Запрашиваем новый IP у Tor...")
        try:
            with Controller.from_port(port=self.control_port) as controller:
                controller.authenticate()
                controller.signal(Signal.NEWNYM)
            await asyncio.sleep(10)
            await self.get_current_ip()
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка смены IP: {e}")
            return False

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
        """Инициализирует сервис и проверяет Tor"""
        if self.tor.is_enabled:
            await self.tor.initialize()

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

    def _get_ytdlp_options(self, output_path: str) -> Dict:
        """Формирует опции для yt-dlp"""
        opts = {
            "format": "bestaudio/best",
            "outtmpl": output_path.replace(".mp3", "") + ".%(ext)s",
            "quiet": True,
            "noprogress": True,
            "no_warnings": True,
            "noplaylist": True,
            "retries": 3,
            "postprocessors": [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        if self.tor.is_running():
            opts["proxy"] = YT_PROXY
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
            try:
                logger.info(f"Попытка {attempt}/{max_retries} скачать аудио для {video_id} через IP: {self.tor.current_ip}")
                opts = self._get_ytdlp_options(local_path)

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
                logger.warning(f"Ошибка при скачивании (попытка {attempt}): {e}")
                if attempt < max_retries:
                    if self.tor.is_running():
                        await self.tor.change_ip()
                else:
                    raise YouTubeBlockedError(f"Не удалось скачать видео после {max_retries} попыток. Последняя ошибка: {e}")

        raise DownloadError("Неизвестная ошибка скачивания.")

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


# Удобная функция для инициализации
async def create_smart_video_service() -> SmartVideoService:
    """Создает и инициализирует SmartVideoService"""
    service = SmartVideoService()
    await service.initialize()
    return service


# Функция для получения статуса системы
async def get_system_status() -> Dict[str, Any]:
    """Возвращает статус всех компонентов системы"""
    service = SmartVideoService()

    # Тестируем Tor если включен
    tor_status = "disabled"
    tor_ip = None
    if service.tor.is_enabled:
        if await service.tor.start_tor():
            tor_status = "running"
            tor_ip = service.tor.current_ip
        else:
            tor_status = "failed"

    # Тестируем Invidious
    invidious_working = []
    for instance in YT_INVIDIOUS_INSTANCES[:3]:  # Тестируем первые 3
        try:
            proxies = service.tor.get_requests_proxies() if service.tor.is_running() else None
            response = requests.get(f"{instance}/api/v1/stats", timeout=10, proxies=proxies)
            if response.status_code == 200:
                invidious_working.append(instance)
        except Exception:
            pass

    await service.tor.stop()

    return {
        "components": {
            "yt_dlp": _yt_dlp_ok,
            "youtube_transcript_api": _yta_ok,
            "boto3_r2": _boto_ok,
            "tor": service.tor.is_enabled,
            "requests": requests is not None
        },
        "r2": {
            "configured": _r2_enabled(),
            "account_id": bool(R2_ACCOUNT_ID),
            "bucket": bool(R2_BUCKET),
            "credentials": bool(R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY)
        },
        "tor": {
            "enabled": USE_TOR,
            "status": tor_status,
            "ip": tor_ip,
            "port": TOR_PORT,
            "control_port": TOR_CONTROL_PORT
        },
        "invidious": {
            "total_instances": len(YT_INVIDIOUS_INSTANCES),
            "working_instances": len(invidious_working),
            "working_urls": invidious_working
        },
        "environment": {
            "use_tor": USE_TOR,
            "yt_proxy": bool(YT_PROXY),
            "cookies_file": bool(YT_COOKIES_FILE and os.path.exists(YT_COOKIES_FILE))
        }
    }
