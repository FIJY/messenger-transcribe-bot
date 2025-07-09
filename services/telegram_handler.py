# services/telegram_handler.py
import os
import logging
import tempfile
import uuid
import asyncio
from typing import Dict, Any, List, Optional
from telegram import Update, InlineKeyboardMarkup, Bot, Message, BotCommand
from telegram.constants import ParseMode
from datetime import datetime, timezone
from bson import ObjectId

from .database import Database
from .s3_service import S3Service
from .celery_client import get_celery_app_client
from .payment_service import PaymentService
from .telegram_ui import TelegramUI
from .insight_service import InsightService
from .translation_service import TranslationService

logger = logging.getLogger(__name__)


class TelegramHandler:
    def __init__(self, token: str, database: Database, s3_service: S3Service,
                 payment_service: PaymentService, insight_service: InsightService,
                 translation_service: TranslationService):
        if not token: raise ValueError("Telegram token is required.")
        self.bot = Bot(token=token)
        self.database = database
        self.s3_service = s3_service
        self.celery_app_client = get_celery_app_client()
        self.payment_service = payment_service
        self.admin_telegram_id = os.getenv('ADMIN_TELEGRAM_ID')
        self.ui = TelegramUI()
        self.insight_service = insight_service
        self.translation_service = translation_service

    async def set_bot_commands(self):
        commands = [
            BotCommand("start", "Restart the bot"),
            BotCommand("status", "Check your current plan"),
            BotCommand("search", "Search through your notes"),
            BotCommand("summary", "Get a summary of recent notes"),
            BotCommand("help", "Get help and information")
        ]
        try:
            await self.bot.set_my_commands(commands)
            logger.info("Bot commands have been set successfully.")
        except Exception as e:
            logger.error(f"Failed to set bot commands: {e}")

    async def handle_update(self, update_data: dict):
        update = Update.de_json(update_data, bot=self.bot)
        if update.callback_query:
            await self._handle_callback_query(update.callback_query)
            return
        if not update.message or not update.message.from_user:
            return

        user_id = str(update.message.from_user.id)
        chat_id = update.message.chat_id
        username = update.message.from_user.username

        if update.message.text and update.message.text.startswith('/'):
            await self._handle_command(user_id, chat_id, username, update.message.text)
            return

        user = self.database.get_user(user_id)
        if not user:
            user = await self._handle_start_command(user_id, chat_id, username)

        if update.message.photo:
            if user.get('state') == 'awaiting_payment_proof':
                await self.payment_service.handle_payment_proof(update.message)
                return

        file_to_process = update.message.document or update.message.audio or update.message.video or update.message.voice
        if file_to_process:
            await self._handle_file(file_to_process, user_id, chat_id)
        elif update.message.text:
            await self._handle_text_note(update.message.text, user_id, chat_id)

    async def _handle_command(self, user_id: str, chat_id: int, username: Optional[str], text: str):
        command_parts = text.split()
        command = command_parts[0]

        if command == '/start':
            await self._handle_start_command(user_id, chat_id, username)
        elif command == '/status':
            await self._handle_status_command(user_id, chat_id)
        elif command == '/help':
            bot_user = await self.bot.get_me()
            add_to_group_url = f"https://t.me/{bot_user.username}?startgroup=true"
            await self.send_message(chat_id, self.ui.get_help_message(add_to_group_url))
        elif command == '/search':
            query = " ".join(command_parts[1:])
            if not query:
                await self.send_message(chat_id, "Please provide a search term. Usage: `/search <your query>`")
                return
            await self.send_message(chat_id, f"🔍 Searching for notes matching: `{query}`...")
            notes = self.database.find_notes_by_keywords(user_id, [query])
            response_text = self.ui.format_search_results(notes, query)
            await self.send_message(chat_id, response_text)
        elif command == '/summary':
            await self.send_message(chat_id, "⏳ Generating summary for the last 7 days...")
            notes = self.database.get_notes_for_period(user_id, days=7)
            if not notes:
                await self.send_message(chat_id, "No notes found for the last 7 days.")
                return
            full_text = "\n\n---\n\n".join([note['content'] for note in notes])
            summary = self.insight_service.get_summary(full_text)
            await self.send_message(chat_id,
                                    f"📝 *Summary for the last 7 days:*\n\n{summary or 'Could not generate summary.'}")

        if user_id == self.admin_telegram_id:
            if command == '/confirm':
                await self._handle_confirm_command(command_parts, chat_id)
            if command == '/check':
                await self._handle_check_command(command_parts, chat_id)

    async def _handle_text_note(self, text: str, user_id: str, chat_id: int):
        try:
            note_id = self.database.save_note(user_id=user_id, content=text)
            message, reply_markup = self.ui.get_note_actions_message(note_id)
            await self.send_message(chat_id, f"✅ *Note created from text.*\n\n```{text[:250]}...```",
                                    reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error creating text note for user {user_id}: {e}")
            await self.send_message(chat_id, "❌ Sorry, an error occurred while saving your note.")

    async def _handle_file(self, file_obj, user_id: str, chat_id: int):
        await self.send_message(chat_id, "✅ File received. Processing...")
        local_file_path = None
        try:
            tg_file = await file_obj.get_file()
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(tg_file.file_path)[-1]) as temp_f:
                local_file_path = temp_f.name
                await tg_file.download_to_drive(custom_path=local_file_path)

            object_key = f"{uuid.uuid4()}{os.path.splitext(local_file_path)[-1]}"
            if not self.s3_service.upload_file(local_file_path, object_key):
                await self.send_message(chat_id, "❌ Server error: could not save file.");
                return
            if self.celery_app_client:
                self.celery_app_client.send_task('tasks.process_media', args=[user_id, object_key, {},
                                                                              {'platform': 'telegram',
                                                                               'chat_id': chat_id}])
        except Exception as e:
            logger.error(f"Error handling Telegram file: {e}", exc_info=True)
            await self.send_message(chat_id, "❌ An error occurred while processing your file.")
        finally:
            if local_file_path and os.path.exists(local_file_path): os.remove(local_file_path)

    async def _handle_start_command(self, user_id: str, chat_id: int, username: Optional[str]):
        user = self.database.get_user(user_id)
        if not user:
            user = self.database.create_user(user_id, username=username)
        await self.send_message(chat_id, self.ui.get_welcome_message())
        return user

    async def _handle_status_command(self, user_id: str, chat_id: int):
        user = self.database.get_user(user_id)
        if not user:
            await self.send_message(chat_id, "Please use /start first.")
            return
        message = self.ui.get_status_message(user)
        await self.send_message(chat_id, message)

    async def _handle_confirm_command(self, command_parts: List[str], chat_id: int):
        if len(command_parts) != 3:
            await self.send_message(chat_id, "❌ Incorrect format. Use: `/confirm <user_id> <plan_name>`")
            return

        user_to_activate, plan_name = command_parts[1], command_parts[2].lower()
        if plan_name not in ['basic', 'premium']:
            await self.send_message(chat_id, f"❌ Unknown plan '{plan_name}'.")
            return

        target_user = self.database.get_user(user_to_activate)
        if not target_user:
            await self.send_message(chat_id, f"❌ User with ID `{user_to_activate}` not found.")
            return

        if target_user.get('plan') == plan_name and target_user.get('subscription_expires_at',
                                                                    datetime.now(timezone.utc)) > datetime.now(
                timezone.utc):
            await self.send_message(chat_id, f"⚠️ **Warning:** User `{user_to_activate}` is already on this plan.")
            return

        self.database.update_user_subscription(user_to_activate, plan_name)
        await self.send_message(chat_id, f"✅ User `{user_to_activate}` upgraded to *{plan_name.capitalize()}*.")

        try:
            await self.send_message(int(user_to_activate), f"🎉 Your *{plan_name.capitalize()}* plan is now active!")
        except Exception as e:
            logger.error(f"Failed to send confirmation to user {user_to_activate}: {e}")
            await self.send_message(chat_id, f"⚠️ Could not notify user {user_to_activate} directly.")

    async def _handle_check_command(self, command_parts: List[str], chat_id: int):
        if len(command_parts) != 2:
            await self.send_message(chat_id, "❌ Incorrect format. Use: `/check <user_id>`")
            return

        user_to_check = command_parts[1]
        user_data = self.database.get_user(user_to_check)
        if not user_data:
            await self.send_message(chat_id, f"❌ User with ID `{user_to_check}` not found.")
            return

        message = self.ui.get_status_message(user_data)
        await self.send_message(chat_id, f"ℹ️ *Status for user `{user_to_check}`*\n\n" + message)

    async def _handle_callback_query(self, query: Update.callback_query):
        await query.answer()
        payload = query.data
        chat_id = query.message.chat_id
        user_id = str(query.from_user.id)

        parts = payload.split('_')
        action_type = parts[0]

        if action_type == 'CONFIRM' and parts[1] == 'OK':
            s3_key = "_".join(parts[2:])
            raw_transcription = self.database.get_raw_transcription(s3_key)
            if not raw_transcription:
                await query.edit_message_text("Sorry, I couldn't find the original transcription to create a note.")
                return

            note_id = self.database.save_note(
                user_id=user_id,
                content=raw_transcription.get('transcription', ''),
                s3_object_key=s3_key,
                detected_language=raw_transcription.get('detected_language'),
                duration_minutes=raw_transcription.get('duration_minutes', 0)
            )
            message, reply_markup = self.ui.get_note_actions_message(note_id)
            await query.edit_message_text(f"✅ Note created!\n\n{message}", reply_markup=reply_markup)
            return

        if action_type == 'RETRY' and parts[1] == 'LANG':
            s3_key = "_".join(parts[2:])
            user = self.database.get_user(user_id)
            reply_markup = self.ui.build_smart_buttons(user, 'transcription', s3_key)
            await query.edit_message_text("Got it. What was the language, actually?", reply_markup=reply_markup)
            return

        if action_type == 'NOTE':
            note_id = ObjectId(parts[-1])
            note = self.database.get_note_by_id(note_id)
            if not note:
                await query.edit_message_text("This note has been deleted.")
                return

            action = parts[1]

            if action == 'SUMMARIZE':
                await query.edit_message_text("📝 Generating summary...")
                summary = self.insight_service.get_summary(note['content'])
                await self.send_message(chat_id, f"*Summary:*\n{summary or 'Could not generate summary.'}")

            elif action == 'TODO':
                self.database.update_note(note_id, {"type": "todo"})
                await self.send_message(chat_id, "✅ Note marked as a TODO.")

            elif action == 'TRANSLATE':
                target_lang = parts[2] if len(parts) > 2 else None
                if not target_lang:
                    text, markup = self.ui.get_translation_language_options(note_id)
                    await query.edit_message_text(text, reply_markup=markup)
                else:
                    await query.edit_message_text(f"Translating to {target_lang.upper()}...")
                    result = self.translation_service.translate_text(note['content'], target_lang,
                                                                     note.get('source_language'))
                    if result['success']:
                        await self.send_message(chat_id,
                                                f"*{target_lang.upper()} Translation:*\n{result['translated_text']}")
                    else:
                        await self.send_message(chat_id, f"❌ Translation failed: {result['error']}")

            elif action == 'FIND':
                keywords = self.insight_service.get_keywords(note['content'])
                if not keywords:
                    await self.send_message(chat_id, "Could not identify keywords to find related notes.")
                    return
                await self.send_message(chat_id, f"🔍 Searching for notes related to: `{', '.join(keywords)}`")
                related_notes = self.database.find_notes_by_keywords(user_id, keywords, current_note_id=note_id)
                response = self.ui.format_related_notes(related_notes)
                await self.send_message(chat_id, response)

            elif action == 'DELETE':
                confirm_action = parts[2] if len(parts) > 2 else None
                if confirm_action == 'CONFIRM':
                    if self.database.delete_note(note_id):
                        await query.edit_message_text("🗑️ Note successfully deleted.")
                    else:
                        await query.edit_message_text("Could not delete the note.")
                elif confirm_action == 'CANCEL':
                    message, reply_markup = self.ui.get_note_actions_message(note_id)
                    await query.edit_message_text(f"✅ Note created!\n\n{message}", reply_markup=reply_markup)
                else:
                    text, markup = self.ui.get_delete_confirmation(note_id)
                    await query.edit_message_text(text, reply_markup=markup)

    async def send_message(self, chat_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None):
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send message to Telegram chat {chat_id}: {e}")