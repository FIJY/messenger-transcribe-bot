# services/payment_service.py
import os
import logging
from telegram import Bot, Message

# ИСПРАВЛЕНО: Убран импорт 'PLANS', который вызывал ошибку
from .database import Database
from .telegram_ui import TelegramUI
from .localization_service import LocalizationService

logger = logging.getLogger(__name__)


class PaymentService:
    def __init__(self, bot: Bot, db: Database, ui: TelegramUI, localizer: LocalizationService):
        self.bot = bot
        self.db = db
        self.ui = ui
        self.localizer = localizer
        self.admin_telegram_id = os.getenv('ADMIN_TELEGRAM_ID')

    async def handle_payment_proof(self, message: Message):
        user_id = str(message.from_user.id)
        chat_id = message.chat_id
        lang_code = message.from_user.language_code or 'en'

        if not self.admin_telegram_id:
            logger.warning("ADMIN_TELEGRAM_ID is not set. Cannot forward payment proofs.")
            await self.bot.send_message(chat_id, "Payment processing is temporarily unavailable.")
            return

        # Forward the proof to the admin
        await self.bot.forward_message(
            chat_id=self.admin_telegram_id,
            from_chat_id=chat_id,
            message_id=message.message_id
        )

        # Send a confirmation to the user
        await self.bot.send_message(
            chat_id,
            self.localizer.get_string(lang_code, 'payment_proof_received',
                                      default="Спасибо! Ваше подтверждение оплаты получено и будет проверено в ближайшее время.")
        )

        # Optionally, send user info to admin as well
        await self.bot.send_message(
            self.admin_telegram_id,
            f"New payment proof from user:\nID: `{user_id}`\nUsername: @{message.from_user.username}"
        )
