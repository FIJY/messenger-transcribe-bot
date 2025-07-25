# services/callback_query_handler.py
import logging
import json
from typing import TYPE_CHECKING, Any, Optional
from telegram import Update
from bson import ObjectId, errors as bson_errors

# Use TYPE_CHECKING to avoid circular import errors at runtime
if TYPE_CHECKING:
    from .telegram_handler import TelegramHandler

logger = logging.getLogger(__name__)


class CallbackQueryHandler:
    def __init__(self, main_handler: 'TelegramHandler'):
        # Get all dependencies from the main handler instance
        self.main_handler = main_handler
        self.bot = main_handler.bot
        self.db = main_handler.database
        self.ui = main_handler.ui
        self.localizer = main_handler.localizer
        self.insight_service = main_handler.insight_service
        self.translation_service = main_handler.translation_service
        self.business_analyzer = main_handler.business_analyzer
        self.export_service = main_handler.export_service

    async def handle(self, query: Update.callback_query, user_lang: str):
        payload = query.data
        parts = payload.split('_')

        if parts[0] == 'SHOW' and parts[1] == 'LANG' and parts[2] == 'MENU':
            await self._show_language_menu(query, payload, user_lang)
            return

        if parts[0] in ['TRANSLATE', 'RETRANSCRIBE']:
            await self._perform_language_action(query, payload, user_lang)
            return

        await self._handle_general_action(query, payload, user_lang)

    async def _show_language_menu(self, query: Update.callback_query, payload: str, user_lang: str):
        try:
            _, _, _, action_type, page_str, note_id_str = payload.split('_')
            note_id = ObjectId(note_id_str)
            text, markup = self.ui.get_language_selection_menu(user_lang, note_id, action_type,
                                                               self.main_handler.SUPPORTED_LANGUAGES,
                                                               page=int(page_str))
            await query.edit_message_text(text, reply_markup=markup)
        except (IndexError, ValueError, bson_errors.InvalidId) as e:
            logger.error(f"Error parsing language menu callback: {payload}, error: {e}")

    async def _perform_language_action(self, query: Update.callback_query, payload: str, user_lang: str):
        try:
            action_type, target_lang, note_id_str = payload.split('_')
            note_id = ObjectId(note_id_str)
            note = self.db.get_note_by_id(note_id)
            if not note:
                await query.edit_message_text("This menu is no longer active.", reply_markup=None)
                return

            if action_type == 'TRANSLATE':
                await self._perform_translation(query, note, target_lang, user_lang)
            else:  # RETRANSCRIBE
                await self.main_handler._perform_retranscribe(query, note, target_lang, user_lang)
        except (IndexError, ValueError, bson_errors.InvalidId) as e:
            logger.error(f"Error parsing action callback: {payload}, error: {e}")

    async def _handle_general_action(self, query: Update.callback_query, payload: str, user_lang: str):
        try:
            parts = payload.split('_')
            action = '_'.join(parts[:-1])
            note_id = ObjectId(parts[-1])
            note = self.db.get_note_by_id(note_id)
            if not note:
                await query.edit_message_text("This menu is no longer active.", reply_markup=None)
                return

            if action.startswith('EXPORT'):
                file_format = action.split('_')[1].lower()
                await self._handle_export_action(query, note, file_format, user_lang)
            elif action == 'ACTION_BACK_TO_MAIN':
                text, markup = self.ui.get_main_actions_menu(user_lang, note_id)
                await query.edit_message_text(text, reply_markup=markup)
            elif action == 'ACTION_CHAT':
                new_state = {'mode': 'chatting', 'note_id': str(note_id)}
                self.db.update_user(str(query.from_user.id), {'state': new_state})
                await self.bot.send_message(query.message.chat_id,
                                            self.localizer.get_string(user_lang, 'chat_mode_entered'))
            else:
                await self._handle_main_action(query, note, action, user_lang)
        except (IndexError, bson_errors.InvalidId) as e:
            logger.warning(f"Could not parse callback data or find note: {payload}, error: {e}")

    async def _perform_translation(self, query: Update.callback_query, note: dict, target_lang: str, lang_code: str):
        note_id = note['_id']
        chat_id = query.message.chat_id
        await self.bot.send_chat_action(chat_id, 'typing')
        translated_text = self.translation_service.translate_text(note['content'], target_language=target_lang)
        header = self.main_handler.SUPPORTED_LANGUAGES.get(target_lang, target_lang)
        response_text = f"*{header}:*\n```\n{translated_text or 'Could not translate.'}\n```"
        await self.main_handler.send_message(chat_id, response_text)
        await self.main_handler._send_text_as_file(chat_id, translated_text, f"translation_{target_lang}_{note_id}.txt",
                                                   f"Перевод на {header}")
        text, markup = self.ui.get_main_actions_menu(lang_code, note_id)
        await query.edit_message_text(text, reply_markup=markup)

    async def _handle_export_action(self, query: Update.callback_query, note: dict, file_format: str, lang_code: str):
        await self.main_handler._handle_export_action(query, note, file_format, lang_code)

    async def _handle_main_action(self, query: Update.callback_query, note: dict, action: str, lang_code: str):
        await self.main_handler._handle_main_action(query, note, action, lang_code)
