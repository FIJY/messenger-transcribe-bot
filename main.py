# main.py - FastAPI сервер для Telegram бота
import logging
import os
import sys
import asyncio

# Проверяем и импортируем зависимости
try:
    import httpx
    from fastapi import FastAPI, Request, Response, status
    from contextlib import asynccontextmanager
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("💡 Установите зависимости: pip install -r requirements.txt")
    sys.exit(1)

from config import settings
from bot import TranscribeBot

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Глобальные переменные для хранения экземпляров
bot_instance: TranscribeBot | None = None


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    global bot_instance

    logger.info("🚀 Запуск TranscribeBot...")

    try:
        # 1. Инициализируем бота и все его компоненты
        bot_instance = TranscribeBot(settings)
        init_success = await bot_instance.initialize()

        if not init_success:
            logger.error("❌ Инициализация бота провалена. Приложение может работать некорректно.")
            # В реальном проде можно остановить запуск, если бот не стартовал
            # sys.exit(1)

        # 2. Устанавливаем webhook ПОСЛЕ инициализации
        if init_success:
            await setup_webhook()

        logger.info("🎉 Приложение готово к работе!")

    except Exception as e:
        logger.error(f"❌ Критическая ошибка при запуске: {e}", exc_info=True)

    yield

    # Очистка ресурсов при остановке
    logger.info("🛑 Остановка приложения...")
    if bot_instance:
        await bot_instance.shutdown()


# Создание FastAPI приложения
app = FastAPI(
    title="TranscribeBot API",
    description="AI-powered transcription bot",
    version="2.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """Главная страница с информацией о сервисе"""
    return {
        "message": "🤖 TranscribeBot API активен!",
        "version": "2.0.0",
        "status": "healthy" if bot_instance else "degraded",
        "bot_initialized": bot_instance is not None,
    }


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


# Добавить в main.py после создания app
from health_check import run_health_checks


@app.get("/health")
async def health_check():
    """Endpoint для проверки здоровья всех сервисов"""
    health_status = await run_health_checks()
    status_code = 200 if health_status["overall_status"] == "healthy" else 503
    return Response(
        content=json.dumps(health_status, indent=2),
        media_type="application/json",
        status_code=status_code
    )


@app.get("/metrics")
async def metrics():
    """Базовые метрики для мониторинга"""
    from monitoring import MonitoringService
    monitor = MonitoringService()

    system_stats = monitor.resource_monitor.get_system_stats()
    celery_stats = monitor.celery_monitor.get_worker_stats()

    return {
        "system": system_stats,
        "celery": celery_stats,
        "bot_status": "running" if bot_instance else "stopped"
    }

# Запуск сервера для локального тестирования
if __name__ == "__main__":
    try:
        import uvicorn
        from services.telegram_client import TelegramClient
    except ImportError:
        print("❌ uvicorn или другие компоненты не установлены")
        print("💡 Установите: pip install uvicorn")
        sys.exit(1)

    port = int(os.getenv("PORT", 8000))
    host = "0.0.0.0"

    logger.info(f"🌐 Запуск сервера на {host}:{port}")

    # Для локальной разработки можно использовать long polling вместо webhook
    # Для этого нужно закомментировать uvicorn.run и раскомментировать блок ниже

    # async def start_polling():
    #     global bot_instance
    #     logger.info("🚀 Запуск в режиме long polling...")
    #     bot_instance = TranscribeBot(settings)
    #     await bot_instance.initialize()
    #     client = TelegramClient(settings.TELEGRAM_TOKEN)
    #     await client.delete_webhook() # Удаляем вебхук перед поллингом
    #     offset = 0
    #     while True:
    #         updates = await client.get_updates(offset)
    #         for update in updates:
    #             offset = update['update_id'] + 1
    #             await bot_instance.process_update(update)
    #         await asyncio.sleep(1)

    # try:
    #      asyncio.run(start_polling())
    # except KeyboardInterrupt:
    #      logger.info("🛑 Сервер остановлен пользователем")

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,  # Включаем автоперезагрузку для удобства разработки
        log_level="info",
    )