# services/telegram_handler.py
import os
import logging
import tempfile
import uuid
import asyncio
import re
import json
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
from .business_analyzer_service import BusinessAnalyzerService

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
        self.business_analyzer = BusinessAnalyzerService()
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

        file_to_process = update.message.document or update.message.audio or update.message.video or update.message.voice or update.message.video_note
        url_match = re.search(r'https?://\S+', update.message.text or "")

        if file_to_process:
            await self._handle_file_upload(file_to_process, user_id, chat_id)
        elif url_match:
            await self._handle_url(url_match.group(0), user_id, chat_id)
        elif update.message.text:
            await self._handle_text_note(update.message.text, user_id, chat_id)

    async def _handle_url(self, url: str, user_id: str, chat_id: int):
        await self.send_message(chat_id, "🔗 Link received. Starting download...")

        local_file_path = None
        try:
            local_file_path, error_type = self.downloader_service.download_audio(url)

            if not local_file_path:
                if error_type == 'LOGIN_REQUIRED':
                    await self.send_message(chat_id,
                                            "❌ This content is private or protected (e.g., private YouTube, Instagram Reels). Please download it manually and send me the file.")
                else:
                    await self.send_message(chat_id,
                                            "❌ Failed to download audio from the link. The link might be broken or from an unsupported site.")
                return

            await self._process_local_file(local_file_path, user_id, chat_id, from_url=True)
        except Exception as e:
            logger.error(f"Error handling URL {url}: {e}", exc_info=True)
            await self.send_message(chat_id, "❌ An error occurred while processing your link.")
        finally:
            if local_file_path and os.path.exists(local_file_path):
                os.remove(local_file_path)

    async def _handle_callback_query(self, query: Update.callback_query):
        await query.answer()
        payload = query.data
        chat_id = query.message.chat_id

        parts = payload.split('_')
        action_type = parts[0]
        action_name = parts[1]

        # Обработка интерактивного бизнес-отчета
        if action_type == 'BIZ':
            section_key = action_name
            note_id = ObjectId(parts[2])
            note = self.database.get_note_by_id(note_id)
            if not note or 'business_analysis' not in note:
                return await self.send_message(chat_id, "Analysis data not found for this note.")

            analysis_data = note['business_analysis']
            section_data = analysis_data.get(section_key)

            if not section_data:
                return await self.send_message(chat_id, f"Section '{section_key}' not found in the analysis.")

            formatted_section = f"*{section_key.replace('_', ' ').title()}*:\n\n"
            if isinstance(section_data, (dict, list)):
                formatted_section += "```json\n" + json.dumps(section_data, indent=2, ensure_ascii=False) + "\n```"
            else:
                formatted_section += str(section_data)
            await self.send_message(chat_id, formatted_section)
            return

        # Основная логика
        try:
            note_id_str = parts[2]
            note_id = ObjectId(note_id_str)
        except (IndexError, Exception):
            return await self.send_message(chat_id, f"Error processing action: Invalid callback data '{payload}'")

        note = self.database.get_note_by_id(note_id)
        if not note:
            return await query.edit_message_text("This menu is no longer active as the note was deleted.",
                                                 reply_markup=None)

        if action_type == 'ACTION':
            # ... (Логика для ACTION_BACK, ACTION_REPORT, ACTION_SUMMARIZE, и др.)
            if action_name == 'BACK':
                text, markup = self.ui.get_main_actions_menu(note_id)
                await query.edit_message_text(text, reply_markup=markup)

            elif action_name == 'REPORT':
                text, markup = self.ui.get_template_selection_message(note_id)
                await query.edit_message_text(text, reply_markup=markup)

            elif action_name == 'SUMMARIZE':
                await self.send_message(chat_id, "🤖 Generating simple summary...")
                summary = self.insight_service.get_summary(note['content'])
                await self.send_message(chat_id, f"*Summary:*\n{summary or 'Could not generate summary.'}")

            elif action_name == 'BIZANALYSIS':  # ИСПРАВЛЕННЫЙ action_name
                await self.send_message(chat_id,
                                        "🤖 Starting comprehensive business analysis. This may take several minutes...")
                analysis_result = self.business_analyzer.run_comprehensive_analysis(note['content'])
                if not analysis_result:
                    return await self.send_message(chat_id, "❌ Failed to perform business analysis.")

                self.database.update_note(note_id,
                                          {"business_analysis": analysis_result, "tags": ["business_analysis"]})
                text, markup = self.ui.get_business_analysis_menu(note_id)
                await query.edit_message_text(text, reply_markup=markup)

            elif action_name == 'TRANSLATE':
                if len(parts) > 3:
                    target_lang = parts[3]
                    await self.send_message(chat_id, f"🌐 Translating to {target_lang.upper()}...")
                    result = self.translation_service.translate_text(note['content'], target_lang,
                                                                     note.get('source_language'))
                    response_text = f"*{target_lang.upper()} Translation:*\n{result['translated_text']}" if result[
                        'success'] else f"❌ Translation failed: {result['error']}"
                    await self.send_message(chat_id, response_text)

                    text, markup = self.ui.get_main_actions_menu(note_id)
                    await query.edit_message_text(text, reply_markup=markup)
                else:
                    text, markup = self.ui.get_translation_language_options(note_id)
                    await query.edit_message_text(text, reply_markup=markup)

            elif action_name == 'DELETE':
                text, markup = self.ui.get_delete_confirmation(note_id)
                await query.edit_message_text(text, reply_markup=markup)

            elif action_name == 'DELETECONFIRM':
                if self.database.delete_note(note_id):
                    await query.edit_message_text("🗑️ Note successfully deleted.", reply_markup=None)

            elif action_name == 'DELETECANCEL':
                text, markup = self.ui.get_main_actions_menu(note_id)
                await query.edit_message_text(text, reply_markup=markup)

        elif action_type == 'TEMPLATE':
            # ... (логика без изменений)
            pass

    # ... (все остальные методы без изменений)
    async def _handle_command(self, user_id: str, chat_id: int, username: Optional[str], text: str):
        pass

    async def _handle_text_note(self, text: str, user_id: str, chat_id: int):
        pass

    async def _process_local_file(self, local_file_path: str, user_id: str, chat_id: int, from_url: bool = False):
        pass

    async def _handle_file_upload(self, file_obj: Message, user_id: str, chat_id: int):
        pass

    async def _handle_start_command(self, user_id: str, chat_id: int, username: Optional[str]):
        pass

    async def _handle_status_command(self, user_id: str, chat_id: int):
        pass

    async def send_message(self, chat_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None):
        pass