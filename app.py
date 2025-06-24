# app.py
import os
import logging
import asyncio
from quart import Quart, request, jsonify, render_template
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

# Импорты всех наших сервисов
from services.message_handler import MessageHandler
from services.telegram_handler import TelegramHandler
from services.database import Database
from services.translation_service import TranslationService
from services.s3_service import S3Service

# Инициализируем Quart приложение
app = Quart(__name__)

# --- Инициализация сервисов ---
# Мы используем глобальные переменные для хендлеров, чтобы они были доступны в роутах
message_handler = None
telegram_handler = None


@app.before_serving
async def startup():
    """
    Эта функция выполняется один раз при старте сервера.
    Здесь мы инициализируем все наши сервисы.
    """
    global message_handler, telegram_handler
    logger.info("Initializing services for web process...")
    try:
        database = Database()
        s3_service = S3Service()
        translation_service = TranslationService()

        # Инициализация обработчика для Messenger
        message_handler = MessageHandler(database=database, translation_service=translation_service)

        # Инициализация обработчика для Telegram
        telegram_token = os.getenv('TELEGRAM_TOKEN')
        if telegram_token:
            telegram_handler = TelegramHandler(
                token=telegram_token,
                database=database,
                s3_service=s3_service,
                translation_service=translation_service  # <== Важное исправление
            )
            logger.info("✅ Telegram Handler initialized successfully.")
        else:
            logger.warning("TELEGRAM_TOKEN not found. Telegram bot will be disabled.")

        logger.info("✅ Web services initialized successfully.")
    except Exception as e:
        logger.error(f"❌ CRITICAL INITIALIZATION ERROR: {e}", exc_info=True)
        # Если что-то пошло не так, хендлеры останутся None, и бот не будет работать


# --- Роуты ---

@app.route('/', methods=['GET'])
async def health_check():
    """Проверка состояния сервиса"""
    return jsonify({'status': 'Bot web service is running'})


# --- Роуты для Messenger ---
@app.route('/webhook', methods=['GET'])
async def webhook_verify():
    """Верификация вебхука для Facebook Messenger"""
    verify_token = os.getenv('VERIFY_TOKEN')
    if request.args.get('hub.verify_token') == verify_token:
        return request.args.get('hub.challenge', '')
    return 'Verification failed', 403


@app.route('/webhook', methods=['POST'])
async def webhook_handler():
    """Обработка входящих сообщений от Facebook Messenger"""
    try:
        data = await request.get_json()
        if data and data.get('object') == 'page':
            if message_handler:
                # Этот хендлер пока синхронный, вызываем его напрямую
                message_handler.handle_message(data)
            else:
                logger.error("MessageHandler was not initialized.")
        return 'OK', 200
    except Exception as e:
        logger.error(f"Critical error in webhook_handler: {e}", exc_info=True)
        return 'OK', 200


# --- Роут для Telegram ---
@app.route('/telegram_webhook', methods=['POST'])
async def telegram_webhook_handler():
    """Обработка входящих сообщений от Telegram"""
    try:
        data = await request.get_json()
        if data:
            if telegram_handler:
                await telegram_handler.handle_update(data)
            else:
                logger.error("TelegramHandler was not initialized.")
        return 'OK', 200
    except Exception as e:
        logger.error(f"Critical error in telegram_webhook_handler: {e}", exc_info=True)
        return 'OK', 200


# --- Роуты для статических страниц (Privacy Policy / Terms) ---
@app.route('/privacy')
async def privacy_policy():
    """Рендерит страницу с политикой конфиденциальности из шаблона"""
    return await render_template('privacy_policy.html')


@app.route('/terms')
async def terms_of_service():
    """Рендерит страницу с условиями использования из шаблона"""
    return await render_template('terms_of_service.html')

# Запуск приложения через Hypercorn будет осуществляться командой из render.yaml,
# поэтому блок if __name__ == '__main__' больше не нужен.