# services/telegram_ui.py
import os
from typing import Dict, Any, List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from bson import ObjectId

from .database import PLANS
from config.transcrib_suggestion_config import DEFAULT_POPULAR_TRANSLATION_LANGS


class TelegramUI:
    def __init__(self):
        self.base_url = os.getenv('RENDER_EXTERNAL_URL', 'https://your-app-name.onrender.com')
        self.support_contact = os.getenv('SUPPORT_CONTACT')

    def get_welcome_message(self) -> str:
        return (
            "🎉 *Welcome to your AI Notes Assistant!*\n\n"
            "To get started, just send me a voice message, an audio/video file, a text message, or a link to a YouTube video.\n\n"
            "Type /help to see all available commands."
        )

    def get_help_message(self, add_to_group_url: str) -> str:
        basic_plan = PLANS['basic']
        premium_plan = PLANS['premium']
        help_text = (
            "🤖 *Bot Help & Information*\n\n"
            "**How to Use Me:**\n"
            "Send me a voice message, audio/video file, text message, or a link, and I will turn it into a structured note.\n\n"
            "💡 **Совет:** Чтобы отправить файл размером больше 20 МБ, прикрепите его как **'Файл'**, а не как 'Аудио' или 'Видео'.\n\n"
            "**Available Commands:**\n"
            "`/start` - Restart the bot.\n"
            "`/status` - Check your current plan.\n"
            "`/search <text>` - Find text in your notes.\n"
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

    def get_main_actions_menu(self, note_id: ObjectId) -> tuple[str, InlineKeyboardMarkup]:
        message_text = "What would you like to do with this transcription?"
        keyboard = [
            [
                InlineKeyboardButton("📊 Create Smart Report", callback_data=f"ACTION_REPORT_{note_id}"),
                InlineKeyboardButton("🌐 Translate", callback_data=f"ACTION_TRANSLATE_{note_id}")
            ],
            [
                InlineKeyboardButton("📝 Simple Summary", callback_data=f"ACTION_SUMMARIZE_{note_id}"),
                # НОВАЯ КНОПКА
                InlineKeyboardButton("📜 Create Subtitles (.srt)", callback_data=f"ACTION_SUBTITLES_{note_id}")
            ],
            [
                InlineKeyboardButton("📈 Business Analysis", callback_data=f"ACTION_BIZANALYSIS_{note_id}"),
                InlineKeyboardButton("🗑️ Delete Note", callback_data=f"ACTION_DELETE_{note_id}")
            ]
        ]
        return message_text, InlineKeyboardMarkup(keyboard)

    def get_template_category_menu(self, note_id: ObjectId) -> tuple[str, InlineKeyboardMarkup]:
        message_text = "Please choose a report category:"
        keyboard = [
            [
                InlineKeyboardButton("📁 General", callback_data=f"CATEGORY_GENERAL_{note_id}"),
                InlineKeyboardButton("💼 Business", callback_data=f"CATEGORY_BUSINESS_{note_id}")
            ],
            [
                InlineKeyboardButton("👥 Partnership", callback_data=f"CATEGORY_PARTNERSHIP_{note_id}"),
                InlineKeyboardButton("⬅️ Back to Main Menu", callback_data=f"ACTION_BACK_MAIN_{note_id}")
            ]
        ]
        return message_text, InlineKeyboardMarkup(keyboard)

    def get_template_selection_message(self, note_id: ObjectId, category: str) -> tuple[str, InlineKeyboardMarkup]:
        message_text = f"Selected category: *{category.capitalize()}*. Now choose a template:"
        keyboard = []
        if category == 'GENERAL':
            keyboard.extend([
                [InlineKeyboardButton("📝 Meeting Minutes", callback_data=f"TEMPLATE_MEETING_{note_id}")],
                [InlineKeyboardButton("🎙️ Podcast Show Notes", callback_data=f"TEMPLATE_PODCAST_{note_id}")],
                [InlineKeyboardButton("🎯 Coaching Session", callback_data=f"TEMPLATE_COACHING_{note_id}")],
            ])
        elif category == 'BUSINESS':
            keyboard.extend([
                [InlineKeyboardButton("💡 Client Briefing", callback_data=f"TEMPLATE_BRIEFING_{note_id}")],
                [InlineKeyboardButton("📞 Sales Call Analysis", callback_data=f"TEMPLATE_SALES_CALL_{note_id}")],
                [InlineKeyboardButton("🤵 Interview Summary", callback_data=f"TEMPLATE_INTERVIEW_{note_id}")],
            ])
        elif category == 'PARTNERSHIP':
            keyboard.extend([
                [InlineKeyboardButton("🤝 Partnership Discussion",
                                      callback_data=f"TEMPLATE_PARTNERSHIP_MEETING_{note_id}")],
                [InlineKeyboardButton("⚖️ Business Negotiation",
                                      callback_data=f"TEMPLATE_BUSINESS_NEGOTIATION_{note_id}")],
                [InlineKeyboardButton("🕵️ Due Diligence", callback_data=f"TEMPLATE_DUE_DILIGENCE_{note_id}")],
                [InlineKeyboardButton("😡 Conflict Resolution",
                                      callback_data=f"TEMPLATE_CONFLICT_RESOLUTION_{note_id}")],
            ])

        keyboard.append([InlineKeyboardButton("⬅️ Back to Categories", callback_data=f"ACTION_REPORT_{note_id}")])
        return message_text, InlineKeyboardMarkup(keyboard)

    def get_delete_confirmation(self, note_id: ObjectId) -> tuple[str, InlineKeyboardMarkup]:
        return (
            "Are you sure you want to delete this note?",
            InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Yes, delete", callback_data=f"ACTION_DELETE_CONFIRM_{note_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"ACTION_DELETE_CANCEL_{note_id}")
            ]])
        )

    def get_translation_language_options(self, note_id: ObjectId) -> tuple[str, InlineKeyboardMarkup]:
        buttons = []
        for lang in DEFAULT_POPULAR_TRANSLATION_LANGS:
            buttons.append(InlineKeyboardButton(f"{lang['flag']} {lang['title']}",
                                                callback_data=f"ACTION_TRANSLATE_{note_id}_{lang['code']}"))

        keyboard = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
        keyboard.append([InlineKeyboardButton("⬅️ Back to Main Menu", callback_data=f"ACTION_BACK_MAIN_{note_id}")])

        return "Please select the target language:", InlineKeyboardMarkup(keyboard)

    def get_business_analysis_menu(self, note_id: ObjectId) -> tuple[str, InlineKeyboardMarkup]:
        message_text = "Comprehensive analysis complete. Choose a section to view:"
        keyboard = [
            [
                InlineKeyboardButton("📝 Summary", callback_data=f"BIZ_summary_{note_id}"),
                InlineKeyboardButton("🔑 Keywords", callback_data=f"BIZ_keywords_{note_id}"),
            ],
            [
                InlineKeyboardButton("✅ Action Items", callback_data=f"BIZ_action_items_{note_id}"),
                InlineKeyboardButton("⚖️ Risks", callback_data=f"BIZ_risk_assessment_{note_id}"),
            ],
            [
                InlineKeyboardButton("🤝 Dynamics", callback_data=f"BIZ_dynamics_{note_id}"),
                InlineKeyboardButton("💰 Deal Terms", callback_data=f"BIZ_deal_terms_{note_id}"),
            ],
            [
                InlineKeyboardButton("📋 Next Agenda", callback_data=f"BIZ_next_agenda_{note_id}"),
                InlineKeyboardButton("😊 Sentiment", callback_data=f"BIZ_sentiment_{note_id}"),
            ],
            [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data=f"ACTION_BACK_MAIN_{note_id}")]
        ]
        return message_text, InlineKeyboardMarkup(keyboard)

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