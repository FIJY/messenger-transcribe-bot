# app.py
import logging
import sys
from quart import Quart, Response

# Добавляем корень проекта в пути, чтобы Python находил наши модули
sys.path.insert(0, '.')

from config import settings, START_MESSAGE

# Создаем приложение
app = Quart(__name__)

# URL для вебхука
WEBHOOK_URL_PATH = f"/{settings.TELEGRAM_TOKEN}"

@app.route(WEBHOOK_URL_PATH, methods=['POST'])
async def webhook():
    logging.info("Webhook received!")
    return Response(status=200)

@app.route("/health")
async def health_check():
    return Response("OK", status=200)

# Блок if __name__ == '__main__' больше не нужен,
# так как Gunicorn сам импортирует и запускает объект 'app'.