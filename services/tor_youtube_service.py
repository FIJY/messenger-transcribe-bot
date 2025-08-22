# services/tor_youtube_service.py - Интеграция рабочего Tor решения
import asyncio
import tempfile
import os
import logging
import aiohttp
import subprocess
from typing import Optional, Dict, List
import yt_dlp

logger = logging.getLogger(__name__)


class TorYouTubeService:
    """Сервис YouTube с Tor (на основе вашего рабочего bash-скрипта)"""

    def __init__(self):
        self.tor_socks = "127.0.0.1:9050"
        self.tor_control_port = "9051"
        self.max_retries = 3
        self.download_dir = "/tmp/youtube_downloads"
        self.current_ip = None

        # Создаем директорию для загрузок
        os.makedirs(self.download_dir, exist_ok=True)

    async def check_tor_status(self) -> bool:
        """Проверить статус Tor (как в вашем скрипте)"""
        try:
            # Проверяем доступность порта
            proc = await asyncio.create_subprocess_exec(
                'nc', '-z', '127.0.0.1', '9050',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()

            if proc.returncode == 0:
                logger.info("✅ Tor работает")
                return True
            else:
                logger.warning("⚠️ Tor не доступен")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка проверки Tor: {e}")
            return False

    async def get_current_ip(self) -> Optional[str]:
        """Получить текущий IP через Tor (как в bash)"""
        try:
            connector = aiohttp.TCPConnector()
            timeout = aiohttp.ClientTimeout(total=10)

            async with aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout
            ) as session:
                proxy_url = f"socks5://{self.tor_socks}"

                async with session.get(
                        'https://api.ipify.org',
                        proxy=proxy_url
                ) as response:
                    if response.status == 200:
                        ip = await response.text()
                        self.current_ip = ip.strip()
                        logger.info(f"🌐 IP через Tor: {self.current_ip}")
                        return self.current_ip

        except Exception as e:
            logger.error(f"❌ Ошибка получения IP: {e}")

        return None

    async def renew_tor_ip(self):
        """Обновить IP через Tor (SIGNAL NEWNYM из bash)"""
        try:
            # Команда как в вашем bash-скрипте
            cmd = f'echo -e \'AUTHENTICATE ""\nSIGNAL NEWNYM\nQUIT\' | nc 127.0.0.1 {self.tor_control_port}'

            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            await proc.communicate()

            # Ждем как в bash-скрипте
            await asyncio.sleep(5)

            # Проверяем новый IP
            new_ip = await self.get_current_ip()
            if new_ip and new_ip != self.current_ip:
                logger.info(f"🔄 IP обновлен: {self.current_ip} → {new_ip}")
                return True
            else:
                logger.warning("⚠️ IP не изменился")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка обновления IP: {e}")
            return False

    def get_ytdlp_options(self) -> Dict:
        """Настройки yt-dlp точно как в рабочем bash-скрипте"""
        return {
            'format': 'bestaudio/best',
            'proxy': f'socks5://{self.tor_socks}',
            'outtmpl': f'{self.download_dir}/%(title)s.%(ext)s',
            'extractaudio': True,
            'audioformat': 'mp3',
            'noplaylist': True,
            'writeinfojson': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['ru', 'en', 'auto'],
            'ignoreerrors': False,

            # Настройки для стабильности
            'extractor_retries': 3,
            'fragment_retries': 3,
            'retry_sleep_functions': {
                'http': lambda n: min(2 ** n, 10),
                'fragment': lambda n: min(2 ** n, 10)
            },

            # HTTP заголовки
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5'
            }
        }

    async def download_youtube_video(self, video_url: str) -> Optional[Dict]:
        """Скачать видео с YouTube (логика из bash-скрипта)"""

        # Проверяем Tor
        if not await self.check_tor_status():
            logger.error("❌ Tor недоступен")
            return None

        # Получаем текущий IP
        await self.get_current_ip()

        # Попытки скачивания с ретраями (как в bash)
        for attempt in range(1, self.max_retries + 1):
            logger.info(f"🎵 Скачиваем: {video_url} (попытка {attempt})")

            try:
                options = self.get_ytdlp_options()

                # Выполняем в отдельном потоке
                loop = asyncio.get_event_loop()

                def _download():
                    with yt_dlp.YoutubeDL(options) as ydl:
                        return ydl.extract_info(video_url, download=True)

                info = await loop.run_in_executor(None, _download)

                if info:
                    logger.info(f"✅ Успешно скачано: {info.get('title', 'Unknown')}")
                    return {
                        'success': True,
                        'info': info,
                        'download_path': self.download_dir,
                        'ip_used': self.current_ip
                    }

            except Exception as e:
                logger.warning(f"⚠️ Ошибка при скачивании (попытка {attempt}): {e}")

                if attempt < self.max_retries:
                    logger.info("🔄 Обновляем IP и повторяем...")
                    await self.renew_tor_ip()
                else:
                    logger.error(f"❌ Все попытки исчерпаны для: {video_url}")

        return None

    async def extract_audio_info(self, video_url: str) -> Optional[Dict]:
        """Извлечь только информацию без скачивания"""

        if not await self.check_tor_status():
            return None

        await self.get_current_ip()

        try:
            options = self.get_ytdlp_options()
            options['skip_download'] = True  # Только информация

            loop = asyncio.get_event_loop()

            def _extract():
                with yt_dlp.YoutubeDL(options) as ydl:
                    return ydl.extract_info(video_url, download=False)

            info = await loop.run_in_executor(None, _extract)

            if info:
                logger.info(f"ℹ️ Информация получена: {info.get('title', 'Unknown')}")

                # Извлекаем субтитры
                subtitles = self._extract_subtitle_urls(info)

                return {
                    'success': True,
                    'title': info.get('title'),
                    'duration': info.get('duration'),
                    'subtitles': subtitles,
                    'formats': info.get('formats', []),
                    'ip_used': self.current_ip
                }

        except Exception as e:
            logger.error(f"❌ Ошибка извлечения информации: {e}")

        return None

    def _extract_subtitle_urls(self, info: Dict) -> List[Dict]:
        """Извлечь URL субтитров"""
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

        return subtitles

    async def cleanup_downloads(self):
        """Очистка старых загрузок"""
        try:
            import shutil
            if os.path.exists(self.download_dir):
                shutil.rmtree(self.download_dir)
                os.makedirs(self.download_dir, exist_ok=True)
                logger.info("🧹 Временные файлы очищены")
        except Exception as e:
            logger.error(f"❌ Ошибка очистки: {e}")


