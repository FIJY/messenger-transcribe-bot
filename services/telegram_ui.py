# services/telegram_ui.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Dict, Any, Tuple
from bson import ObjectId
from datetime import datetime, timezone

from .localization_service import LocalizationService


class TelegramUI:
    def __init__(self, localizer: LocalizationService):
        self.localizer = localizer

    def get_welcome_message(self, lang_code: str) -> str:
        return self.localizer.get_string(lang_code, 'welcome_message')

    def get_status_message(self, user: Dict[str, Any]) -> str:
        lang_code = user.get('language_code', 'en')
        plan = user.get('plan', 'free').capitalize()
        minutes_used = round(user.get('minutes_used', 0), 2)
        minutes_limit = user.get('minutes_limit', 0)

        header = self.localizer.get_string(lang_code, 'status_header')
        plan_str = self.localizer.get_string(lang_code, 'status_plan', plan=plan)
        minutes_str = self.localizer.get_string(lang_code, 'status_minutes_used', minutes_used=minutes_used,
                                                minutes_limit=minutes_limit)

        expires_at = user.get('subscription_expires_at')
        expires_str = ""
        if expires_at:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            expires_date = expires_at.strftime('%Y-%m-%d %H:%M')
            expires_str = self.localizer.get_string(lang_code, 'status_expires_on', expires_date=expires_date)

        return f"{header}\n\n{plan_str}\n{minutes_str}\n{expires_str}"

    def get_help_message(self, lang_code: str, add_to_group_url: str) -> str:
        return (
            f"{self.localizer.get_string(lang_code, 'help_header')}\n\n"
            f"{self.localizer.get_string(lang_code, 'help_body')}\n\n"
            f"{self.localizer.get_string(lang_code, 'help_commands_header')}\n"
            f"{self.localizer.get_string(lang_code, 'help_command_start')}\n"
            f"{self.localizer.get_string(lang_code, 'help_command_status')}\n"
            f"{self.localizer.get_string(lang_code, 'help_command_search')}\n"
            f"{self.localizer.get_string(lang_code, 'help_command_cancel')}\n\n"
            f"{self.localizer.get_string(lang_code, 'help_add_to_group', add_to_group_url=add_to_group_url)}"
        )

    def format_search_results(self, lang_code: str, notes: List[Dict[str, Any]], query: str) -> str:
        if not notes:
            return f"No notes found matching your query: `{query}`"

        header = f"🔍 *Search Results for:* `{query}`\n\n"
        results_list = []
        for note in notes:
            content_preview = note.get('content', '')[:100].replace('\n', ' ') + '...'
            created_date = note.get('created_at').strftime('%Y-%m-%d')
            results_list.append(f"📄 *{created_date}* - `{content_preview}`")

        return header + "\n".join(results_list)

    def get_main_actions_menu(self, lang_code: str, note_id: ObjectId) -> Tuple[str, InlineKeyboardMarkup]:
        text = self.localizer.get_string(lang_code, 'menu_main_prompt')
        keyboard = [
            [InlineKeyboardButton(self.localizer.get_string(lang_code, 'button_ask_question'),
                                  callback_data=f"ACTION_CHAT_{note_id}")],
            [
                InlineKeyboardButton(self.localizer.get_string(lang_code, 'button_smart_report'),
                                     callback_data=f"ACTION_REPORT_{note_id}"),
                InlineKeyboardButton(self.localizer.get_string(lang_code, 'button_translate'),
                                     callback_data=f"ACTION_TRANSLATE_{note_id}")
            ],
            [
                InlineKeyboardButton(self.localizer.get_string(lang_code, 'button_summary'),
                                     callback_data=f"ACTION_SUMMARIZE_{note_id}"),
                InlineKeyboardButton(self.localizer.get_string(lang_code, 'button_subtitles'),
                                     callback_data=f"ACTION_SUBTITLES_{note_id}")
            ],
            [
                InlineKeyboardButton(self.localizer.get_string(lang_code, 'button_biz_analysis'),
                                     callback_data=f"ACTION_BIZANALYSIS_{note_id}"),
                InlineKeyboardButton(self.localizer.get_string(lang_code, 'button_delete'),
                                     callback_data=f"ACTION_DELETE_{note_id}")
            ],
            # --- НОВАЯ КНОПКА ---
            [
                InlineKeyboardButton("📄 " + self.localizer.get_string(lang_code, 'button_export', default="Export"),
                                     callback_data=f"ACTION_EXPORT_{note_id}")
            ]
        ]
        return text, InlineKeyboardMarkup(keyboard)

    # --- НОВЫЙ МЕТОД ---
    def get_export_menu(self, lang_code: str, note_id: ObjectId) -> Tuple[str, InlineKeyboardMarkup]:
        """Создает клавиатуру с выбором формата для экспорта."""
        text = self.localizer.get_string(lang_code, 'export_prompt', default="Choose export format:")
        keyboard = [
            [
                InlineKeyboardButton("Markdown (.md)", callback_data=f"EXPORT_MD_{note_id}"),
                InlineKeyboardButton("Word (.docx)", callback_data=f"EXPORT_DOCX_{note_id}"),
            ],
            [
                InlineKeyboardButton("PDF (.pdf)", callback_data=f"EXPORT_PDF_{note_id}")
            ],
            [
                InlineKeyboardButton("⬅️ " + self.localizer.get_string(lang_code, 'button_back', default="Back"),
                                     callback_data=f"ACTION_BACK_TO_MAIN_{note_id}")
            ]
        ]
        return text, InlineKeyboardMarkup(keyboard)

    def get_delete_confirmation(self, lang_code: str, note_id: ObjectId) -> Tuple[str, InlineKeyboardMarkup]:
        text = "Are you sure you want to permanently delete this note?"
        keyboard = [
            [
                InlineKeyboardButton("✅ Yes, delete it", callback_data=f"ACTION_DELETE_CONFIRM_{note_id}"),
                InlineKeyboardButton("❌ No, cancel", callback_data=f"ACTION_DELETE_CANCEL_{note_id}")
            ]
        ]
        return text, InlineKeyboardMarkup(keyboard)
