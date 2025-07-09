# services/telegram_handler.py
import os
import logging
import tempfile
import uuid
import asyncio
import re
from typing import Dict, Any, List, Optional
from telegram import Update, InlineKeyboardMarkup, Bot, Message, BotCommand
from telegram.constants import ParseMode
from bson import ObjectId

from .database import Database
from .s3_service import S3Service
from .celery_client import get_celery_app_client
from .payment_service import PaymentService
from .telegram_ui import TelegramUI
from .insight_service import InsightService
from .translation_service import TranslationService
from .downloader_service import DownloaderService

logger = logging.getLogger(__name__)


class TelegramHandler:
    def __init__(self, token: str, database: Database, s3_service: S3Service,
                 payment_service: PaymentService, insight_service: InsightService,
                 translation_service: TranslationService):
        if not token: raise ValueError("Telegram token is required.")
        self.bot = Bot(token=token)
        self.database = database
        self.s3_service = s3_service
        self.downloader_service = DownloaderService()
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

        # Добавлена поддержка видео-кружочков (video_note)
        file_to_process = update.message.document or update.message.audio or update.message.video or update.message.voice or update.message.video_note
        url_match = re.search(r'https?://\S+', update.message.text or "")

        if file_to_process:
            await self._handle_file_upload(file_to_process, user_id, chat_id)
        elif url_match:
            await self._handle_url(url_match.group(0), user_id, chat_id)
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
            notes = self.database.search_notes_by_query(user_id, query)
            response_text = self.ui.format_search_results(notes, query)
            await self.send_message(chat_id, response_text)
        elif command == '/summary':
            await self.send_message(chat_id,
                                    "This command is deprecated. Please use the 'Create Smart Report' button on a specific note.")

        if user_id == self.admin_telegram_id:
            if command == '/confirm':
                await self._handle_confirm_command(command_parts, chat_id)
            if command == '/check':
                await self._handle_check_command(command_parts, chat_id)

    async def _handle_text_note(self, text: str, user_id: str, chat_id: int):
        try:
            note_id = self.database.save_note(user_id=user_id, content=text, tags=['plain_text'])
            await self.send_message(chat_id, f"✅ *Note saved:* ```{text[:250]}...```")
            message, reply_markup = self.ui.get_main_actions_menu(note_id)
            await self.send_message(chat_id, message, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error creating text note for user {user_id}: {e}")
            await self.send_message(chat_id, "❌ Sorry, an error occurred while saving your note.")

    async def _handle_url(self, url: str, user_id: str, chat_id: int):
        await self.send_message(chat_id, "🔗 Link received. Starting download...")

        local_file_path = None
        try:
            local_file_path = self.downloader_service.download_audio(url)
            if not local_file_path:
                await self.send_message(chat_id,
                                        "❌ Failed to download audio from the link. The link might be broken, private, or protected.")
                return

            await self._process_local_file(local_file_path, user_id, chat_id, from_url=True)
        except Exception as e:
            logger.error(f"Error handling URL {url}: {e}", exc_info=True)
            await self.send_message(chat_id, "❌ An error occurred while processing your link.")
        finally:
            if local_file_path and os.path.exists(local_file_path):
                os.remove(local_file_path)

    async def _process_local_file(self, local_file_path: str, user_id: str, chat_id: int, from_url: bool = False):
        try:
            object_key = f"{uuid.uuid4()}{os.path.splitext(local_file_path)[-1]}"
            if not self.s3_service.upload_file(local_file_path, object_key):
                await self.send_message(chat_id, "❌ Server error: could not upload file to storage.")
                return

            if self.celery_app_client:
                logger.info(f"Sending task to Celery for object {object_key}")
                self.celery_app_client.send_task('tasks.process_media', args=[user_id, object_key, {},
                                                                              {'platform': 'telegram',
                                                                               'chat_id': chat_id}])
                if from_url:
                    await self.send_message(chat_id, "✅ Download complete. Your file is now being processed...")
        except Exception as e:
            logger.error(f"Error in _process_local_file: {e}", exc_info=True)
            await self.send_message(chat_id, "❌ An error occurred during file processing.")

    async def _handle_file_upload(self, file_obj, user_id: str, chat_id: int):
        await self.send_message(chat_id, "✅ File received. Processing...")
        local_file_path = None
        try:
            tg_file = await file_obj.get_file()
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(tg_file.file_path)[-1]) as temp_f:
                local_file_path = temp_f.name
                await tg_file.download_to_drive(custom_path=local_file_path)

            await self._process_local_file(local_file_path, user_id, chat_id)
        except Exception as e:
            logger.error(f"Error handling Telegram file upload: {e}", exc_info=True)
            await self.send_message(chat_id, "❌ An error occurred while processing your file.")
        finally:
            if local_file_path and os.path.exists(local_file_path):
                os.remove(local_file_path)

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

        parts = payload.split('_')
        action_type = parts[0]
        action_name = parts[1]

        try:
            note_id_str = parts[2] if len(parts) > 2 else None
            note_id = ObjectId(note_id_str) if note_id_str else None
        except Exception:
            await self.send_message(chat_id, "Error processing action: Invalid Note ID.")
            return

        if not note_id:
            await self.send_message(chat_id, "Error processing action: Note ID not found.")
            return

        note = self.database.get_note_by_id(note_id)
        if not note:
            await query.edit_message_text("This menu is no longer active as the note was deleted.", reply_markup=None)
            return

        if action_type == 'ACTION':
            if action_name == 'REPORT':
                text, markup = self.ui.get_template_selection_message(note_id)
                await query.edit_message_text(text, reply_markup=markup)

            elif action_name == 'SUMMARIZE':
                await self.send_message(chat_id, "🤖 Generating summary...")
                summary = self.insight_service.get_summary(note['content'])
                await self.send_message(chat_id, f"*Summary:*\n{summary or 'Could not generate summary.'}")

            elif action_name == 'TRANSLATE':
                if len(parts) > 3:
                    target_lang = parts[3]
                    await self.send_message(chat_id, f"🌐 Translating to {target_lang.upper()}...")
                    result = self.translation_service.translate_text(note['content'], target_lang,
                                                                     note.get('source_language'))
                    response_text = f"*{target_lang.upper()} Translation:*\n{result['translated_text']}" if result[
                        'success'] else f"❌ Translation failed: {result['error']}"
                    await self.send_message(chat_id, response_text)
                else:
                    text, markup = self.ui.get_translation_language_options(note_id)
                    await query.edit_message_text(text, reply_markup=markup)

            elif action_name == 'DELETE':
                if len(parts) > 2 and parts[2] == 'CONFIRM':
                    if self.database.delete_note(note_id):
                        await query.edit_message_text("🗑️ Note successfully deleted.", reply_markup=None)
                    else:
                        await query.edit_message_text("Could not delete the note.")
                elif len(parts) > 2 and parts[2] == 'CANCEL':
                    text, markup = self.ui.get_main_actions_menu(note_id)
                    await query.edit_message_text(text, reply_markup=markup)
                else:
                    text, markup = self.ui.get_delete_confirmation(note_id)
                    await query.edit_message_text(text, reply_markup=markup)

        elif action_type == 'TEMPLATE':
            template_key = action_name
            await self.send_message(chat_id, f"🤖 Generating report with template '{template_key}'...")

            report_text = self.insight_service.create_report(note['content'], template_key)
            if not report_text:
                await self.send_message(chat_id, "❌ Sorry, failed to generate the report.")
                return

            report_name = self.insight_service.REPORT_PROMPTS.get(template_key, {}).get('name', 'Report')
            final_report_header = f"📊 *Report: {report_name}*"
            await self.send_message(chat_id, f"{final_report_header}\n\n{report_text}")

            # Возвращаем исходное меню действий, чтобы пользователь мог продолжить
            text, markup = self.ui.get_main_actions_menu(note_id)
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