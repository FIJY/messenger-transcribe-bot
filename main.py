# main.py - Основное приложение
import asyncio
import logging
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager

from bot import TranscribeBot
from config import settings

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Глобальная переменная для бота
bot_instance = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    global bot_instance

    # Инициализация бота при запуске
    logger.info("🚀 Запуск TranscribeBot...")
    bot_instance = TranscribeBot()
    await bot_instance.initialize()
    logger.info("✅ Bot инициализирован успешно")

    yield

    # Очистка ресурсов при остановке
    logger.info("🛑 Остановка бота...")
    if bot_instance:
        await bot_instance.shutdown()


# Создание FastAPI приложения
app = FastAPI(
    title="TranscribeBot API",
    description="AI-powered transcription and content processing bot",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    return {
        "status": "healthy",
        "service": "transcribe-bot",
        "version": "1.0.0"
    }


@app.post(f"/webhook/{settings.TELEGRAM_TOKEN}")
async def telegram_webhook(request: Request):
    """Обработка webhook от Telegram"""
    try:
        update_data = await request.json()
        logger.info(f"📨 Получен update: {update_data.get('update_id')}")

        if bot_instance:
            await bot_instance.process_update(update_data)

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"❌ Ошибка обработки webhook: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True if settings.DEBUG else False
    )