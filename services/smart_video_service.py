# services/smart_video_service.py
# Полная версия: YT -> (Tor/proxy/invidious) -> локально -> R2 cache -> возвращаем локальный путь + r2_url в метаданных
import os
import re
import time
import hashlib
import logging
import tempfile
import asyncio
from typing import Optional, Dict, Any, Tuple, List
from concurrent.futures import ThreadPoolExecutor

# Добавьте в начало smart_video_service.py

import tempfile
import os


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
    """Получить настройки yt-dlp с поддержкой куков"""

    options = {
        'format': 'best[height<=720]/best',
        'noplaylist': True,
        'extract_flat': False,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['ru', 'en', 'auto'],
        'ignoreerrors': True,
        'no_warnings': False,

        # Заголовки как в рабочем примере
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
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

    # Добавляем куки если есть
    if cookies_file and os.path.exists(cookies_file):
        options['cookiefile'] = cookies_file
        logger.info(f"🍪 Используем куки: {cookies_file}")

    # Tor прокси
    if os.getenv('USE_TOR', 'false').lower() == 'true':
        options['proxy'] = os.getenv('YT_PROXY', 'socks5://127.0.0.1:9050')

    return options


# Обновите основную функцию загрузки:
async def download_youtube_with_cookies(video_url: str):
    """Загрузка YouTube с использованием куков"""

    cookies_file = setup_cookies_file()

    try:
        options = get_yt_dlp_options(cookies_file)

        # Сначала пробуем получить информацию
        options_info = options.copy()
        options_info['skip_download'] = True

        with yt_dlp.YoutubeDL(options_info) as ydl:
            info = ydl.extract_info(video_url, download=False)

            if info:
                logger.info(f"✅ Информация получена: {info.get('title', 'Unknown')}")

                # Проверяем субтитры
                has_subtitles = bool(info.get('subtitles') or info.get('automatic_captions'))

                if has_subtitles:
                    logger.info("📝 Субтитры найдены!")
                    return info
                else:
                    logger.info("🎵 Субтитров нет, скачиваем аудио")
                    # Здесь можно добавить логику скачивания аудио
                    return info

    except Exception as e:
        logger.error(f"❌ Ошибка загрузки с куками: {e}")
        return None

    finally:
        # Очищаем временный файл куков
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
    """Tor сервис для обхода блокировок YouTube"""

    def __init__(self, tor_port: int = TOR_PORT, control_port: int = TOR_CONTROL_PORT):
        self.tor_port = tor_port
        self.control_port = control_port
        self.tor_process = None
        self.last_ip_change = 0
        self.current_ip = None
        self.is_enabled = USE_TOR and _tor_ok
        self.is_connected_to_existing = False # <-- ИЗМЕНЕНИЕ: Флаг для подключения к существующему Tor

    # <-- ИЗМЕНЕНИЕ: Новый асинхронный метод для проверки существующего Tor
    async def _connect_to_existing_tor(self) -> bool:
        """Проверяет, запущен ли Tor на нужном порту, и подключается к нему."""
        if not self.is_enabled:
            return False
        try:
            # Проверяем, открыт ли порт
            reader, writer = await asyncio.open_connection('127.0.0.1', self.tor_port)
            writer.close()
            await writer.wait_closed()
            logger.info(f"✅ Обнаружен открытый порт {self.tor_port}. Проверяем, является ли он Tor...")

            # Тестируем соединение, чтобы убедиться, что это рабочий Tor-прокси
            if await self._test_tor_connection():
                logger.info(f"✅ Успешно подключились к существующему Tor. IP: {self.current_ip}")
                self.is_connected_to_existing = True
                return True
            else:
                logger.warning(f"⚠️ Порт {self.tor_port} открыт, но это не рабочий Tor-прокси.")
                return False
        except ConnectionRefusedError:
            return False # Порт закрыт, это нормально
        except Exception as e:
            logger.warning(f"Ошибка при проверке существующего Tor: {e}")
            return False

    # <-- ИЗМЕНЕНИЕ: Логика запуска теперь сначала проверяет существующий Tor
    async def start_tor(self) -> bool:
        """Запускает Tor или подключается к существующему"""
        if not self.is_enabled:
            return False

        # 1. Попытка подключиться к уже запущенному Tor
        if await self._connect_to_existing_tor():
            logger.info("🧅 Используем уже запущенный Tor")
            return True

        # 2. Если не удалось, запускаем свой собственный процесс
        logger.info("🔍 Существующий Tor не найден, запускаем свой процесс...")
        try:
            result = subprocess.run(['which', 'tor'], capture_output=True)
            if result.returncode != 0:
                logger.error("❌ Tor не установлен. Установите: apt-get install tor")
                return False

            await self._create_tor_config()
            logger.info(f"🧅 Запускаем Tor на портах {self.tor_port}/{self.control_port}")
            self.tor_process = subprocess.Popen(
                ['tor', '-f', '/tmp/torrc', '--quiet'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            await asyncio.sleep(15)

            if await self._test_tor_connection():
                logger.info(f"✅ Tor запущен успешно, IP: {self.current_ip}")
                return True
            else:
                logger.error("❌ Tor запустился, но соединение не работает")
                self.stop()
                return False
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Tor: {e}")
            return False

    async def _create_tor_config(self):
        """Создает конфигурацию Tor"""
        config = f"""
SocksPort {self.tor_port}
ControlPort {self.control_port}
DataDirectory /tmp/tor_data
ExitNodes {{us}},{{de}},{{nl}},{{se}},{{ch}},{{fr}},{{ca}}
StrictNodes 0
NewCircuitPeriod 300
MaxCircuitDirtiness 300
CircuitBuildTimeout 10
LearnCircuitBuildTimeout 0
"""
        os.makedirs('/tmp/tor_data', exist_ok=True, mode=0o700)
        with open('/tmp/torrc', 'w') as f:
            f.write(config)

    # <-- ИЗМЕНЕНИЕ: Метод сделан асинхронным для корректной работы
    async def _test_tor_connection(self) -> bool:
        """Тестирует Tor соединение асинхронно"""
        try:
            loop = asyncio.get_event_loop()
            proxies = {
                'http': f'socks5://127.0.0.1:{self.tor_port}',
                'https': f'socks5://127.0.0.1:{self.tor_port}'
            }
            # Выполняем синхронный requests в отдельном потоке, чтобы не блокировать asyncio
            response = await loop.run_in_executor(
                None,
                lambda: requests.get('https://httpbin.org/ip', proxies=proxies, timeout=30)
            )
            if response.status_code == 200:
                ip_data = response.json()
                self.current_ip = ip_data.get('origin', 'unknown')
                return True
            return False
        except Exception as e:
            logger.warning(f"Ошибка тестирования Tor: {e}")
            return False

    async def change_ip(self) -> bool:
        """Принудительно меняет IP через Tor"""
        if not self.is_running():
            return False
        try:
            logger.info("🔄 Меняем IP через Tor...")
            with Controller.from_port(port=self.control_port) as controller:
                controller.authenticate()
                controller.signal(Signal.NEWNYM)
            await asyncio.sleep(10)
            old_ip = self.current_ip
            if await self._test_tor_connection():
                if self.current_ip != old_ip:
                    logger.info(f"✅ IP изменен: {old_ip} → {self.current_ip}")
                    self.last_ip_change = time.time()
                    return True
                else:
                    logger.warning("⚠️ IP не изменился, повторяем...")
                    return False
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка смены IP: {e}")
            return False

    def get_proxy_config(self) -> Optional[str]:
        """Возвращает строку прокси для yt-dlp"""
        if self.is_running():
            return f'socks5://127.0.0.1:{self.tor_port}'
        return None

    def get_requests_proxies(self) -> Optional[dict]:
        """Возвращает прокси для requests"""
        if self.is_running():
            return {
                'http': f'socks5://127.0.0.1:{self.tor_port}',
                'https': f'socks5://127.0.0.1:{self.tor_port}'
            }
        return None

    async def stop(self):
        """Останавливает Tor"""
        if self.tor_process:
            logger.info("🛑 Останавливаем Tor...")
            self.tor_process.terminate()
            self.tor_process.wait()
            self.tor_process = None

    # <-- ИЗМЕНЕНИЕ: Логика проверки теперь учитывает оба сценария
    def is_running(self) -> bool:
        """Проверяет, запущен ли Tor или мы к нему подключены"""
        is_process_running = self.tor_process is not None and self.tor_process.poll() is None
        return self.is_connected_to_existing or is_process_running

# ... остальная часть файла без изменений ...
# (Код ниже этой строки остается прежним)
# ...
# ...
# ...

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


class SmartVideoService:
    def __init__(self, temp_dir: Optional[str] = None, max_workers: int = 2):
        self.temp_dir = temp_dir or tempfile.gettempdir()
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

        self.subtitles_available = _yta_ok and (YouTubeTranscriptApi is not None)
        self.download_available = _yt_dlp_ok and (yt_dlp is not None)

        if not self.subtitles_available:
            logger.warning("youtube-transcript-api не установлен. Субтитры недоступны.")
        if not self.download_available:
            logger.warning("yt-dlp не установлен. Загрузка аудио недоступна.")

        self.s3 = _init_r2_client()
        if self.s3 is None:
            logger.warning("R2 не настроен: кеш в облаке отключён.")

        # Инициализируем Tor сервис
        self.tor = TorService()

        logger.info(f"SmartVideoService: субтитры={'✅' if self.subtitles_available else '❌'}, "
                    f"загрузка={'✅' if self.download_available else '❌'}, "
                    f"R2={'✅' if self.s3 else '❌'}, "
                    f"Tor={'✅' if self.tor.is_enabled else '❌'}")

    async def initialize(self):
        """Инициализирует сервис (запускает Tor если нужно)"""
        if self.tor.is_enabled:
            logger.info("🧅 Инициализируем Tor для обхода блокировок...")
            await self.tor.start_tor()

    # ========== Helpers ==========

    @staticmethod
    def is_youtube_url(url: str) -> bool:
        youtube_patterns = [
            r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([^&\s]+)',
            r'(?:https?://)?(?:www\.)?youtu\.be/([^?\s]+)',
            r'(?:https?://)?(?:m\.)?youtube\.com/watch\?v=([^&\s]+)',
            r'(?:https?://)?(?:mobile\.)?youtube\.com/watch\?v=([^&\s]+)',
        ]
        for pattern in youtube_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        return False

    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        patterns = [
            r'(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})',
            r'/embed/([a-zA-Z0-9_-]{11})',
            r'/v/([a-zA-Z0-9_-]{11})',
            r'watch\?v=([a-zA-Z0-9_-]{11})',
        ]
        for pattern in patterns:
            m = re.search(pattern, url)
            if m:
                return m.group(1)
        return None

    @staticmethod
    def _sha1(s: str) -> str:
        return hashlib.sha1(s.encode("utf-8")).hexdigest()

    def _r2_key_for_audio(self, video_id: str, codec: str = "mp3", abr: str = "192k") -> str:
        # Ключ в R2: можно добавить префиксы/папки
        return f"yt/{video_id}/{video_id}.{codec}"

    def _r2_url_for_key(self, key: str) -> Optional[str]:
        if not self.s3:
            return None
        # Если есть публичный базовый URL (через Cloudflare/domain), формируем постоянную ссылку
        if R2_PUBLIC_BASEURL:
            return f"{R2_PUBLIC_BASEURL.rstrip('/')}/{key}"
        # Иначе — временная пресайн-ссылка
        try:
            return self.s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": R2_BUCKET, "Key": key},
                ExpiresIn=24 * 3600,
            )
        except Exception as e:
            logger.warning(f"Не удалось создать presigned URL: {e}")
            return None

    def _r2_head(self, key: str) -> bool:
        if not self.s3:
            return False
        try:
            self.s3.head_object(Bucket=R2_BUCKET, Key=key)
            return True
        except Exception:
            return False

    def _r2_upload_file(self, local_path: str, key: str, content_type: str = "audio/mpeg") -> None:
        if not self.s3:
            return
        try:
            extra = {"ContentType": content_type, "ACL": "private"}
            self.s3.upload_file(local_path, R2_BUCKET, key, ExtraArgs=extra)
            logger.info(f"⬆️ Загружено в R2: s3://{R2_BUCKET}/{key}")
        except Exception as e:
            logger.error(f"Ошибка загрузки в R2: {e}")

    # ========== Invidious API helpers ==========

    async def _get_invidious_metadata(self, video_id: str) -> Optional[Dict]:
        """Получает метаданные видео через Invidious API"""
        for base in YT_INVIDIOUS_INSTANCES:
            try:
                url = f"{base.rstrip('/')}/api/v1/videos/{video_id}"
                proxies = self.tor.get_requests_proxies()

                response = requests.get(url, timeout=30, proxies=proxies)
                if response.status_code == 200:
                    return response.json()
            except Exception as e:
                logger.warning(f"Invidious API недоступен {base}: {e}")
                continue
        return None

    async def _get_invidious_subtitles(self, video_id: str) -> Optional[str]:
        """Получает субтитры через Invidious API"""
        metadata = await self._get_invidious_metadata(video_id)
        if not metadata:
            return None

        # Ищем субтитры
        captions = metadata.get('captions', [])
        if not captions:
            return None

        # Приоритет языков
        preferred_langs = ['ru', 'en', 'en-US', 'ru-RU']
        caption_url = None

        # Сначала ищем предпочитаемые языки
        for lang in preferred_langs:
            for caption in captions:
                if caption.get('languageCode', '').startswith(lang):
                    caption_url = caption.get('url')
                    break
            if caption_url:
                break

        # Если не нашли, берем первые доступные
        if not caption_url and captions:
            caption_url = captions[0].get('url')

        if not caption_url:
            return None

        # Скачиваем субтитры
        try:
            # Обычно это относительный URL, добавляем базу
            if caption_url.startswith('/'):
                for base in YT_INVIDIOUS_INSTANCES:
                    try:
                        full_url = f"{base.rstrip('/')}{caption_url}"
                        proxies = self.tor.get_requests_proxies()
                        response = requests.get(full_url, timeout=30, proxies=proxies)
                        if response.status_code == 200:
                            return self._parse_vtt_subtitles(response.text)
                    except Exception:
                        continue
            else:
                proxies = self.tor.get_requests_proxies()
                response = requests.get(caption_url, timeout=30, proxies=proxies)
                if response.status_code == 200:
                    return self._parse_vtt_subtitles(response.text)

        except Exception as e:
            logger.warning(f"Ошибка загрузки субтитров через Invidious: {e}")

        return None

    def _parse_vtt_subtitles(self, vtt_content: str) -> str:
        """Парсит VTT субтитры в простой текст"""
        lines = vtt_content.split('\n')
        text_parts = []

        for line in lines:
            line = line.strip()
            # Пропускаем заголовки VTT и временные метки
            if (line and
                    not line.startswith('WEBVTT') and
                    not line.startswith('NOTE') and
                    not '-->' in line and
                    not line.isdigit() and
                    not re.match(r'^\d+:\d+', line)):

                # Очистка от HTML тегов
                clean_line = re.sub(r'<[^>]+>', '', line)
                if clean_line.strip():
                    text_parts.append(clean_line.strip())

        full_text = ' '.join(text_parts)
        # Легкая очистка
        full_text = re.sub(r'\s+', ' ', full_text)
        full_text = re.sub(r'\[[^\]]*\]|\([^)]*\)|♪[^♪]*♪', '', full_text)
        full_text = re.sub(r'\s+', ' ', full_text).strip()

        return full_text

    # ========== Subtitles ==========

    async def get_video_info(self, url: str) -> Dict[str, Any]:
        if not self.is_youtube_url(url):
            raise SmartVideoError("Поддерживается только YouTube")
        video_id = self.extract_video_id(url)
        if not video_id:
            raise SmartVideoError("Не удалось извлечь ID видео")
        return {"video_id": video_id, "url": url, "platform": "YouTube"}

    async def get_transcript_text(self, url: str, languages: Optional[List[str]] = None) -> Tuple[str, str]:
        if not self.is_youtube_url(url):
            raise SmartVideoError("Поддерживается только YouTube")

        video_id = self.extract_video_id(url)
        if not video_id:
            raise SmartVideoError("Не удалось извлечь ID видео")

        if languages is None:
            languages = ['ru', 'en', 'en-US', 'ru-RU']

        # Сначала пробуем через обычный API
        if self.subtitles_available:
            try:
                loop = asyncio.get_event_loop()
                transcript_text = await loop.run_in_executor(
                    self.executor,
                    self._get_subtitles_sync,
                    video_id,
                    languages
                )
                logger.info(f"✅ Субтитры получены через API для {video_id}, длина: {len(transcript_text)} символов")
                return transcript_text, 'subtitles'
            except (NoTranscriptFound, TranscriptsDisabled) as e:
                logger.info(f"❌ Субтитры через API не найдены для {video_id}: {e}")
            except Exception as e:
                logger.warning(f"Ошибка получения субтитров через API: {e}")

        # Fallback через Invidious
        logger.info(f"🔄 Пробуем получить субтитры через Invidious для {video_id}")
        invidious_text = await self._get_invidious_subtitles(video_id)
        if invidious_text and len(invidious_text.strip()) > 50:
            logger.info(f"✅ Субтитры получены через Invidious для {video_id}, длина: {len(invidious_text)} символов")
            return invidious_text, 'subtitles_invidious'

        raise SubtitleNotFoundError(f"Субтитры не найдены ни через API, ни через Invidious")

    def _get_subtitles_sync(self, video_id: str, languages: List[str]) -> str:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript = None
        for lang in languages:
            try:
                transcript = transcript_list.find_transcript([lang])
                break
            except NoTranscriptFound:
                continue
        if not transcript:
            available_transcripts = list(transcript_list)
            if available_transcripts:
                transcript = available_transcripts[0]
            else:
                raise NoTranscriptFound(video_id)

        transcript_data = transcript.fetch()
        text_parts = [item.get('text', '').strip() for item in transcript_data if item.get('text', '').strip()]
        full_text = ' '.join(text_parts)

        # легкая очистка
        full_text = re.sub(r'\s+', ' ', full_text)
        full_text = re.sub(r'\[[^\]]*\]|\([^)]*\)|♪[^♪]*♪', '', full_text)
        full_text = re.sub(r'\s+', ' ', full_text).strip()
        return full_text

    # ========== Download (with R2 cache) ==========

    async def download_audio_as_fallback(self, url: str, codec: str = "mp3", abr: str = "192") -> str:
        """
        Скачивает аудио локально (для транскрипции), параллельно пушит в R2 (кеш).
        Возвращает локальный путь к .mp3.
        """
        if not self.download_available:
            raise DownloadError("yt-dlp не установлен")
        if not self.is_youtube_url(url):
            raise SmartVideoError("Поддерживается только YouTube")

        video_id = self.extract_video_id(url)
        if not video_id:
            raise SmartVideoError("Не удалось извлечь ID видео")

        os.makedirs(AUDIO_STORAGE_DIR, exist_ok=True)
        cleanup_old_audio_files()

        # Ключ в R2
        r2_key = self._r2_key_for_audio(video_id, codec=codec)
        r2_url_existing = self._r2_url_for_key(r2_key) if self._r2_head(r2_key) else None

        # Локальный путь
        local_path = os.path.join(AUDIO_STORAGE_DIR, f"{video_id}.mp3")

        # Уже скачан локально?
        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
            logger.info(f"✅ Локальный файл уже есть: {local_path}")
            # Если в R2 нет — зальем
            if not r2_url_existing and self.s3:
                self._r2_upload_file(local_path, r2_key, content_type="audio/mpeg")
            return local_path

        # Автоматическая смена IP через Tor каждые 5 минут
        if self.tor.is_running() and time.time() - self.tor.last_ip_change > 300:
            await self.tor.change_ip()

        # Иначе качаем.
        loop = asyncio.get_event_loop()
        try:
            path = await loop.run_in_executor(
                self.executor,
                self._download_audio_sync_with_fallbacks,
                url,
                local_path,
                codec,
                abr
            )
            # Успех → заливаем в R2
            if self.s3:
                self._r2_upload_file(path, r2_key, content_type="audio/mpeg")
            return path
        except YouTubeBlockedError as e:
            logger.error(f"Блокировка YouTube/IP: {e}")
            raise
        except Exception as e:
            logger.error(f"Ошибка загрузки аудио для {video_id}: {e}")
            raise DownloadError(f"Не удалось загрузить аудио: {str(e)}")

    def _download_audio_sync_with_fallbacks(self, url: str, local_path: str, codec: str, abr: str) -> str:
        """
        Порядок:
        1) через Tor (если включен),
        2) прямой YouTube (при наличии куки/прокси),
        3) через Invidious инстансы.
        """

        # Базовые опции yt-dlp
        def _base_opts(out_path: str) -> dict:
            opts = {
                "format": "bestaudio/best",
                "outtmpl": out_path.replace(".mp3", "") + ".%(ext)s",
                "quiet": True,
                "noprogress": True,
                "no_warnings": True,
                "noplaylist": True,
                "retries": 3,
                "geo_bypass": True,
                "user_agent": YT_DLP_UA,
                "http_headers": {
                    "Referer": "https://www.youtube.com/",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "*/*",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Origin": "https://www.youtube.com",
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-origin",
                    "Pragma": "no-cache",
                    "Cache-Control": "no-cache",
                },
                "postprocessors": [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': codec,
                    'preferredquality': abr,
                }],
                "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
                "concurrent_fragment_downloads": 1,
                "socket_timeout": 60,
            }
            # Куки
            if YT_COOKIES_FILE and os.path.exists(YT_COOKIES_FILE):
                opts["cookiefile"] = YT_COOKIES_FILE
            return opts

        # 1) Через Tor (если запущен)
        if self.tor.is_running():
            tor_opts = _base_opts(local_path)
            tor_proxy = self.tor.get_proxy_config()
            if tor_proxy:
                tor_opts["proxy"] = tor_proxy

            try:
                logger.info(f"🧅 Пробуем скачать через Tor: {self.tor.current_ip}")
                with yt_dlp.YoutubeDL(tor_opts) as ydl:
                    ydl.download([url])
                final = self._resolve_final_mp3_path(local_path)
                if not os.path.exists(final):
                    raise DownloadError("yt-dlp (Tor) завершился без итогового файла")
                logger.info(f"✅ Скачано через Tor: {final}")
                return final
            except Exception as e1:
                msg = str(e1).lower()
                logger.warning(f"⚠️ Tor путь не удался: {e1}")
                # Если через Tor не получилось, пробуем сменить IP и повторить
                if "403" in msg or "forbidden" in msg or "429" in msg:
                    # Создаем новый event loop для синхронного контекста
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        ip_changed = loop.run_until_complete(self.tor.change_ip())
                        loop.close()

                        if ip_changed:
                            try:
                                logger.info(f"🔄 Повторяем через Tor с новым IP: {self.tor.current_ip}")
                                with yt_dlp.YoutubeDL(tor_opts) as ydl:
                                    ydl.download([url])
                                final = self._resolve_final_mp3_path(local_path)
                                if os.path.exists(final):
                                    logger.info(f"✅ Скачано через Tor (повтор): {final}")
                                    return final
                            except Exception as e2:
                                logger.warning(f"⚠️ Повтор через Tor тоже не удался: {e2}")
                    except Exception as tor_error:
                        logger.warning(f"⚠️ Ошибка смены IP через Tor: {tor_error}")

        # 2) Прямой YouTube (если есть прокси или куки)
        direct_opts = _base_opts(local_path)
        if YT_PROXY:
            direct_opts["proxy"] = YT_PROXY

        try:
            logger.info("🎬 Пробуем прямой YouTube")
            with yt_dlp.YoutubeDL(direct_opts) as ydl:
                ydl.download([url])
            final = self._resolve_final_mp3_path(local_path)
            if not os.path.exists(final):
                raise DownloadError("yt-dlp завершился без итогового файла")
            logger.info(f"✅ Скачано напрямую: {final}")
            return final
        except Exception as e1:
            msg = str(e1).lower()
            logger.warning(f"⚠️ Прямой путь не удался: {e1}")
            if "403" in msg or "forbidden" in msg or "http error 429" in msg or "too many requests" in msg:
                pass  # Переходим к Invidious

        # 3) Через Invidious инстансы
        return self._download_via_invidious(url, local_path, codec, abr)

    def _download_via_invidious(self, url: str, local_path: str, codec: str, abr: str) -> str:
        # Преобразуем youtube URL в invidious URLs и пытаемся по очереди
        vid = self.extract_video_id(url)
        if not vid:
            raise DownloadError("Не удалось извлечь ID видео для Invidious")

        last_err = None
        for base in YT_INVIDIOUS_INSTANCES:
            inv_url = f"{base.rstrip('/')}/watch?v={vid}"
            opts = {
                "format": "bestaudio/best",
                "outtmpl": local_path.replace(".mp3", "") + ".%(ext)s",
                "quiet": True,
                "noprogress": True,
                "no_warnings": True,
                "noplaylist": True,
                "retries": 2,
                "user_agent": YT_DLP_UA,
                "postprocessors": [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': codec,
                    'preferredquality': abr,
                }],
                "concurrent_fragment_downloads": 1,
                "socket_timeout": 45,
            }

            # Добавляем Tor прокси если доступен
            tor_proxy = self.tor.get_proxy_config()
            if tor_proxy:
                opts["proxy"] = tor_proxy
            elif YT_PROXY:
                opts["proxy"] = YT_PROXY

            try:
                logger.info(f"🔄 Пробуем Invidious: {base}")
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([inv_url])
                final = self._resolve_final_mp3_path(local_path)
                if not os.path.exists(final):
                    raise DownloadError("yt-dlp (Invidious) завершился без итогового файла")
                logger.info(f"✅ Скачано через Invidious: {base}")
                return final
            except Exception as e:
                last_err = e
                logger.warning(f"⚠️ Invidious инстанс упал/недоступен: {base} → {e}")

        if last_err:
            raise YouTubeBlockedError(f"Не удалось скачать ни напрямую, ни через Invidious: {last_err}")
        raise YouTubeBlockedError("Не удалось скачать ни напрямую, ни через Invidious (неизвестная ошибка)")

    @staticmethod
    def _resolve_final_mp3_path(local_path_requested: str) -> str:
        """
        yt-dlp пишет во временный файл с исходным расширением (.webm/.m4a),
        затем постпроцессором конвертирует в mp3.
        Ищем результат с .mp3.
        """
        base = os.path.splitext(local_path_requested)[0]
        final = base + ".mp3"
        return final

    # ========== Smart entry ==========

    async def get_text_smart(self, url: str, prefer_subtitles: bool = True) -> Tuple[str, str, Dict[str, Any]]:
        """
        1) Если есть субтитры → возвращаем текст, 'subtitles', метаданные.
        2) Иначе → скачаем аудио локально, одновременно закешируем в R2, вернём локальный путь, 'audio_file', метаданные.
           В метаданных будет r2_url (если R2 настроен) для быстрой отдачи клиенту.
        """
        if not self.is_youtube_url(url):
            raise SmartVideoError("Поддерживается только YouTube")

        info = await self.get_video_info(url)
        video_id = info["video_id"]

        # Сначала субтитры (если просили и есть библиотека)
        if prefer_subtitles and (self.subtitles_available or USE_TOR):
            try:
                text, source = await self.get_transcript_text(url)
                if text and len(text.strip()) > 50:
                    return text, source, {
                        'method': 'subtitles',
                        'video_id': video_id,
                        'platform': 'YouTube',
                        'length': len(text),
                        'words': len(text.split()),
                        'source': source
                    }
            except SubtitleNotFoundError:
                pass
            except Exception as e:
                logger.warning(f"Субтитры недоступны: {e}")

        # Иначе — аудио
        local_audio_path = await self.download_audio_as_fallback(url)
        # Сформируем r2_url (если уже в R2), чтобы ты мог отправить клиенту
        r2_url = None
        if self.s3:
            key = self._r2_key_for_audio(video_id)
            if self._r2_head(key):
                r2_url = self._r2_url_for_key(key)

        return local_audio_path, 'audio_file', {
            'method': 'audio_download',
            'video_id': video_id,
            'platform': 'YouTube',
            'audio_path': local_audio_path,
            'requires_transcription': True,
            'r2_url': r2_url,
            'tor_used': self.tor.is_running(),
            'current_ip': self.tor.current_ip if self.tor.is_running() else None
        }

    # ========== Cleanup / Context manager ==========

    def cleanup_temp_files(self, file_path: str):
        """Удаляет файл когда больше не нужен."""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Файл удален: {file_path}")
        except Exception as e:
            logger.warning(f"Не удалось удалить {file_path}: {e}")

    def get_capabilities(self) -> Dict[str, bool]:
        return {
            'subtitles': self.subtitles_available,
            'subtitles_invidious': True,  # Всегда доступно через Invidious API
            'audio_download': self.download_available,
            'youtube_only': True,
            'r2_cache': self.s3 is not None,
            'tor_available': self.tor.is_enabled,
            'tor_running': self.tor.is_running()
        }

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.tor.stop()
        self.executor.shutdown(wait=True)


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
