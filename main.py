# main.py - Ультра-простая версия без pydantic
import logging
import os
from fastapi import FastAPI, Request

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Простая проверка переменных окружения
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

if not TELEGRAM_TOKEN:
    logger.error("❌ TELEGRAM_TOKEN не установлен!")
    logger.info("💡 Создайте переменную окружения TELEGRAM_TOKEN с токеном от @BotFather")
    exit(1)

logger.info(f"✅ Токен найден: {TELEGRAM_TOKEN[:10]}...{TELEGRAM_TOKEN[-4:]}")

# Импортируем config только после проверки токена
try:
    from config import settings

    logger.info("✅ Конфигурация загружена успешно")
except Exception as e:
    logger.error(f"❌ Ошибка загрузки config: {e}")


    # Создаем простую заглушку
    class SimpleSettings:
        def __init__(self):
            self.TELEGRAM_TOKEN = TELEGRAM_TOKEN
            self.OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')


    settings = SimpleSettings()
    logger.info("✅ Использую упрощенную конфигурацию")

# Глобальная переменная для бота
bot_instance = None

# Создание FastAPI приложения
app = FastAPI(
    title="TranscribeBot API",
    description="AI-powered transcription bot",
    version="1.0.0"
)


@app.on_event("startup")
async def startup_event():
    """Инициализация при запуске"""
    global bot_instance

    try:
        logger.info("🚀 Запуск TranscribeBot...")

        # Простая инициализация
        from bot_simple import SimpleBotHandler
        bot_instance = SimpleBotHandler()
        await bot_instance.initialize()

        logger.info("✅ Bot инициализирован успешно")

    except Exception as e:
        logger.error(f"❌ Ошибка инициализации: {e}", exc_info=True)
        # Не прерываем запуск


@app.on_event("shutdown")
async def shutdown_event():
    """Очистка при остановке"""
    global bot_instance

    logger.info("🛑 Остановка бота...")
    if bot_instance:
        try:
            await bot_instance.shutdown()
        except Exception as e:
            logger.error(f"Ошибка при остановке: {e}")


@app.get("/")
async def root():
    """Корневой endpoint"""
    return {
        "message": "TranscribeBot API is running! 🤖",
        "version": "1.0.0",
        "status": "healthy",
        "bot_token_set": bool(TELEGRAM_TOKEN),
        "bot_initialized": bot_instance is not None
    }


@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    return {
        "status": "healthy",
        "service": "transcribe-bot",
        "version": "1.0.0",
        "bot_status": "running" if bot_instance else "not_initialized",
        "token_configured": bool(TELEGRAM_TOKEN)
    }


@app.post(f"/webhook/{TELEGRAM_TOKEN}")
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
        "webhook_url": f"/webhook/{TELEGRAM_TOKEN}",
        "telegram_token_set": bool(TELEGRAM_TOKEN),
        "full_webhook_url": f"https://your-app.onrender.com/webhook/{TELEGRAM_TOKEN}"
    }


if __name__ == "__main__":
    import uvicorn

    # Определяем порт
    port = int(os.getenv("PORT", 8000))

    logger.info(f"🌐 Запуск сервера на порту {port}")
    logger.info(f"🔗 Webhook URL: /webhook/{TELEGRAM_TOKEN}")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,  # Отключаем reload в продакшене
        log_level="info"
    )