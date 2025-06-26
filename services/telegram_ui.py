# services/telegram_ui.py
import os
from typing import Dict, Any, List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config.transcrib_suggestion_config import (
    DEFAULT_POPULAR_TRANSCRIPTION_LANGS,
    SUPPORTED_LANGUAGES_MAP
)
from .database import PLANS


class TelegramUI:
    def __init__(self):
        self.base_url = os.getenv('RENDER_EXTERNAL_URL', 'https://your-app-name.onrender.com')
        self.support_contact = os.getenv('SUPPORT_CONTACT')

    def get_welcome_message(self) -> str:
        return (
            "🎉 *Welcome to the Transcription Bot!*\n\n"
            "To get started, just send me an audio or video file.\n\n"
            "Type /help to see all available commands and features.\n\n"
            f"By using this bot, you agree to our [Terms of Service]({self.base_url}/terms) and [Privacy Policy]({self.base_url}/privacy)."
        )

    def get_help_message(self) -> str:
        basic_plan = PLANS['basic']
        premium_plan = PLANS['premium']
        help_text = (
            "🤖 *Bot Help & Information*\n\n"
            "**How to Use Me:**\n"
            "Simply send me an audio or video file, and I will transcribe it into text for you.\n\n"
            "**Available Commands:**\n"
            "`/start` - Start or restart the bot.\n"
            "`/status` - Check your current plan and minute balance.\n"
            "`/languages` - See the full list of supported languages.\n"
            "`/help` - Show this help message.\n\n"
            "**Our Monthly Plans:**\n"
            f"🔹 **Basic (${basic_plan['price_usd']}/month):** A package of {basic_plan['limit_minutes']} minutes for transcription.\n"
            f"💎 **Premium (${premium_plan['price_usd']}/month):** An extended package of {premium_plan['limit_minutes']} minutes with access to all features, including text translation.\n\n"
            f"For more details, please see our [Terms of Service]({self.base_url}/terms) and [Privacy Policy]({self.base_url}/privacy).\n\n"
        )
        if self.support_contact:
            help_text += f"If you have any questions, please contact our support: {self.support_contact}"
        return help_text

    def get_status_message(self, user: Dict[str, Any]) -> str:
        plan = user.get('plan', 'free').capitalize()
        minutes_used = user.get('minutes_used', 0)
        minutes_limit = user.get('minutes_limit', 0)

        if plan == 'Free':
            minutes_left = minutes_limit - minutes_used
            return (f"📊 *Your Status*\n\n"
                    f"Plan: {plan}\n"
                    f"Minutes left: {minutes_left:.1f} / {minutes_limit} minutes")
        else:
            expires_at = user.get('subscription_expires_at')
            expires_str = expires_at.strftime('%d %B %Y') if expires_at else 'N/A'
            return (f"📊 *Your Status*\n\n"
                    f"Plan: {plan} 💎\n"
                    f"Subscription valid until: {expires_str}\n"
                    f"Minutes used this period: {minutes_used:.1f} / {minutes_limit} minutes")

    def get_languages_message_chunks(self) -> List[str]:
        """Возвращает полный список языков, разбитый на части для отправки."""
        processed_langs = {}
        for key, value in SUPPORTED_LANGUAGES_MAP.items():
            if len(key) > 2:
                processed_langs[value] = key.capitalize()

        sorted_langs = sorted(processed_langs.items(), key=lambda item: item[1])

        header = "🌐 *Full List of Supported Languages for Transcription*\n\n"
        message_chunk = header
        messages = []

        for code, name in sorted_langs:
            line = f"• *{name}:* `{code}`\n"
            if len(message_chunk) + len(line) > 4096:
                messages.append(message_chunk)
                message_chunk = ""
            message_chunk += line

        if message_chunk:
            messages.append(message_chunk)

        return messages

    def get_limit_exceeded_message(self, user_id: str) -> tuple[str, InlineKeyboardMarkup]:
        basic_plan = PLANS['basic']
        premium_plan = PLANS['premium']
        payment_link = "https://pay.ababank.com/qLuyZbAyLDpyq9VSA"
        message = (
            f"⏳ *You have used all your available minutes.*\n\n"
            f"To continue, please choose a monthly package:\n\n"
            f"🔹 **Basic: ${basic_plan['price_usd']}/month**\n"
            f"• {basic_plan['limit_minutes']} minutes of transcription\n\n"
            f"💎 **Premium: ${premium_plan['price_usd']}/month**\n"
            f"• {premium_plan['limit_minutes']} minutes for all features\n\n"
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
        return message, reply_markup

    def build_smart_buttons(self, user: Dict[str, Any], context: str) -> InlineKeyboardMarkup:
        # Эта функция остается здесь, так как она чисто про UI
        if context == 'transcription':
            defaults, stats, prefix, other_payload = DEFAULT_POPULAR_TRANSCRIPTION_LANGS, user.get(
                'transcription_lang_usage', {}), "RETRY_AS_", "INPUT_OTHER_TRANSCRIPTION_LANG"
        else:
            defaults, stats, prefix, other_payload = DEFAULT_POPULAR_TRANSLATION_LANGS, user.get(
                'translation_lang_usage', {}), "TRANSLATE_", "INPUT_OTHER_TRANSLATION_LANG"

        sorted_user_langs = sorted(stats.keys(), key=stats.get, reverse=True)
        buttons, added_codes = [], set()

        def add_button(lang_code):
            title_info = next((lang for lang in defaults if lang['code'] == lang_code), None)
            if title_info:
                flag = title_info.get('flag', '')
                title_text = title_info.get('title', lang_code.upper())
                title = f"{flag} {title_text}".strip()
            else:
                title = lang_code.upper()

            buttons.append(InlineKeyboardButton(title, callback_data=f"{prefix}{lang_code}"))
            added_codes.add(lang_code)

        for lang_code in sorted_user_langs[:3]: add_button(lang_code)
        for lang in defaults:
            if len(buttons) >= 5: break
            if lang['code'] not in added_codes: add_button(lang['code'])

        keyboard = [buttons, [InlineKeyboardButton("✍️ Type other...", callback_data=other_payload)]]
        return InlineKeyboardMarkup(keyboard)