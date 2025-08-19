# monitoring.py - Система мониторинга ресурсов и алертов
import logging
import asyncio
import psutil
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from celery import Celery
from config import settings

logger = logging.getLogger(__name__)


class ResourceMonitor:
    """Мониторинг системных ресурсов"""

    def __init__(self):
        self.memory_threshold = 80  # % использования памяти
        self.cpu_threshold = 85  # % использования CPU
        self.disk_threshold = 90  # % использования диска
        self.alerts_sent = {}  # Кэш отправленных алертов

    def get_system_stats(self) -> Dict[str, Any]:
        """Получает статистику системы"""
        try:
            # Память
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_available_gb = memory.available / (1024 ** 3)

            # CPU
            cpu_percent = psutil.cpu_percent(interval=1)

            # Диск
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            disk_free_gb = disk.free / (1024 ** 3)

            # Процессы
            process_count = len(psutil.pids())

            return {
                'timestamp': datetime.utcnow().isoformat(),
                'memory': {
                    'percent': memory_percent,
                    'available_gb': round(memory_available_gb, 2),
                    'total_gb': round(memory.total / (1024 ** 3), 2)
                },
                'cpu': {
                    'percent': cpu_percent,
                    'count': psutil.cpu_count()
                },
                'disk': {
                    'percent': round(disk_percent, 1),
                    'free_gb': round(disk_free_gb, 2),
                    'total_gb': round(disk.total / (1024 ** 3), 2)
                },
                'processes': process_count
            }
        except Exception as e:
            logger.error(f"Ошибка получения системной статистики: {e}")
            return {}

    def check_alerts(self, stats: Dict[str, Any]) -> list:
        """Проверяет пороги и возвращает алерты"""
        alerts = []
        current_time = datetime.utcnow()

        # Проверяем память
        if stats.get('memory', {}).get('percent', 0) > self.memory_threshold:
            alert_key = 'high_memory'
            if self._should_send_alert(alert_key, current_time):
                alerts.append({
                    'type': 'HIGH_MEMORY',
                    'message': f"🚨 Высокое использование памяти: {stats['memory']['percent']}%",
                    'severity': 'WARNING',
                    'timestamp': current_time.isoformat()
                })
                self.alerts_sent[alert_key] = current_time

        # Проверяем CPU
        if stats.get('cpu', {}).get('percent', 0) > self.cpu_threshold:
            alert_key = 'high_cpu'
            if self._should_send_alert(alert_key, current_time):
                alerts.append({
                    'type': 'HIGH_CPU',
                    'message': f"🚨 Высокая загрузка CPU: {stats['cpu']['percent']}%",
                    'severity': 'WARNING',
                    'timestamp': current_time.isoformat()
                })
                self.alerts_sent[alert_key] = current_time

        # Проверяем диск
        if stats.get('disk', {}).get('percent', 0) > self.disk_threshold:
            alert_key = 'high_disk'
            if self._should_send_alert(alert_key, current_time):
                alerts.append({
                    'type': 'HIGH_DISK',
                    'message': f"🚨 Мало места на диске: {stats['disk']['percent']}%",
                    'severity': 'CRITICAL',
                    'timestamp': current_time.isoformat()
                })
                self.alerts_sent[alert_key] = current_time

        return alerts

    def _should_send_alert(self, alert_key: str, current_time: datetime) -> bool:
        """Проверяет, нужно ли отправлять алерт (избегаем спам)"""
        if alert_key not in self.alerts_sent:
            return True

        # Отправляем алерт не чаще раза в 15 минут
        last_sent = self.alerts_sent[alert_key]
        return (current_time - last_sent) > timedelta(minutes=15)


class CeleryMonitor:
    """Мониторинг состояния Celery"""

    def __init__(self):
        from services.transcription import celery_app
        self.celery_app = celery_app

    def get_worker_stats(self) -> Dict[str, Any]:
        """Получает статистику воркеров Celery"""
        try:
            # Инспектируем активных воркеров
            inspect = self.celery_app.control.inspect()

            # Получаем список активных воркеров
            active_workers = inspect.active()
            if not active_workers:
                return {'error': 'No active workers found'}

            # Статистика по воркерам
            stats = inspect.stats()
            reserved_tasks = inspect.reserved()
            active_tasks = inspect.active()

            worker_info = {}
            for worker_name in active_workers.keys():
                worker_info[worker_name] = {
                    'active_tasks': len(active_tasks.get(worker_name, [])),
                    'reserved_tasks': len(reserved_tasks.get(worker_name, [])),
                    'stats': stats.get(worker_name, {}),
                    'status': 'online'
                }

            return {
                'timestamp': datetime.utcnow().isoformat(),
                'workers': worker_info,
                'total_workers': len(active_workers)
            }

        except Exception as e:
            logger.error(f"Ошибка получения статистики Celery: {e}")
            return {'error': str(e)}

    def get_queue_stats(self) -> Dict[str, Any]:
        """Получает статистику очередей"""
        try:
            # Подключаемся к Redis для проверки очередей
            import redis
            redis_client = redis.from_url(settings.REDIS_URL)

            # Проверяем размер очереди
            queue_length = redis_client.llen('celery')

            # Проверяем состояние Redis
            redis_info = redis_client.info()

            return {
                'timestamp': datetime.utcnow().isoformat(),
                'queue_length': queue_length,
                'redis_connected_clients': redis_info.get('connected_clients', 0),
                'redis_used_memory': redis_info.get('used_memory_human', 'unknown'),
                'redis_uptime_seconds': redis_info.get('uptime_in_seconds', 0)
            }

        except Exception as e:
            logger.error(f"Ошибка получения статистики очереди: {e}")
            return {'error': str(e)}


