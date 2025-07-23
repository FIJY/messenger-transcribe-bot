# services/telegram_ui.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Dict, Any, Tuple
from bson import ObjectId
from datetime import datetime, timezone


class TelegramUI:
    def get_welcome_message(self) -> str:
        return (
            "👋 *Welcome!*\n\n"
            "I can transcribe audio and video, create summaries, and analyze content for you.\n\n"
            "Just send me a file, a voice message, or a link to a video (like YouTube)."
        )

    def get_status_message(self, user: Dict[str, Any]) -> str:
        plan = user.get('plan', 'free').capitalize()
        minutes_used = round(user.get('minutes_used', 0), 2)
        minutes_limit = user.get('minutes_limit', 0)

        expires_at = user.get('subscription_expires_at')
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        expires_str = f"_Expires on: {expires_at.strftime('%Y-%m-%d %H:%M')} UTC_" if expires_at else ""

        return (
            f"📊 *Your Status*\n\n"
            f"🔹 *Plan:* {plan}\n"
            f"🔸 *Minutes Used:* {minutes_used} / {minutes_limit}\n"
            f"{expires_str}"
        )

    def get_help_message(self, add_to_group_url: str) -> str:
        return (
            "🆘 *Help & Information*\n\n"
            "I can process:\n"
            "- Audio files (mp3, wav, ogg, etc.)\n"
            "- Video files (mp4, mov, etc.)\n"
            "- Voice messages & video notes\n"
            "- Links to YouTube videos\n\n"
            "*Commands:*\n"
            "`/start` - Restart the bot\n"
            "`/status` - Check your plan details\n"
            "`/search <query>` - Search your notes\n"
            "`/cancel` - Exit special modes (like chat)\n\n"
            f"[Click here to add me to a group]({add_to_group_url})"
        )

    def format_search_results(self, notes: List[Dict[str, Any]], query: str) -> str:
        if not notes:
            return f"No notes found matching your query: `{query}`"

        header = f"🔍 *Search Results for:* `{query}`\n\n"
        results_list = []
        for note in notes:
            content_preview = note.get('content', '')[:100].replace('\n', ' ') + '...'
            created_date = note.get('created_at').strftime('%Y-%m-%d')
            results_list.append(f"📄 *{created_date}* - `{content_preview}`")

        return header + "\n".join(results_list)

    def get_main_actions_menu(self, note_id: ObjectId) -> Tuple[str, InlineKeyboardMarkup]:
        """
        Возвращает основное меню действий после транскрипции.
        """
        text = "What would you like to do with this transcription?"
        keyboard = [
            [InlineKeyboardButton("💬 Задать вопрос по тексту", callback_data=f"ACTION_CHAT_{note_id}")],
            [
                InlineKeyboardButton("📊 Create Smart Report", callback_data=f"ACTION_REPORT_{note_id}"),
                InlineKeyboardButton("🌐 Translate", callback_data=f"ACTION_TRANSLATE_{note_id}")
            ],
            [
                InlineKeyboardButton("📝 Simple Summary", callback_data=f"ACTION_SUMMARIZE_{note_id}"),
                InlineKeyboardButton("📜 Create Subtitles (.srt)", callback_data=f"ACTION_SUBTITLES_{note_id}")
            ],
            [
                InlineKeyboardButton("💼 Business Analysis", callback_data=f"ACTION_BIZANALYSIS_{note_id}"),
                InlineKeyboardButton("🗑️ Delete Note", callback_data=f"ACTION_DELETE_{note_id}")
            ]
        ]
        return text, InlineKeyboardMarkup(keyboard)

    def get_delete_confirmation(self, note_id: ObjectId) -> Tuple[str, InlineKeyboardMarkup]:
        text = "Are you sure you want to permanently delete this note?"
        keyboard = [
            [
                InlineKeyboardButton("✅ Yes, delete it", callback_data=f"ACTION_DELETE_CONFIRM_{note_id}"),
                InlineKeyboardButton("❌ No, cancel", callback_data=f"ACTION_DELETE_CANCEL_{note_id}")
            ]
        ]
        return text, InlineKeyboardMarkup(keyboard)

    # ... и другие UI-методы, если они у вас есть
