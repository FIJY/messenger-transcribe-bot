# services/youtube_service.py - Исправленный сервис для работы с YouTube
import os
import tempfile
import logging
import asyncio
from typing import Dict, Optional, List
import yt_dlp

logger = logging.getLogger(__name__)


class YouTubeService:
    """Сервис для работы с YouTube через yt-dlp с поддержкой куков"""

    def __init__(self):
        self.cookies_file = None
        self._setup_cookies()

    def _setup_cookies(self):
        """Настройка файла с куками из переменной окружения"""
        cookies_data = os.getenv('YT_COOKIES_DATA')

        if cookies_data:
            try:
                # Создаем временный файл для куков
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
                    f.write(cookies_data)
                    self.cookies_file = f.name
                logger.info(f"✅ Куки YouTube загружены в {self.cookies_file}")
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки куков: {e}")
        else:
            logger.warning("⚠️ YT_COOKIES_DATA не найден")

    def get_ytdlp_options(self, format_selector: str = 'bestaudio') -> Dict:
        """Получить настройки yt-dlp с куками"""
        options = {
            'format': format_selector,
            'noplaylist': True,
            'extract_flat': False,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['ru', 'en', 'auto'],
            'ignoreerrors': False,
            'no_warnings': False,

            # Обновленные заголовки как в вашем рабочем примере
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate'
            },

            # Настройки повторных попыток
            'extractor_retries': 3,
            'fragment_retries': 3,
            'retry_sleep_functions': {
                'http': lambda n: min(2 ** n, 10),
                'fragment': lambda n: min(2 ** n, 10)
            }
        }

        # Добавляем куки если есть
        if self.cookies_file and os.path.exists(self.cookies_file):
            options['cookiefile'] = self.cookies_file
            logger.info(f"🍪 Используем куки: {self.cookies_file}")

        # Tor прокси если включен
        if os.getenv('USE_TOR', 'false').lower() == 'true':
            proxy_url = os.getenv('YT_PROXY', 'socks5://127.0.0.1:9050')
            options['proxy'] = proxy_url
            logger.info(f"🔄 Используем Tor прокси: {proxy_url}")

        return options

    async def download_audio(self, video_url: str, output_path: str) -> Optional[Dict]:
        """Скачать аудио из YouTube видео"""
        try:
            options = self.get_ytdlp_options('bestaudio/best')
            options.update({
                'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
                'extractaudio': True,
                'audioformat': 'mp3',
                'writethumbnail': False,
                'writeinfojson': True
            })

            logger.info(f"🎵 Скачиваем аудио: {video_url}")

            with yt_dlp.YoutubeDL(options) as ydl:
                # Выполняем в отдельном потоке чтобы не блокировать
                def _download():
                    info = ydl.extract_info(video_url, download=True)
                    return info

                loop = asyncio.get_event_loop()
                info = await loop.run_in_executor(None, _download)

                if info:
                    logger.info(f"✅ Аудио скачано: {info.get('title', 'Unknown')}")
                    return info

        except Exception as e:
            logger.error(f"❌ Ошибка скачивания аудио: {e}")
            return None

    async def get_video_info(self, video_url: str) -> Optional[Dict]:
        """Получить информацию о видео без скачивания"""
        try:
            options = self.get_ytdlp_options()
            options['skip_download'] = True

            logger.info(f"ℹ️ Получаем инфо: {video_url}")

            with yt_dlp.YoutubeDL(options) as ydl:
                def _extract():
                    return ydl.extract_info(video_url, download=False)

                loop = asyncio.get_event_loop()
                info = await loop.run_in_executor(None, _extract)
                return info

        except Exception as e:
            logger.error(f"❌ Ошибка получения информации: {e}")
            return None

    async def extract_subtitles(self, video_url: str) -> Optional[List[Dict]]:
        """Извлечь субтитры из видео"""
        try:
            info = await self.get_video_info(video_url)
            if not info:
                return None

            subtitles = []

            # Автоматические субтитры
            if 'automatic_captions' in info:
                for lang, subs in info['automatic_captions'].items():
                    for sub in subs:
                        if sub.get('ext') in ['vtt', 'srv1', 'srv2', 'srv3']:
                            subtitles.append({
                                'language': lang,
                                'url': sub['url'],
                                'auto': True,
                                'format': sub.get('ext', 'unknown')
                            })

            # Ручные субтитры
            if 'subtitles' in info:
                for lang, subs in info['subtitles'].items():
                    for sub in subs:
                        if sub.get('ext') in ['vtt', 'srv1', 'srv2', 'srv3']:
                            subtitles.append({
                                'language': lang,
                                'url': sub['url'],
                                'auto': False,
                                'format': sub.get('ext', 'unknown')
                            })

            logger.info(f"📝 Найдено {len(subtitles)} субтитров")
            return subtitles

        except Exception as e:
            logger.error(f"❌ Ошибка извлечения субтитров: {e}")
            return None

    def cleanup(self):
        """Очистка временных файлов"""
        if self.cookies_file and os.path.exists(self.cookies_file):
            try:
                os.unlink(self.cookies_file)
                logger.info("🧹 Временный файл куков удален")
            except Exception as e:
                logger.error(f"❌ Ошибка удаления куков: {e}")


# Пример использования в вашем smart_video_service.py
async def enhanced_youtube_download(video_url: str):
    """Улучшенная загрузка с куками"""

    youtube_service = YouTubeService()

    try:
        # Сначала пробуем получить субтитры
        subtitles = await youtube_service.extract_subtitles(video_url)

        if subtitles:
            logger.info("✅ Субтитры найдены, скачиваем")
            return subtitles

        # Если субтитров нет, скачиваем аудио
        temp_dir = tempfile.mkdtemp()
        audio_info = await youtube_service.download_audio(video_url, temp_dir)

        if audio_info:
            logger.info("✅ Аудио скачано для транскрипции")
            return audio_info

        return None

    finally:
        youtube_service.cleanup()