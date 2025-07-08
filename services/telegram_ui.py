# services/telegram_ui.py
import os
from typing import Dict, Any, List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from bson import ObjectId

from .database import PLANS
from config.transcrib_suggestion_config import (
    DEFAULT_POPULAR_TRANSLATION_LANGS,
    SUPPORTED_LANGUAGES_MAP,
    DEFAULT_POPULAR_TRANSCRIPTION_LANGS
)


class TelegramUI:
    def __init__(self):
        self.base_url = os.getenv('RENDER_EXTERNAL_URL', 'https://your-app-name.onrender.com')
        self.support_contact = os.getenv('SUPPORT_CONTACT')

    def get_welcome_message(self) -> str:
        return (
            "🎉 *Welcome to your AI Notes Assistant!*\n\n"
            "To get started, just send me a voice message, an audio/video file, or a text message.\n\n"
            "Type /help to see all available commands."
        )

    def get_help_message(self, add_to_group_url: str) -> str:
        basic_plan = PLANS['basic']
        premium_plan = PLANS['premium']
        help_text = (
            "🤖 *Bot Help & Information*\n\n"
            "**How to Use Me:**\n"
            "Send me a voice message, audio/video file, or just text, and I will turn it into a structured note.\n\n"
            "**Available Commands:**\n"
            "`/start` - Restart the bot.\n"
            "`/status` - Check your current plan.\n"
            "`/search <text>` - Find text in your notes.\n"
            "`/summary` - Get a summary of recent notes.\n"
            "`/help` - Show this help message.\n\n"
            f"👥 *Add to a Group*\n"
            f"Click here to add me to your group chat: [Add to Group]({add_to_group_url})\n\n"
            "**Our Monthly Plans:**\n"
            f"🔹 **Basic (${basic_plan['price_usd']}/month):** {basic_plan['limit_minutes']} minutes.\n"
            f"💎 **Premium (${premium_plan['price_usd']}/month):** {premium_plan['limit_minutes']} minutes with all features.\n\n"
            f"For more details, please see our [Terms of Service]({self.base_url}/terms) and [Privacy Policy]({self.base_url}/privacy).\n\n"
        )
        if self.support_contact:
            help_text += f"If you have any questions, please contact our support: {self.support_contact}"
        return help_text

    def get_transcription_confirmation_message(self, text: str, lang_name: str, s3_key: str) -> tuple[
        str, InlineKeyboardMarkup]:
        message_text = f"📝 *Transcription ({lang_name}):*\n\n```{text}```\n\nIs the language and transcription correct?"
        keyboard = [
            [
                InlineKeyboardButton("✅ Looks Good", callback_data=f"CONFIRM_OK_{s3_key}"),
                InlineKeyboardButton("🗣️ Other language", callback_data=f"RETRY_LANG_{s3_key}")
            ]
        ]
        return message_text, InlineKeyboardMarkup(keyboard)

    def get_note_actions_message(self, note_id: ObjectId) -> tuple[str, InlineKeyboardMarkup]:
        message_text = "What would you like to do with this note?"
        keyboard = [
            [
                InlineKeyboardButton("📝 Summarize", callback_data=f"NOTE_SUMMARIZE_{note_id}"),
                InlineKeyboardButton("✅ Mark as TODO", callback_data=f"NOTE_TODO_{note_id}"),
            ],
            [
                InlineKeyboardButton("🌐 Translate", callback_data=f"NOTE_TRANSLATE_{note_id}"),
                InlineKeyboardButton("🔗 Find Related", callback_data=f"NOTE_FIND_{note_id}"),
            ],
            [InlineKeyboardButton("🗑️ Delete", callback_data=f"NOTE_DELETE_{note_id}")]
        ]
        return message_text, InlineKeyboardMarkup(keyboard)

    def get_delete_confirmation(self, note_id: ObjectId) -> tuple[str, InlineKeyboardMarkup]:
        return (
            "Are you sure you want to delete this note?",
            InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Yes, delete", callback_data=f"NOTE_DELETE_CONFIRM_{note_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"NOTE_DELETE_CANCEL_{note_id}")
            ]])
        )

    def get_translation_language_options(self, note_id: ObjectId) -> tuple[str, InlineKeyboardMarkup]:
        buttons = []
        for lang in DEFAULT_POPULAR_TRANSLATION_LANGS:
            buttons.append(InlineKeyboardButton(f"{lang['flag']} {lang['title']}",
                                                callback_data=f"NOTE_TRANSLATE_{note_id}_{lang['code']}"))

        keyboard = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
        return "Please select the target language:", InlineKeyboardMarkup(keyboard)

    def format_related_notes(self, notes: List[Dict[str, Any]]) -> str:
        if not notes: return "No related notes found."
        message = "🔍 *Found related notes:*\n\n"
        for note in notes:
            content_preview = (note['content'][:70] + '...').replace('\n', ' ')
            message += f"• `{content_preview}`\n"
        return message

    def format_search_results(self, notes: List[Dict[str, Any]], query: str) -> str:
        if not notes: return f"No notes found matching your query: `{query}`"
        message = f"🔍 *Search results for \"{query}\":*\n\n"
        for note in notes:
            content_preview = (note['content'][:100] + '...').replace('\n', ' ')
            message += f"🗓️ _{note['created_at'].strftime('%Y-%m-%d')}_:\n`{content_preview}`\n\n"
        return message

    def get_status_message(self, user: Dict[str, Any]) -> str:
        plan = user.get('plan', 'free').capitalize()
        minutes_used = user.get('minutes_used', 0)
        minutes_limit = user.get('minutes_limit', 0)

        if plan == 'Free':
            minutes_left = minutes_limit - minutes_used
            return (f"📊 *Your Status*\n\nPlan: {plan}\nMinutes left: {minutes_left:.1f} / {minutes_limit} minutes")
        else:
            expires_at = user.get('subscription_expires_at')
            expires_str = expires_at.strftime('%d %B %Y') if expires_at else 'N/A'
            return (
                f"📊 *Your Status*\n\nPlan: {plan} 💎\nSubscription valid until: {expires_str}\nMinutes used this period: {minutes_used:.1f} / {minutes_limit} minutes")

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

    def build_smart_buttons(self, user: Dict[str, Any], context: str) -> InlineKeyboardMarkup:
        # Эта функция используется для выбора языка при повторной попытке
        if context == 'transcription':
            defaults = DEFAULT_POPULAR_TRANSCRIPTION_LANGS
            usage_stats = user.get('transcription_lang_usage', {})
            prefix = "RETRY_AS_"
            # s3_key нужен для контекста, его нужно передавать
            other_payload = "INPUT_OTHER_TRANSCRIPTION_LANG_"
        else:
            return InlineKeyboardMarkup([[]])  # Для перевода своя логика

        sorted_user_langs = sorted(usage_stats.keys(), key=stats.get, reverse=True)
        buttons, added_codes = [], set()

        def add_button(lang_code):
            title_info = next((lang for lang in defaults if lang['code'] == lang_code), None)
            title = lang_code.upper()
            if title_info:
                flag = title_info.get('flag', '')
                title_text = title_info.get('title', title)
                title = f"{flag} {title_text}".strip()

            buttons.append(InlineKeyboardButton(title, callback_data=f"{prefix}{lang_code}"))
            added_codes.add(lang_code)

        for lang_code in sorted_user_langs[:3]: add_button(lang_code)
        for lang in defaults:
            if len(buttons) >= 5: break
            if lang['code'] not in added_codes: add_button(lang['code'])

        keyboard = [buttons, [InlineKeyboardButton("✍️ Type other...", callback_data=other_payload)]]
        return InlineKeyboardMarkup(keyboard)