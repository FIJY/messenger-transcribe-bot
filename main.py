# main.py - FastAPI сервер для Telegram бота
import logging
import os
import sys
import asyncio
import json
from datetime import datetime

# Настройте базовое логгирование, если его еще нет
logging.basicConfig(level=logging.INFO)

logging.info("================== DIAGNOSTICS ==================")
logging.info(f"USE_TOR: {os.getenv('USE_TOR')}")
logging.info(f"YT_PROXY: {os.getenv('YT_PROXY')}")
logging.info(f"YT_INVIDIOUS_INSTANCES: {os.getenv('YT_INVIDIOUS_INSTANCES')}")
logging.info(f"USE_COOKIES: {os.getenv('USE_COOKIES', 'false')}")
logging.info("=================================================")

# Проверяем и импортируем зависимости
try:
    import httpx
    from fastapi import FastAPI, Request, Response, status
    from contextlib import asynccontextmanager
    import uvicorn
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("💡 Установите зависимости: pip install -r requirements.txt")
    sys.exit(1)

from config import settings
from bot import TranscribeBot
from services.telegram_client import TelegramClient

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Глобальные переменные для хранения экземпляров
bot_instance: TranscribeBot | None = None
smart_video_service = None  # ДОБАВЛЯЕМ глобальный сервис


async def setup_webhook():
    """Установка webhook с обработкой ошибок"""
    if not settings.WEBHOOK_URL:
        logger.warning("⚠️ WEBHOOK_URL не установлен. Пропускаю настройку webhook.")
        return False

    webhook_url_path = f"/webhook/{settings.TELEGRAM_TOKEN}"
    full_webhook_url = f"{settings.WEBHOOK_URL.rstrip('/')}{webhook_url_path}"

    client = TelegramClient(settings.TELEGRAM_TOKEN)
    success = await client.set_webhook(full_webhook_url)
    await client.close()

    if success:
        logger.info(f"✅ Webhook установлен: {full_webhook_url}")
    else:
        logger.error(f"❌ Не удалось установить webhook.")

    return success


async def simple_health_check():
    """Простая проверка здоровья системы"""
    try:
        from services.smart_video_service import get_system_status

        system_status = await get_system_status()
        bot_healthy = bot_instance is not None

        overall_healthy = (
                bot_healthy and
                system_status.get("components", {}).get("yt_dlp", False)
        )

        return {
            "overall_status": "healthy" if overall_healthy else "degraded",
            "timestamp": datetime.now().isoformat(),
            "bot_initialized": bot_healthy,
            "services": {
                "telegram_bot": bot_healthy,
                "smart_video": system_status.get("components", {}),
                "tor": system_status.get("tor", {}),
                "r2": system_status.get("r2", {}),
            }
        }
    except Exception as e:
        return {
            "overall_status": "error",
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "bot_initialized": bot_instance is not None
        }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    global bot_instance, smart_video_service

    logger.info("🚀 Запуск TranscribeBot...")

    try:
        # 0. ДОБАВЛЯЕМ ПРЕДЗАГРУЗКУ СИСТЕМЫ В САМОМ НАЧАЛЕ
        logger.info("⚡ Запуск предзагрузки системы...")
        try:
            from services.smart_video_service import preload_system
            await preload_system()
            logger.info("⚡ Предзагрузка системы завершена")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка предзагрузки (продолжаем): {e}")

        # 1. СНАЧАЛА инициализируем SmartVideoService (включая Tor)
        logger.info("🔧 Инициализация SmartVideoService...")
        try:
            from services.smart_video_service import create_smart_video_service
            smart_video_service = await create_smart_video_service()
            logger.info("✅ SmartVideoService инициализирован")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации SmartVideoService: {e}")
            smart_video_service = None

        # 2. Создаем бота
        bot_instance = TranscribeBot(settings)

        # 3. СНАЧАЛА инициализируем бота (создаются все handlers)
        init_success = await bot_instance.initialize()

        # 4. ПОТОМ передаем готовый сервис (после создания handlers)
        if smart_video_service and init_success:
            bot_instance.set_video_service(smart_video_service)
            logger.info("✅ SmartVideoService передан в бот")

        if not init_success:
            logger.error("❌ Инициализация бота провалена")

        # 5. Устанавливаем webhook ПОСЛЕ полной инициализации
        if init_success:
            await setup_webhook()

        logger.info("🎉 Приложение готово к работе!")

    except Exception as e:
        logger.error(f"❌ Критическая ошибка при запуске: {e}", exc_info=True)

    yield

    # Очистка ресурсов при остановке
    logger.info("🛑 Остановка приложения...")

    # Останавливаем SmartVideoService (включая Tor)
    if smart_video_service and hasattr(smart_video_service, 'shutdown'):
        try:
            await smart_video_service.shutdown()
            logger.info("✅ SmartVideoService остановлен")
        except Exception as e:
            logger.error(f"❌ Ошибка остановки SmartVideoService: {e}")

    if bot_instance:
        await bot_instance.shutdown()


