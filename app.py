# app.py
import logging
import asyncio
from quart import Quart, Response
from hypercorn.config import Config
from hypercorn.asyncio import serve
import sys

# Add the project root to the Python path
sys.path.insert(0, '.')

from config.settings import settings
from config.constants import START_MESSAGE

app = Quart(__name__)

# Fix for the KeyError: 'PROVIDE_AUTOMATIC_OPTIONS'
app.config["PROVIDE_AUTOMATIC_OPTIONS"] = False

# Webhook URL secured by the bot token
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

    asyncio.run(serve(app, hypercorn_config))