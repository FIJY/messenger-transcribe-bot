# app.py
import logging
import asyncio
from quart import Quart, Response
from hypercorn.config import Config
from hypercorn.asyncio import serve
import sys

# Добавляем корень проекта в пути, чтобы Python находил наши модули
sys.path.insert(0, '.')

# Теперь импорты выглядят чисто и работают правильно
from config import settings, START_MESSAGE

app = Quart(__name__)

# URL для вебхука, защищенный токеном
WEBHOOK_URL_PATH = f"/{settings.TELEGRAM_TOKEN}"

@app.route(WEBHOOK_URL_PATH, methods=['POST'])
async def webhook():
    logging.info("Webhook received!")
    return Response(status=200)

@app.route("/health")
async def health_check():
    logging.info(f"Health check OK. Start message is: {START_MESSAGE}")
    return Response("OK", status=200)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.info("Starting application...")

    hypercorn_config = Config()
    hypercorn_config.bind = ["0.0.0.0:8000"]

    # Запускаем сервер
    asyncio.run(serve(app, hypercorn_config))