class DatabaseMonitor:
    """Мониторинг базы данных"""

    async def get_db_stats(self) -> Dict[str, Any]:
        """Получает статистику MongoDB"""
        try:
            from services.database import DatabaseService
            db_service = DatabaseService()
            await db_service.initialize()

            # Статистика коллекций
            users_count = await db_service.db.users.count_documents({})
            audio_files_count = await db_service.db.audio_files.count_documents({})
            transcriptions_count = await db_service.db.transcriptions.count_documents({})

            # Статистика за последние 24 часа
            yesterday = datetime.utcnow() - timedelta(days=1)
            new_users_today = await db_service.db.users.count_documents({
                'created_at': {'$gte': yesterday}
            })
            new_files_today = await db_service.db.audio_files.count_documents({
                'created_at': {'$gte': yesterday}
            })

            # Статистика обработки
            processing_stats = await db_service.db.audio_files.aggregate([
                {'$group': {
                    '_id': '$status',
                    'count': {'$sum': 1}
                }}
            ]).to_list(None)

            status_counts = {item['_id']: item['count'] for item in processing_stats}

            await db_service.close()

            return {
                'timestamp': datetime.utcnow().isoformat(),
                'collections': {
                    'users': users_count,
                    'audio_files': audio_files_count,
                    'transcriptions': transcriptions_count
                },
                'today': {
                    'new_users': new_users_today,
                    'new_files': new_files_today
                },
                'processing_status': status_counts
            }

        except Exception as e:
            logger.error(f"Ошибка получения статистики БД: {e}")
            return {'error': str(e)}


class AlertManager:
    """Менеджер алертов"""

    def __init__(self):
        self.telegram_client = None
        self.admin_chat_ids = []  # ID чатов администраторов

    async def send_alert(self, alert: Dict[str, Any]):
        """Отправляет алерт администраторам"""
        if not self.admin_chat_ids:
            logger.warning("Не настроены ID администраторов для алертов")
            return

        try:
            if not self.telegram_client:
                from services.telegram_client import TelegramClient
                self.telegram_client = TelegramClient(settings.TELEGRAM_TOKEN)

            message = f"""🚨 **СИСТЕМНЫЙ АЛЕРТ**

**Тип:** {alert['type']}
**Серьезность:** {alert['severity']}
**Время:** {alert['timestamp']}

{alert['message']}

---
_TranscribeBot Monitoring_"""

            for admin_id in self.admin_chat_ids:
                try:
                    await self.telegram_client.send_message(admin_id, message)
                except Exception as e:
                    logger.error(f"Не удалось отправить алерт admin {admin_id}: {e}")

        except Exception as e:
            logger.error(f"Ошибка отправки алерта: {e}")


class MonitoringService:
    """Основной сервис мониторинга"""

    def __init__(self):
        self.resource_monitor = ResourceMonitor()
        self.celery_monitor = CeleryMonitor()
        self.db_monitor = DatabaseMonitor()
        self.alert_manager = AlertManager()
        self.is_running = False

    async def start_monitoring(self, interval: int = 60):
        """Запуск мониторинга с заданным интервалом (секунды)"""
        logger.info(f"🔍 Запуск мониторинга (интервал: {interval}с)")
        self.is_running = True

        while self.is_running:
            try:
                # Собираем статистику
                system_stats = self.resource_monitor.get_system_stats()
                celery_stats = self.celery_monitor.get_worker_stats()
                queue_stats = self.celery_monitor.get_queue_stats()
                db_stats = await self.db_monitor.get_db_stats()

                # Логируем статистику
                logger.info(f"📊 System: CPU {system_stats.get('cpu', {}).get('percent', 0)}%, "
                            f"RAM {system_stats.get('memory', {}).get('percent', 0)}%, "
                            f"Disk {system_stats.get('disk', {}).get('percent', 0)}%")

                logger.info(f"🔧 Celery: Workers {celery_stats.get('total_workers', 0)}, "
                            f"Queue {queue_stats.get('queue_length', 0)}")

                # Проверяем алерты
                alerts = self.resource_monitor.check_alerts(system_stats)

                # Проверяем состояние воркеров
                if celery_stats.get('total_workers', 0) == 0:
                    alerts.append({
                        'type': 'NO_WORKERS',
                        'message': '🚨 Нет активных Celery воркеров!',
                        'severity': 'CRITICAL',
                        'timestamp': datetime.utcnow().isoformat()
                    })

                # Проверяем размер очереди
                queue_length = queue_stats.get('queue_length', 0)
                if queue_length > 10:
                    alerts.append({
                        'type': 'LARGE_QUEUE',
                        'message': f'⚠️ Большая очередь задач: {queue_length}',
                        'severity': 'WARNING',
                        'timestamp': datetime.utcnow().isoformat()
                    })

                # Отправляем алерты
                for alert in alerts:
                    await self.alert_manager.send_alert(alert)
                    logger.warning(f"Отправлен алерт: {alert['message']}")

                # Ждем до следующей проверки
                await asyncio.sleep(interval)

            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга: {e}", exc_info=True)
                await asyncio.sleep(interval)

    def stop_monitoring(self):
        """Остановка мониторинга"""
        logger.info("🛑 Остановка мониторинга")
        self.is_running = False


# Функция для запуска мониторинга как отдельного процесса
async def run_monitoring():
    """Запуск мониторинга"""
    monitoring = MonitoringService()
    try:
        await monitoring.start_monitoring(interval=60)  # Проверка каждую минуту
    except KeyboardInterrupt:
        monitoring.stop_monitoring()
        logger.info("Мониторинг остановлен пользователем")


if __name__ == "__main__":
    # Запуск мониторинга
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_monitoring())