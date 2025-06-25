# services/payment_service.py
import os
import logging
from telegram import Bot
from typing import Optional

logger = logging.getLogger(__name__)


class PaymentService:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.admin_chat_id = os.getenv('ADMIN_TELEGRAM_ID')
        if not self.admin_chat_id:
            logger.warning("ADMIN_TELEGRAM_ID is not set. Admin notifications for payments will be disabled.")

    async def notify_admin_of_payment_claim(self, user_id: str, username: Optional[str] = None):
        """
        Отправляет уведомление администратору о том, что пользователь заявил об оплате.
        """
        if not self.admin_chat_id:
            return

        user_mention = f"@{username}" if username else f"ID: `{user_id}`"
        text = (
            f"🔔 *Новая заявка на оплату!*\n\n"
            f"Пользователь {user_mention} нажал кнопку 'Я оплатил'.\n\n"
            f"Пожалуйста, проверьте поступление средств в приложении ABA.\n"
            f"Для активации используйте команду:\n"
            f"`/confirm {user_id} basic` или `/confirm {user_id} premium`"
        )
        try:
            await self.bot.send_message(chat_id=self.admin_chat_id, text=text, parse_mode='Markdown')
            logger.info(f"Sent payment claim notification to admin for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to send admin notification for user {user_id}: {e}")