# main.py - Упрощенная версия для быстрого запуска
import logging
import asyncio
import os
from fastapi import FastAPI, Request, HTTPException
from contextlib import asynccontextmanager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Проверяем наличие необходимых переменных
required_env_vars = ['TELEGRAM_TOKEN', 'OPENAI_API_KEY']
missing_vars = [var for var in required_env_vars if not os.getenv(var)]

if missing_vars:
    logger.error(f"❌ Отсутствуют переменные окружения: {missing_vars}")
    logger.info("💡 Создайте .env файл с необходимыми переменными")
    exit(1)

try:
    from config import settings
except ImportError as e:
    logger.error(f"❌ Ошибка импорта config: {e}")
    logger.info("💡 Убедитесь, что файл config.py создан правильно")
    exit(1)

# Глобальная переменная для бота
bot_instance = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    global bot_instance

    try:
        logger.info("🚀 Запуск TranscribeBot...")

        # Простая инициализация без сложных зависимостей
        from bot_simple import SimpleBotHandler
        bot_instance = SimpleBotHandler()
        await bot_instance.initialize()

        logger.info("✅ Bot инициализирован успешно")

    except Exception as e:
        logger.error(f"❌ Ошибка инициализации: {e}", exc_info=True)
        # Не прерываем запуск, просто логируем ошибку

    yield

    # Очистка ресурсов при остановке
    logger.info("🛑 Остановка бота...")
    if bot_instance:
        try:
            await bot_instance.shutdown()
        except Exception as e:
            logger.error(f"Ошибка при остановке: {e}")


# Создание FastAPI приложения
app = FastAPI(
    title="TranscribeBot API",
    description="AI-powered transcription and content processing bot",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """Корневой endpoint"""
    return {
        "message": "TranscribeBot API is running",
        "version": "1.0.0",
        "status": "healthy"
    }


@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    return {
        "status": "healthy",
        "service": "transcribe-bot",
        "version": "1.0.0",
        "bot_status": "running" if bot_instance else "not_initialized"
    }


@app.post(f"/webhook/{settings.TELEGRAM_TOKEN}")
async def telegram_webhook(request: Request):
    """Обработка webhook от Telegram"""
    try:
        update_data = await request.json()
        logger.info(f"📨 Получен update: {update_data.get('update_id')}")

        if bot_instance:
            await bot_instance.process_update(update_data)
        else:
            logger.warning("⚠️ Bot не инициализирован, пропускаем update")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"❌ Ошибка обработки webhook: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@app.get("/webhook/info")
async def webhook_info():
    """Информация о webhook"""
    return {
        "webhook_url": f"/webhook/{settings.TELEGRAM_TOKEN}",
        "telegram_token_set": bool(settings.TELEGRAM_TOKEN),
        "openai_key_set": bool(settings.OPENAI_API_KEY)
    }


if __name__ == "__main__":
    import uvicorn

    # Определяем порт (для Render или локальной разработки)
    port = int(os.getenv("PORT", 8000))

    logger.info(f"🌐 Запуск сервера на порту {port}")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True if os.getenv("DEBUG") == "true" else False,
        log_level="info"
    )