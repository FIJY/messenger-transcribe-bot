"""
Tor Service для обхода YouTube блокировок
Автоматически меняет IP каждые 10 минут
"""
import os
import subprocess
import time
import logging
import asyncio
from typing import Optional
import requests
from stem import Signal
from stem.control import Controller

logger = logging.getLogger(__name__)


class TorService:
    def __init__(self, tor_port: int = 9050, control_port: int = 9051):
        self.tor_port = tor_port
        self.control_port = control_port
        self.tor_process = None
        self.last_ip_change = 0
        self.current_ip = None

        # Tor конфигурация для yt-dlp
        self.proxy_config = {
            'proxy': f'socks5://127.0.0.1:{tor_port}',
            'http_proxy': f'socks5://127.0.0.1:{tor_port}',
            'https_proxy': f'socks5://127.0.0.1:{tor_port}',
        }

    async def start_tor(self) -> bool:
        """Запускает Tor daemon"""
        try:
            # Проверяем, установлен ли Tor
            result = subprocess.run(['which', 'tor'], capture_output=True)
            if result.returncode != 0:
                logger.error("❌ Tor не установлен. Установите: apt-get install tor")
                return False

            # Создаем конфиг Tor
            await self._create_tor_config()

            # Запускаем Tor
            logger.info(f"🧅 Запускаем Tor на портах {self.tor_port}/{self.control_port}")
            self.tor_process = subprocess.Popen([
                'tor',
                '-f', '/tmp/torrc',
                '--quiet'
            ])

            # Ждем запуска
            await asyncio.sleep(10)

            # Проверяем соединение
            if await self._test_tor_connection():
                logger.info(f"✅ Tor запущен успешно, IP: {self.current_ip}")
                return True
            else:
                logger.error("❌ Tor запустился, но соединение не работает")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка запуска Tor: {e}")
            return False

    async def _create_tor_config(self):
        """Создает конфигурацию Tor"""
        config = f"""
# Tor configuration for YouTube bot
SocksPort {self.tor_port}
ControlPort {self.control_port}
DataDirectory /tmp/tor_data
ExitNodes {{us}},{{de}},{{nl}},{{se}},{{ch}}
StrictNodes 1
NewCircuitPeriod 600
MaxCircuitDirtiness 600
"""

        os.makedirs('/tmp/tor_data', exist_ok=True)
        with open('/tmp/torrc', 'w') as f:
            f.write(config)

    async def _test_tor_connection(self) -> bool:
        """Тестирует Tor соединение"""
        try:
            proxies = {
                'http': f'socks5://127.0.0.1:{self.tor_port}',
                'https': f'socks5://127.0.0.1:{self.tor_port}'
            }

            response = requests.get(
                'https://httpbin.org/ip',
                proxies=proxies,
                timeout=30
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
        try:
            logger.info("🔄 Меняем IP через Tor...")

            with Controller.from_port(port=self.control_port) as controller:
                controller.authenticate()
                controller.signal(Signal.NEWNYM)

            # Ждем смены IP
            await asyncio.sleep(5)

            # Проверяем новый IP
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

    async def get_yt_dlp_config(self) -> dict:
        """Возвращает конфигурацию yt-dlp с Tor прокси"""

        # Автоматическая смена IP каждые 10 минут
        if time.time() - self.last_ip_change > 600:  # 10 минут
            await self.change_ip()

        return {
            'proxy': f'socks5://127.0.0.1:{self.tor_port}',
            'socket_timeout': 60,
            'retries': 2,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],
                }
            }
        }

    def get_requests_proxies(self) -> dict:
        """Возвращает прокси для requests"""
        return {
            'http': f'socks5://127.0.0.1:{self.tor_port}',
            'https': f'socks5://127.0.0.1:{self.tor_port}'
        }

    async def stop(self):
        """Останавливает Tor"""
        if self.tor_process:
            logger.info("🛑 Останавливаем Tor...")
            self.tor_process.terminate()
            self.tor_process.wait()
            self.tor_process = None

    def is_running(self) -> bool:
        """Проверяет, запущен ли Tor"""
        return self.tor_process is not None and self.tor_process.poll() is None


# Глобальный экземпляр для использования в боте
tor_service = TorService()


async def init_tor_if_needed() -> bool:
    """Инициализирует Tor если нужно обходить блокировки"""

    # Проверяем настройки
    use_tor = os.getenv("USE_TOR", "false").lower() == "true"

    if not use_tor:
        logger.info("🧅 Tor отключен в настройках")
        return False

    if tor_service.is_running():
        logger.info("🧅 Tor уже запущен")
        return True

    logger.info("🧅 Инициализируем Tor для обхода YouTube блокировок...")
    return await tor_service.start_tor()


async def get_tor_yt_dlp_config() -> Optional[dict]:
    """Получает конфигурацию yt-dlp с Tor если он запущен"""
    if tor_service.is_running():
        return await tor_service.get_yt_dlp_config()
    return None