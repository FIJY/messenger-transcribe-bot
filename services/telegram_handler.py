# services/telegram_handler.py
import os
import logging
import tempfile
import uuid
import asyncio
from typing import Dict, Any, List, Optional
from telegram import Update, InlineKeyboardMarkup, Bot, Message, BotCommand, ParseMode
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
    def __init__(self, token: str, database: Database, s3_service: S3Service, payment_service: PaymentService):
        if not token: raise ValueError("Telegram token is required.")
        self.bot = Bot(token=token)
        self.database = database
        self.s3_service = s3_service
        self.celery_app_client = get_celery_app_client()
        self.payment_service = payment_service
        self.admin_telegram_id = os.getenv('ADMIN_TELEGRAM_ID')
        self.ui = TelegramUI()
        self.insight_service = InsightService()
        self.translation_service = TranslationService()

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

    async def _handle_callback_query(self, query: Update.callback_query):
        await query.answer()
        payload = query.data
        chat_id = query.message.chat_id
        message_id = query.message.message_id

        parts = payload.split('_')
        action_type = parts[0]
        action = parts[1]
        note_id = ObjectId(parts[2])

        if action_type != 'NOTE': return

        note = self.database.get_note_by_id(note_id)
        if not note:
            await query.edit_message_text("This note has been deleted.")
            return

        if action == 'SUMMARIZE':
            summary = self.insight_service.get_summary(note['content'])
            await self.send_message(chat_id, f"*Summary:*\n{summary or 'Could not generate summary.'}")
        elif action == 'TODO':
            self.database.update_note(note_id, {"type": "todo"})
            await query.edit_message_text(f"✅ Marked as TODO.\n\n```{note['content'][:100]}...```")
        elif action == 'TRANSLATE':
            if len(parts) == 3:  # User clicked "Translate", show language options
                text, reply_markup = self.ui.get_translation_language_options(note_id)
                await query.edit_message_text(text, reply_markup=reply_markup)
            else:  # User selected a language
                target_lang = parts[3]
                await query.edit_message_text(f"Translating to {target_lang.upper()}...")
                result = self.translation_service.translate_text(note['content'], target_lang)
                await self.send_message(chat_id, f"*{target_lang.upper()} Translation:*\n{result['translated_text']}")
        elif action == 'FIND':
            keywords = self.insight_service.get_keywords(note['content'])
            if not keywords:
                await self.send_message(chat_id, "Could not identify keywords to find related notes.")
                return
            related_notes = self.database.find_notes_by_keywords(note['user_id'], keywords)
            response = self.ui.format_related_notes(related_notes)
            await self.send_message(chat_id, response)
        elif action == 'DELETE':
            text, reply_markup = self.ui.get_delete_confirmation(note_id)
            await query.edit_message_text(text, reply_markup=reply_markup)
        elif action == 'DELETE' and parts[2] == 'CONFIRM':
            self.database.delete_note(ObjectId(parts[3]))
            await query.edit_message_text("🗑️ Note successfully deleted.")
        elif action == 'DELETE' and parts[2] == 'CANCEL':
            message, reply_markup = self.ui.get_note_created_message(note['content'], note_id)
            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

        # ... (остальные хендлеры без изменений)
        elif payload == 'SHOW_PAYMENT_QR':
            payment_qr_file_id = os.getenv('PAYMENT_QR_CODE_FILE_ID')
            if payment_qr_file_id:
                await self.bot.send_photo(chat_id, photo=payment_qr_file_id,
                                          caption="Scan this QR code in your ABA app.")
            else:
                await self.send_message(chat_id, "Sorry, the QR code is temporarily unavailable.")
        else:
            await self.send_message(chat_id, "Sorry, this action is no longer supported.")

    async def send_message(self, chat_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None):
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send message to Telegram chat {chat_id}: {e}")