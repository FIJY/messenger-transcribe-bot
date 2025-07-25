# services/telegram_handler.py
import os
import logging
from telegram import Update, Bot, BotCommand

from .database import Database
from .s3_service import S3Service
from .celery_client import get_celery_app_client
from .payment_service import PaymentService
from .localization_service import LocalizationService
from .telegram_ui import TelegramUI
from .insight_service import InsightService
from .translation_service import TranslationService
from .downloader_service import DownloaderService
from .business_analyzer_service import BusinessAnalyzerService
from .youtube_service import YouTubeService
from .export_service import ExportService
from .command_handler import CommandHandler
from .message_handler import MessageHandler
from .callback_query_handler import CallbackQueryHandler

logger = logging.getLogger(__name__)


class TelegramHandler:
    def __init__(self, token: str, database: Database, s3_service: S3Service,
                 payment_service: PaymentService, insight_service: InsightService,
                 translation_service: TranslationService, downloader_service: DownloaderService,
                 business_analyzer: BusinessAnalyzerService, youtube_service: YouTubeService):
        if not token: raise ValueError("Telegram token is required.")
        # Core services
        self.bot = Bot(token=token)
        self.database = database
        self.s3_service = s3_service
        self.payment_service = payment_service
        self.insight_service = insight_service
        self.translation_service = translation_service
        self.downloader_service = downloader_service
        self.business_analyzer = business_analyzer
        self.youtube_service = youtube_service
        self.celery_app_client = get_celery_app_client()
        self.admin_telegram_id = os.getenv('ADMIN_TELEGRAM_ID')
        self.localizer = LocalizationService()
        self.ui = TelegramUI(self.localizer)
        self.export_service = ExportService

        # Initialize sub-handlers
        self.command_handler = CommandHandler(self.bot, self.database, self.ui, self.localizer, self.admin_telegram_id)
        self.message_handler = MessageHandler(self.bot, self.database, self.ui, self.localizer, self.s3_service,
                                              self.celery_app_client, self.insight_service, self.payment_service)
        self.callback_query_handler = CallbackQueryHandler(self)

    async def set_bot_commands(self):
        commands = [
            BotCommand("start", "Restart the bot"), BotCommand("status", "Check your current plan"),
            BotCommand("help", "Get help and information"), BotCommand("cancel", "Exit current mode")
        ]
        try:
            await self.bot.set_my_commands(commands)
            logger.info("Bot commands have been set successfully.")
        except Exception as e:
            logger.error(f"Failed to set bot commands: {e}")

    async def handle_update(self, update_data: dict):
        update = Update.de_json(update_data, bot=self.bot)
        effective_user = update.effective_user
        if not effective_user: return

        user_id = str(effective_user.id)
        user = self.database.get_user(user_id)
        lang_code = effective_user.language_code or 'en'

        if not user:
            user = self.database.create_user(user_id, username=effective_user.username, language_code=lang_code)
        elif user.get('language_code') != lang_code:
            self.database.update_user(user_id, {'language_code': lang_code})
            user['language_code'] = lang_code

        user_lang = user.get('language_code', 'en')

        if update.callback_query:
            await self.callback_query_handler.handle(update.callback_query, user_lang)
        elif update.message:
            if update.message.text and update.message.text.startswith('/'):
                await self.command_handler.handle(update.message, user_lang)
            else:
                await self.message_handler.handle(update.message, user, user_lang)
