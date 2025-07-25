# services/telegram_handler.py
import os
import logging
import tempfile
import uuid
import json
from typing import Dict, Any, List, Optional
from telegram import Update, Bot, Message, BotCommand
from telegram.constants import ParseMode
from bson import ObjectId, errors as bson_errors

from .database import Database
from .s3_service import S3Service
from .celery_client import get_celery_app_client
from .payment_service import PaymentService
from .localization_service import LocalizationService
from .telegram_ui import TelegramUI
from .insight_service import InsightService
from .translation_service import TranslationService
from .downloader_service import DownloaderService
from .business_analyzer_service import BusinessAnalyzerService
from .youtube_service import YouTubeService
from .export_service import ExportService

# Import new handlers from the same directory
from .command_handler import CommandHandler
from .message_handler import MessageHandler
from .callback_query_handler import CallbackQueryHandler

logger = logging.getLogger(__name__)


class TelegramHandler:
    SUPPORTED_LANGUAGES = {
        'en': 'English', 'ru': 'Русский', 'uk': 'Українська', 'de': 'Deutsch',
        'fr': 'Français', 'es': 'Español', 'it': 'Italiano', 'pl': 'Polski',
        'zh': '中文', 'ja': '日本語', 'ko': '한국어', 'ar': 'العربية',
        'pt': 'Português', 'tr': 'Türkçe', 'nl': 'Nederlands', 'sv': 'Svenska'
    }

    def __init__(self, token: str, database: Database, s3_service: S3Service,
                 payment_service: PaymentService, insight_service: InsightService,
                 translation_service: TranslationService, downloader_service: DownloaderService,
                 business_analyzer: BusinessAnalyzerService, youtube_service: YouTubeService):
        if not token: raise ValueError("Telegram token is required.")
        # Core services
        self.bot = Bot(token=token)
        self.database = database
        self.s3_service = s3_service
        self.payment_service = payment_service
        self.insight_service = insight_service
        self.translation_service = translation_service
        self.downloader_service = downloader_service
        self.business_analyzer = business_analyzer
        self.youtube_service = youtube_service
        self.celery_app_client = get_celery_app_client()
        self.admin_telegram_id = os.getenv('ADMIN_TELEGRAM_ID')
        self.localizer = LocalizationService()
        self.ui = TelegramUI(self.localizer)
        self.export_service = ExportService  # Pass the class, not an instance

        # Initialize sub-handlers
        self.command_handler = CommandHandler(self.bot, self.database, self.ui, self.localizer, self.admin_telegram_id)
        self.message_handler = MessageHandler(self.bot, self.database, self.ui, self.localizer, self.s3_service,
                                              self.celery_app_client, self.insight_service, self.payment_service)
        self.callback_query_handler = CallbackQueryHandler(self)

    async def set_bot_commands(self):
        commands = [
            BotCommand("start", "Restart the bot"), BotCommand("status", "Check your current plan"),
            BotCommand("search", "Search through your notes"), BotCommand("help", "Get help and information"),
            BotCommand("cancel", "Exit current mode (e.g., chat mode)")
        ]
        try:
            await self.bot.set_my_commands(commands)
            logger.info("Bot commands have been set successfully.")
        except Exception as e:
            logger.error(f"Failed to set bot commands: {e}")

    async def handle_update(self, update_data: dict):
        update = Update.de_json(update_data, bot=self.bot)
        effective_user = update.effective_user
        if not effective_user: return

        user_id = str(effective_user.id)
        user = self.database.get_user(user_id)
        lang_code = effective_user.language_code or 'en'

        if not user:
            user = self.database.create_user(user_id, username=effective_user.username, language_code=lang_code)
        elif user.get('language_code') != lang_code:
            self.database.update_user(user_id, {'language_code': lang_code})
            user['language_code'] = lang_code

        user_lang = user.get('language_code', 'en')

        if update.callback_query:
            await self.callback_query_handler.handle(update.callback_query, user_lang)
        elif update.message:
            if update.message.text and update.message.text.startswith('/'):
                await self.command_handler.handle(update.message, user_lang)
            else:
                await self.message_handler.handle(update.message, user, user_lang)

    # --- SHARED HELPER METHODS (Used by sub-handlers) ---
    async def send_message(self, chat_id: int, text: str, **kwargs):
        try:
            return await self.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN, **kwargs)
        except Exception:
            try:
                return await self.bot.send_message(chat_id=chat_id, text=text, **kwargs)
            except Exception as e:
                logger.error(f"Failed to send message even without parse_mode: {e}")
                return None

    def _generate_srt_from_text(self, text: str) -> str:
        words = text.split()
        chunk_size = 15
        duration_ms = 5000
        srt_content = []
        start_time_ms = 0
        for i, chunk_start in enumerate(range(0, len(words), chunk_size)):
            chunk_words = words[chunk_start:chunk_start + chunk_size]
            if not chunk_words: continue
            end_time_ms = start_time_ms + duration_ms

            def format_time(ms):
                s, ms = divmod(ms, 1000);
                m, s = divmod(s, 60);
                h, m = divmod(m, 60)
                return f"{h:02}:{m:02}:{s:02},{ms:03}"

            start_formatted = format_time(start_time_ms)
            end_formatted = format_time(end_time_ms)
            srt_content.extend([str(i + 1), f"{start_formatted} --> {end_formatted}", " ".join(chunk_words), ""])
            start_time_ms = end_time_ms + 500
        return "\n".join(srt_content)

    async def _send_text_as_file(self, chat_id: int, text_content: Any, filename: str, caption: str = ""):
        content_to_write = ""
        file_extension = ".txt"
        if isinstance(text_content, dict):
            content_to_write = json.dumps(text_content, indent=2, ensure_ascii=False)
            file_extension = ".json"
        else:
            content_to_write = str(text_content)
        if not filename.endswith(file_extension):
            filename = os.path.splitext(filename)[0] + file_extension
        temp_filepath = None
        try:
            with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=file_extension,
                                             encoding='utf-8') as temp_f:
                temp_f.write(content_to_write)
                temp_filepath = temp_f.name
            with open(temp_filepath, 'rb') as file_to_send:
                await self.bot.send_document(chat_id=chat_id, document=file_to_send, filename=filename, caption=caption)
        except Exception as e:
            logger.error(f"Failed to send text as file: {e}", exc_info=True)
        finally:
            if temp_filepath and os.path.exists(temp_filepath):
                os.remove(temp_filepath)

    async def _perform_retranscribe(self, query, note, target_lang, lang_code):
        chat_id = query.message.chat_id
        s3_key = note.get('s3_object_key')
        if not s3_key:
            await self.send_message(chat_id, "❌ Невозможно перетранскрибировать: исходный файл не найден.")
            return

        status_message = await self.send_message(chat_id,
                                                 f"⏳ Повторная транскрибация с языком: *{self.SUPPORTED_LANGUAGES.get(target_lang, target_lang)}*...")

        temp_filepath = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(s3_key)[-1]) as temp_f:
                temp_filepath = temp_f.name

            self.s3_service.download_file(s3_key, temp_filepath)
            await self.message_handler._process_local_file(temp_filepath, note['user_id'], chat_id, 'retranscribe',
                                                           lang_code, status_message,
                                                           transcription_language=target_lang)

            self.database.delete_note(note['_id'])
            await query.edit_message_text("✅ Задание на повторную транскрибацию отправлено.", reply_markup=None)
        except Exception as e:
            logger.error(f"Failed to re-transcribe {note['_id']}: {e}", exc_info=True)
            if status_message:
                await self.bot.edit_message_text(chat_id, status_message.message_id,
                                                 "❌ Ошибка при повторной транскрибации.")
        finally:
            if temp_filepath and os.path.exists(temp_filepath):
                os.remove(temp_filepath)

    async def _handle_export_action(self, query, note, file_format, lang_code):
        chat_id = query.message.chat_id
        note_id = note['_id']
        status_message = await self.send_message(chat_id,
                                                 f"⏳ {self.localizer.get_string(lang_code, 'export_generating', default='Generating your file...')}")
        transcription = note.get("content", "No transcription available.")
        summary = note.get("summary")
        exporter = self.export_service(transcription_text=transcription, report_text=summary, title=f"Note {note_id}")
        filepath = None
        try:
            if file_format == "md":
                filepath = exporter.to_markdown()
            elif file_format == "docx":
                filepath = exporter.to_docx()
            elif file_format == "pdf":
                filepath = exporter.to_pdf()
            if filepath and os.path.exists(filepath):
                with open(filepath, "rb") as file_to_send:
                    await self.bot.send_document(chat_id, file_to_send,
                                                 caption=f"Your exported {file_format.upper()} file.")
                if status_message: await self.bot.delete_message(chat_id, status_message.message_id)
            else:
                raise FileNotFoundError("Exported file was not created on disk.")
        except Exception as e:
            logger.error(f"Failed to export note {note['_id']} for user {query.from_user.id}: {e}", exc_info=True)
            error_message = f"❌ {self.localizer.get_string(lang_code, 'export_error', default='An error occurred.')}"
            if status_message: await self.bot.edit_message_text(chat_id, status_message.message_id, error_message)
        finally:
            text, markup = self.ui.get_main_actions_menu(lang_code, note_id)
            await query.edit_message_text(text, reply_markup=markup)
            if filepath and os.path.exists(filepath): os.remove(filepath)

    async def _handle_main_action(self, query, note, action, lang_code):
        note_id, chat_id = note['_id'], query.message.chat_id

        def format_response(header_key: str, header_default: str, body: Any) -> str:
            header = self.localizer.get_string(lang_code, header_key, default=header_default)
            body_str = ""
            if isinstance(body, dict):
                body_str = json.dumps(body, indent=2, ensure_ascii=False)
            elif body is None:
                body_str = "Could not generate response."
            else:
                body_str = str(body)
            return f"*{header}:*\n```\n{body_str}\n```"

        if action == 'ACTION_SUMMARIZE':
            await self.bot.send_chat_action(chat_id, 'typing')
            summary = self.insight_service.get_summary(note['content'])
            self.database.update_note(note_id, {"$set": {"summary": summary}})
            response_text = format_response('summary_header', 'Summary', summary)
            await self.send_message(chat_id, response_text)
            await self._send_text_as_file(chat_id, summary, f"summary_{note_id}.txt", "Конспект в виде файла .txt")
        elif action == 'ACTION_REPORT':
            await self.bot.send_chat_action(chat_id, 'typing')
            report = self.insight_service.get_summary(note['content'])
            self.database.update_note(note_id, {"$set": {"smart_report": report}})
            response_text = format_response('report_header', 'Smart Report', report)
            await self.send_message(chat_id, response_text)
            await self._send_text_as_file(chat_id, report, f"report_{note_id}.txt", "Смарт-отчет в виде файла .txt")
        elif action == 'ACTION_BIZANALYSIS':
            await self.bot.send_chat_action(chat_id, 'typing')
            analysis_result = self.business_analyzer.run_comprehensive_analysis(note['content'])
            if analysis_result:
                self.database.update_note(note_id, {"$set": {"business_analysis": analysis_result}})
                response_text = format_response('biz_analysis_header', 'Business Analysis', analysis_result)
                await self.send_message(chat_id, response_text)
                await self._send_text_as_file(chat_id, analysis_result, f"biz_analysis_{note_id}.json",
                                              "Бизнес-анализ в виде файла .json")
            else:
                await self.send_message(chat_id, "❌ Failed to perform business analysis.")
        elif action == 'ACTION_DELETE':
            text, markup = self.ui.get_delete_confirmation(lang_code, note_id)
            await query.edit_message_text(text, reply_markup=markup)
        elif action == 'ACTION_DELETE_CONFIRM':
            if self.database.delete_note(note_id):
                await query.edit_message_text("🗑️ Note successfully deleted.", reply_markup=None)
        elif action == 'ACTION_DELETE_CANCEL':
            text, markup = self.ui.get_main_actions_menu(lang_code, note_id)
            await query.edit_message_text(text, reply_markup=markup)
        elif action == 'ACTION_SUBTITLES':
            await self.bot.send_chat_action(chat_id, 'typing')
            transcription = note.get('content')
            if not transcription:
                await self.send_message(chat_id, "This note has no text to generate subtitles from.")
                return
            status_msg = await self.send_message(chat_id, "🤖 Generating subtitles from transcription...")
            srt_content = self._generate_srt_from_text(transcription)
            temp_filepath = None
            try:
                with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=".srt", encoding='utf-8') as temp_f:
                    temp_f.write(srt_content)
                    temp_filepath = temp_f.name
                with open(temp_filepath, 'rb') as srt_file:
                    await self.bot.send_document(chat_id=chat_id, document=srt_file, filename=f"{note_id}.srt",
                                                 caption="✅ Ваш SRT файл с субтитрами.")
                if status_msg: await self.bot.delete_message(chat_id, status_msg.message_id)
            finally:
                if temp_filepath and os.path.exists(temp_filepath):
                    os.remove(temp_filepath)