# Создание FastAPI приложения
app = FastAPI(
    title="TranscribeBot API",
    description="AI-powered transcription bot with Tor support",
    version="2.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """Главная страница с информацией о сервисе"""
    tor_status = "unknown"
    if smart_video_service and hasattr(smart_video_service, 'tor'):
        tor_status = "running" if smart_video_service.tor.is_running() else "stopped"

    return {
        "message": "🤖 TranscribeBot API активен!",
        "version": "2.0.0",
        "status": "healthy" if bot_instance else "degraded",
        "bot_initialized": bot_instance is not None,
        "tor_status": tor_status,
        "features": [
            "YouTube transcription",
            "Tor proxy support",
            "Invidious fallback",
            "R2 cloud storage",
            "Auto subtitles extraction"
        ],
        "timestamp": datetime.now().isoformat()
    }


@app.head("/")
async def root_head():
    """HEAD endpoint для health checks"""
    return Response(status_code=200)


@app.post(f"/webhook/{settings.TELEGRAM_TOKEN}")
async def telegram_webhook(request: Request):
    """Основной endpoint для получения обновлений от Telegram"""
    if not bot_instance:
        logger.error("⚠️ Bot не инициализирован, входящий запрос не может быть обработан.")
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

    try:
        update_data = await request.json()
        # Запускаем обработку в фоне, чтобы не задерживать ответ Telegram
        asyncio.create_task(bot_instance.process_update(update_data))
        return Response(status_code=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"❌ Критическая ошибка на уровне webhook: {e}", exc_info=True)
        return Response(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@app.get("/health")
async def health_check():
    """Endpoint для проверки здоровья всех сервисов"""
    health_status = await simple_health_check()
    status_code = 200 if health_status["overall_status"] == "healthy" else 503
    return Response(
        content=json.dumps(health_status, indent=2),
        media_type="application/json",
        status_code=status_code
    )


@app.get("/status")
async def detailed_status():
    """Подробный статус всех сервисов"""
    try:
        from services.smart_video_service import get_system_status

        system_status = await get_system_status()

        # Добавляем статус Tor из глобального сервиса
        tor_info = {"status": "unknown"}
        if smart_video_service and hasattr(smart_video_service, 'tor'):
            tor_info = {
                "status": "running" if smart_video_service.tor.is_running() else "stopped",
                "enabled": smart_video_service.tor.is_enabled,
                "current_ip": smart_video_service.tor.current_ip
            }

        return {
            "bot_status": "running" if bot_instance else "stopped",
            "system_status": system_status,
            "tor_status": tor_info,
            "timestamp": datetime.now().isoformat(),
            "environment": {
                "use_tor": os.getenv("USE_TOR", "false"),
                "use_cookies": os.getenv("USE_COOKIES", "false"),
                "r2_configured": bool(os.getenv("R2_ACCOUNT_ID")),
                "webhook_url": bool(os.getenv("WEBHOOK_URL"))
            }
        }
    except Exception as e:
        return {
            "bot_status": "running" if bot_instance else "stopped",
            "system_status": {"error": str(e)},
            "timestamp": datetime.now().isoformat()
        }


@app.get("/metrics")
async def metrics():
    """Базовые метрики для мониторинга"""
    try:
        import psutil

        # Системные метрики
        system_stats = {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent,
            "uptime_seconds": psutil.boot_time()
        }

        return {
            "system": system_stats,
            "bot_status": "running" if bot_instance else "stopped",
            "timestamp": datetime.now().isoformat()
        }
    except ImportError:
        # Если psutil недоступен
        return {
            "system": {"error": "psutil not available"},
            "bot_status": "running" if bot_instance else "stopped",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "error": str(e),
            "bot_status": "running" if bot_instance else "stopped",
            "timestamp": datetime.now().isoformat()
        }


# НОВЫЙ ENDPOINT для диагностики Tor
@app.get("/tor-status")
async def tor_status():
    """Подробный статус Tor"""
    if not smart_video_service:
        return {"error": "SmartVideoService не инициализирован"}

    if not hasattr(smart_video_service, 'tor'):
        return {"error": "Tor сервис недоступен"}

    tor_service = smart_video_service.tor
    return {
        "enabled": tor_service.is_enabled,
        "running": tor_service.is_running(),
        "current_ip": tor_service.current_ip,
        "startup_complete": getattr(tor_service, '_startup_complete', False),
        "tor_port": tor_service.tor_port,
        "control_port": tor_service.control_port,
        "timestamp": datetime.now().isoformat()
    }


# НОВЫЙ ENDPOINT для метрик производительности
@app.get("/performance")
async def performance_metrics():
    """Метрики производительности YouTube загрузок"""
    try:
        if smart_video_service and hasattr(smart_video_service, 'performance_monitor'):
            stats = smart_video_service.performance_monitor.get_stats()
            return {
                "youtube_downloads": stats,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "youtube_downloads": {"error": "Performance monitor not available"},
                "timestamp": datetime.now().isoformat()
            }
    except Exception as e:
        return {
            "youtube_downloads": {"error": str(e)},
            "timestamp": datetime.now().isoformat()
        }


# Запуск сервера для локального тестирования
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = "0.0.0.0"

    logger.info(f"🌐 Запуск сервера на {host}:{port}")

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=False,  # Отключаем reload для production
        log_level="info",
    )