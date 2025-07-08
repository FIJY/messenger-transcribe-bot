# services/telegram_ui.py
import os
from typing import Dict, Any, List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from bson import ObjectId

from .database import PLANS
from config.transcrib_suggestion_config import (
    DEFAULT_POPULAR_TRANSCRIPTION_LANGS,
    DEFAULT_POPULAR_TRANSLATION_LANGS,
    SUPPORTED_LANGUAGES_MAP
)


class TelegramUI:
    def __init__(self):
        self.base_url = os.getenv('RENDER_EXTERNAL_URL', 'https://your-app-name.onrender.com')
        self.support_contact = os.getenv('SUPPORT_CONTACT')

    def get_welcome_message(self) -> str:
        return (
            "🎉 *Welcome to your AI Notes Assistant!*\n\n"
            "To get started, just send me a voice message, an audio/video file, or a YouTube link.\n\n"
            "Type /help to see all available commands."
        )

    def get_help_message(self, add_to_group_url: str) -> str:
        basic_plan = PLANS['basic']
        premium_plan = PLANS['premium']
        help_text = (
            "🤖 *Bot Help & Information*\n\n"
            "**How to Use Me:**\n"
            "Simply send me a voice message, an audio/video file, or a YouTube link, and I will turn it into a structured note.\n\n"
            "**Available Commands:**\n"
            "`/start` - Start or restart the bot.\n"
            "`/status` - Check your current plan and minute balance.\n"
            "`/search` - Find text in your notes (e.g., `/search meeting about budget`).\n"
            "`/summary` - Get a summary of recent notes.\n"
            "`/help` - Show this help message.\n\n"
            f"👥 *Add to a Group*\n"
            f"Click here to add me to your group chat: [Add to Group]({add_to_group_url})\n\n"
            "**Our Monthly Plans:**\n"
            f"🔹 **Basic (${basic_plan['price_usd']}/month):** A package of {basic_plan['limit_minutes']} minutes.\n"
            f"💎 **Premium (${premium_plan['price_usd']}/month):** An extended package of {premium_plan['limit_minutes']} minutes with all features.\n\n"
            f"For more details, please see our [Terms of Service]({self.base_url}/terms) and [Privacy Policy]({self.base_url}/privacy).\n\n"
        )
        if self.support_contact:
            help_text += f"If you have any questions, please contact our support: {self.support_contact}"
        return help_text

    def get_note_created_message(self, note_text: str, note_id: ObjectId) -> tuple[str, InlineKeyboardMarkup]:
        short_text = (note_text[:250] + '...') if len(note_text) > 250 else note_text

        message_text = (
            f"✅ *Note created successfully!*\n\n"
            f"```\n{short_text}\n```"
        )

        keyboard = [
            [
                InlineKeyboardButton("📝 Create TODO", callback_data=f"NOTE_TODO_{note_id}"),
                InlineKeyboardButton("🔗 Find Related", callback_data=f"NOTE_FIND_{note_id}"),
            ],
            [
                InlineKeyboardButton("📤 Share", callback_data=f"NOTE_SHARE_{note_id}"),
                InlineKeyboardButton("🗑️ Delete", callback_data=f"NOTE_DELETE_{note_id}"),
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        return message_text, reply_markup

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
        processed_langs = {}
        for key, value in SUPPORTED_LANGUAGES_MAP.items():
            if len(key) > 2:
                processed_langs[value] = key.capitalize()

        sorted_langs = sorted(processed_langs.items(), key=lambda item: item[1])

        header = "🌐 *Full List of Supported Languages for Transcription*\n\n"
        message_chunk = header
        messages = []

        for code, name in sorted_langs:
            line = f"• {name}: `{code}`\n"
            if len(message_chunk) + len(line) > 4096:
                messages.append(message_chunk)
                message_chunk = ""
            message_chunk += line

        if message_chunk and message_chunk != header:
            messages.append(message_chunk)

        return messages