# Интеграция в ваш smart_video_service.py
class EnhancedSmartVideoService:
    """Улучшенный сервис с интеграцией Tor YouTube"""

    def __init__(self):
        self.tor_youtube = TorYouTubeService()

    async def process_youtube_url(self, video_url: str, user_id: int) -> Dict:
        """Обработка YouTube URL с Tor"""

        logger.info(f"🎬 Обрабатываем YouTube: {video_url}")

        try:
            # Сначала пробуем получить субтитры
            info = await self.tor_youtube.extract_audio_info(video_url)

            if info and info.get('subtitles'):
                logger.info("📝 Найдены субтитры!")
                return {
                    'method': 'subtitles',
                    'data': info,
                    'success': True
                }

            # Если субтитров нет, скачиваем аудио
            logger.info("🎵 Субтитров нет, скачиваем аудио...")
            download_result = await self.tor_youtube.download_youtube_video(video_url)

            if download_result and download_result.get('success'):
                logger.info("✅ Аудио скачано для транскрипции")
                return {
                    'method': 'audio_download',
                    'data': download_result,
                    'success': True
                }

            return {
                'success': False,
                'error': 'Не удалось обработать видео'
            }

        except Exception as e:
            logger.error(f"❌ Ошибка обработки YouTube: {e}")
            return {
                'success': False,
                'error': str(e)
            }

        finally:
            # Очищаем временные файлы
            await self.tor_youtube.cleanup_downloads()


# Использование в handlers/text_handler.py
async def handle_youtube_url_with_tor(video_url: str, user_id: int):
    """Обработка YouTube через Tor (интеграция в текстовый хендлер)"""

    enhanced_service = EnhancedSmartVideoService()
    result = await enhanced_service.process_youtube_url(video_url, user_id)

    return result