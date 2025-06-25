# services/payment_service.py
import os
import logging
from telegram import Bot, Message, InlineKeyboardButton, InlineKeyboardMarkup
from typing import Optional

from .database import Database

logger = logging.getLogger(__name__)


class PaymentService:
    def __init__(self, bot: Bot, database: Database):
        self.bot = bot
        self.database = database
        self.admin_chat_id = os.getenv('ADMIN_TELEGRAM_ID')
        self.payment_qr_file_id = os.getenv('PAYMENT_QR_CODE_FILE_ID')
        if not self.admin_chat_id:
            logger.warning("ADMIN_TELEGRAM_ID is not set. Admin notifications for payments will be disabled.")

    async def send_payment_instructions(self, chat_id: int, user_id: str):
        """Отправляет сообщение об исчерпании лимита с инструкциями по оплате."""
        payment_link = "https://pay.ababank.com/qLuyZbAyLDpyq9VSA"
        message = (
            f"⏳ *You have used all your available minutes.*\n\n"
            f"To continue, please choose a monthly package:\n\n"
            f"🔹 **Basic: $2/month**\n"
            f"• 100 minutes of transcription\n"
            f"• Files up to 20 minutes\n\n"
            f"💎 **Premium: $5/month**\n"
            f"• 200 minutes for all features\n"
            f"• Files up to 60 minutes\n\n"
            f"💳 **Payment Options:**\n\n"
            f"**1. ABA Bank Transfer**\n"
            f"   Account Name: `SHMYKOVA OLGA`\n"
            f"   Account Number: `000 686 883`\n\n"
            f"**2. ABA Pay Link**\n"
            f"   [Tap here to pay with ABA Pay]({payment_link})\n\n"
            f"❗️**Important:** After payment, please **send a screenshot of the receipt** to this chat for verification."
        )
        keyboard = [[InlineKeyboardButton("📱 Show QR Code for Payment", callback_data="SHOW_PAYMENT_QR")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await self.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown', reply_markup=reply_markup)
        # Устанавливаем пользователю состояние ожидания скриншота
        self.database.update_user(user_id, {'state': 'awaiting_payment_proof'})

    async def handle_payment_proof(self, message: Message):
        """Обрабатывает полученный скриншот об оплате."""
        user = message.from_user
        user_id = str(user.id)
        chat_id = message.chat_id

        if not self.admin_chat_id:
            logger.warning("Admin ID not set, cannot forward payment proof.")
            await self.bot.send_message(chat_id, "Thank you! Your proof is in the queue and will be reviewed shortly.")
            return

        try:
            # 1. Отправляем пользователю подтверждение
            await self.bot.send_message(chat_id, "🙏 Thank you! Your payment proof has been received and sent for verification. Your plan will be activated shortly.")

            # 2. Формируем сообщение для админа
            user_mention = f"@{user.username}" if user.username else f"ID: `{user_id}`"
            admin_caption = (
                f"🔔 *Payment Proof Received*\n\n"
                f"From User: {user_mention}\n"
                f"Please verify and activate their plan using `/confirm {user_id} <plan_name>`."
            )

            # 3. Пересылаем скриншот админу
            await message.forward(chat_id=self.admin_chat_id)
            # 4. Отправляем текстовое сообщение с деталями следом
            await self.bot.send_message(chat_id=self.admin_chat_id, text=admin_caption, parse_mode='Markdown')

            # 5. Сбрасываем состояние пользователя
            self.database.update_user(user_id, {'state': None})

        except Exception as e:
            logger.error(f"Failed to process payment proof for user {user_id}: {e}", exc_info=True)