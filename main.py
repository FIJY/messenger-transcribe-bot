# main.py - Стабильная версия с улучшенной обработкой ошибок
import logging
import os
import httpx
import asyncio
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Проверка переменных окружения
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://messenger-transcribe-bot.onrender.com')

if not TELEGRAM_TOKEN:
    logger.error("❌ TELEGRAM_TOKEN не установлен!")
    exit(1)

logger.info(f"✅ Токен найден: {TELEGRAM_TOKEN[:10]}...{TELEGRAM_TOKEN[-4:]}")
logger.info(f"🌐 Webhook URL: {WEBHOOK_URL}")

# Глобальная переменная для бота
bot_instance = None


async def setup_webhook():
    """Установка webhook с retry логикой"""
    webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook/{TELEGRAM_TOKEN}"
    api_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"

    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(api_url, json={"url": webhook_url})
                result = response.json()

                if result.get("ok"):
                    logger.info(f"✅ Webhook установлен успешно: {webhook_url}")
                    return True
                else:
                    logger.error(f"❌ Ошибка установки webhook (попытка {attempt + 1}): {result.get('description')}")

        except Exception as e:
            logger.error(f"❌ Ошибка при установке webhook (попытка {attempt + 1}): {e}")

        if attempt < max_retries - 1:
            await asyncio.sleep(2 ** attempt)  # Экспоненциальная задержка

    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    global bot_instance

    try:
        logger.info("🚀 Запуск TranscribeBot...")

        # 1. Устанавливаем webhook
        webhook_success = await setup_webhook()
        if not webhook_success:
            logger.warning("⚠️ Webhook не установлен, но продолжаем запуск")

        # 2. Инициализируем бота
        try:
            from bot_simple import SimpleBotHandler
            bot_instance = SimpleBotHandler()
            init_success = await bot_instance.initialize()

            if init_success:
                logger.info("✅ Bot инициализирован успешно")
            else:
                logger.warning("⚠️ Bot инициализирован с предупреждениями")

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации бота: {e}")
            bot_instance = None

        logger.info("🎉 Приложение готово к работе")

    except Exception as e:
        logger.error(f"❌ Критическая ошибка при запуске: {e}", exc_info=True)
        # Не прерываем запуск - FastAPI все равно должен работать

    yield

    # Очистка ресурсов
    logger.info("🛑 Остановка приложения...")
    if bot_instance:
        try:
            await bot_instance.shutdown()
        except Exception as e:
            logger.error(f"Ошибка при остановке бота: {e}")


# Создание FastAPI приложения
app = FastAPI(
    title="TranscribeBot API",
    description="AI-powered transcription bot",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """Корневой endpoint с подробной информацией"""
    return {
        "message": "TranscribeBot API is running! 🤖",
        "version": "1.0.0",
        "status": "healthy",
        "bot_initialized": bot_instance is not None,
        "webhook_url": f"{WEBHOOK_URL}/webhook/{TELEGRAM_TOKEN}",
        "endpoints": {
            "health": "/health",
            "webhook_info": "/webhook/info",
            "manual_webhook": "/set_webhook"
        }
    }


@app.get("/health")
async def health_check():
    """Детальная проверка здоровья"""
    return {
        "status": "healthy",
        "service": "transcribe-bot",
        "version": "1.0.0",
        "components": {
            "bot_status": "running" if bot_instance else "failed",
            "token_configured": bool(TELEGRAM_TOKEN),
            "webhook_configured": bool(WEBHOOK_URL)
        },
        "environment": {
            "python_version": os.sys.version,
            "port": os.getenv("PORT", "8000")
        }
    }


@app.post(f"/webhook/{TELEGRAM_TOKEN}")
async def telegram_webhook(request: Request):
    """Обработка webhook от Telegram"""
    try:
        update_data = await request.json()
        update_id = update_data.get('update_id', 'unknown')

        logger.info(f"📨 Получен update: {update_id}")

        if bot_instance:
            try:
                await bot_instance.process_update(update_data)
                logger.info(f"✅ Update {update_id} обработан успешно")
            except Exception as e:
                logger.error(f"❌ Ошибка обработки update {update_id}: {e}")
                return {"status": "error", "message": str(e)}
        else:
            logger.warning(f"⚠️ Bot не инициализирован, пропускаем update {update_id}")

        return {"status": "ok", "update_id": update_id}

    except Exception as e:
        logger.error(f"❌ Критическая ошибка webhook: {e}", exc_info=True)
        return {"status": "error", "message": "Internal server error"}


@app.get("/webhook/info")
async def webhook_info():
    """Информация о webhook"""
    return {
        "webhook_endpoint": f"/webhook/{TELEGRAM_TOKEN}",
        "full_webhook_url": f"{WEBHOOK_URL}/webhook/{TELEGRAM_TOKEN}",
        "telegram_token_configured": bool(TELEGRAM_TOKEN),
        "webhook_url_configured": bool(WEBHOOK_URL)
    }


@app.get("/set_webhook")
async def manual_webhook_setup():
    """Ручная установка webhook"""
    success = await setup_webhook()
    return {
        "success": success,
        "webhook_url": f"{WEBHOOK_URL}/webhook/{TELEGRAM_TOKEN}",
        "message": "Webhook установлен" if success else "Ошибка установки webhook"
    }


@app.get("/bot/status")
async def bot_status():
    """Статус бота"""
    if bot_instance:
        try:
            # Проверяем подключение к Telegram API
            async with httpx.AsyncClient() as client:
                response = await client.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe")
                bot_info = response.json() if response.status_code == 200 else None

            return {
                "bot_initialized": True,
                "bot_info": bot_info.get("result") if bot_info and bot_info.get("ok") else None,
                "api_status": "connected" if bot_info and bot_info.get("ok") else "error"
            }
        except Exception as e:
            return {
                "bot_initialized": True,
                "api_status": "error",
                "error": str(e)
            }
    else:
        return {
            "bot_initialized": False,
            "api_status": "not_initialized"
        }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))

    logger.info(f"🌐 Запуск сервера на порту {port}")
    logger.info(f"🔗 Webhook URL: {WEBHOOK_URL}/webhook/{TELEGRAM_TOKEN}")

    try:
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=port,
            reload=False,
            log_level="info",
            access_log=True
        )
    except Exception as e:
        logger.error(f"❌ Критическая ошибка запуска сервера: {e}")
        exit(1)