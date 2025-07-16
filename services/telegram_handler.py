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
from bson import ObjectId, errors as bson_errors

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

        if user_id == self.admin_telegram_id:
            pass  # Admin commands logic here

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

    async def _handle_file_upload(self, file_obj: Message, user_id: str, chat_id: int):
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

    async def _handle_callback_query(self, query: Update.callback_query):
        await query.answer()
        payload = query.data
        chat_id = query.message.chat_id

        parts = payload.split('_')

        # Новый, надежный парсер
        try:
            action = '_'.join(parts[:-1])  # Действие - все, кроме последнего элемента
            note_id = ObjectId(parts[-1])  # ID заметки - всегда последний элемент
        except (IndexError, bson_errors.InvalidId):
            return await self.send_message(chat_id, f"Error processing action: Invalid callback data '{payload}'")

        note = self.database.get_note_by_id(note_id)
        if not note:
            return await query.edit_message_text("This menu is no longer active as the note was deleted.",
                                                 reply_markup=None)

        action_type = action.split('_')[0]

        # Обработка интерактивного бизнес-отчета
        if action_type == 'BIZ':
            section_key = action.split('_')[1]
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
        if action_type == 'ACTION':
            action_name = action.split('_')[1]

            if action_name == 'BACK' and parts[1] == 'MAIN':
                text, markup = self.ui.get_main_actions_menu(note_id)
                await query.edit_message_text(text, reply_markup=markup)

            elif action_name == 'REPORT':
                text, markup = self.ui.get_template_category_menu(note_id)
                await query.edit_message_text(text, reply_markup=markup)

            elif action_name == 'SUMMARIZE':
                await self.send_message(chat_id, "🤖 Generating simple summary...")
                summary = self.insight_service.get_summary(note['content'])
                await self.send_message(chat_id, f"*Summary:*\n{summary or 'Could not generate summary.'}")

            elif action_name == 'BIZANALYSIS':
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
                    target_lang = parts[-1]
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

        elif action_type == 'CATEGORY':
            category_name = action.split('_')[1]
            text, markup = self.ui.get_template_selection_message(note_id, category_name)
            await query.edit_message_text(text, reply_markup=markup)

        elif action_type == 'TEMPLATE':
            template_key = '_'.join(parts[1:-1])  # Собираем полный ключ шаблона

            report_name = self.insight_service.REPORT_PROMPTS.get(template_key, {}).get('name', 'Report')
            await self.send_message(chat_id, f"🤖 Generating report using template '{report_name}'...")

            report_text = self.insight_service.create_report(note['content'], template_key)

            if not report_text:
                await self.send_message(chat_id, "❌ Sorry, failed to generate the report.")
            else:
                final_report_header = f"📊 *Report: {report_name}*"
                await self.send_message(chat_id, f"{final_report_header}\n\n{report_text}")

                updated_content = f"# {report_name}\n\n{report_text}\n\n---\n\n## Original Transcription\n\n{note['content']}"
                self.database.update_note(note_id, {"content": updated_content, "tags": [template_key.lower()]})

                new_menu_text, new_markup = self.ui.get_main_actions_menu(note_id)
                await self.send_message(chat_id, new_menu_text, reply_markup=new_markup)

            await query.delete_message()

    async def send_message(self, chat_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None):
        try:
            if len(text) > 4096:
                parts = text.split('\n\n')
                current_message = ""
                for part in parts:
                    if len(current_message) + len(part) + 2 > 4096:
                        await self.bot.send_message(chat_id=chat_id, text=current_message,
                                                    parse_mode=ParseMode.MARKDOWN)
                        current_message = part
                    else:
                        current_message += "\n\n" + part
                if current_message:
                    await self.bot.send_message(chat_id=chat_id, text=current_message, parse_mode=ParseMode.MARKDOWN)

                if reply_markup:
                    await self.bot.send_message(chat_id=chat_id, text="Actions:", reply_markup=reply_markup)
            else:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"Failed to send message to Telegram chat {chat_id}: {e}")