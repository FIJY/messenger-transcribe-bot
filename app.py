# app.py (или main.py, как вам удобнее)
import logging
from quart import Quart, request, Response
import sys

# Это решает все проблемы с импортами для IDE и для запуска
sys.path.append('.')

from containers import Container
from config import settings
from telegram_handler import TelegramHandler


def create_app() -> Quart:
    """Фабрика для создания Quart приложения."""

    app_container = Container()
    # "Связываем" контейнер с модулями, где есть @inject
    app_container.wire(modules=[__name__, "celery_worker"])

    app = Quart(__name__)
    app.container = app_container

    # Получаем обработчик из контейнера
    telegram_handler: TelegramHandler = app.container.telegram_handler()

    WEBHOOK_URL_PATH = f"/{settings.TELEGRAM_TOKEN}"

    @app.post(WEBHOOK_URL_PATH)
    async def webhook():
        data = await request.get_json()
        await telegram_handler.handle_update(data)
        return Response(status=200)

    @app.get("/health")
    async def health_check():
        return Response("OK", status=200)

    return app


app = create_app()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    # Используем Hypercorn для запуска, как и было в вашем проекте
    from hypercorn.config import Config
    from hypercorn.asyncio import serve
    import asyncio

    hypercorn_config = Config()
    hypercorn_config.bind = ["0.0.0.0:8000"]

    asyncio.run(serve(app, hypercorn_config))