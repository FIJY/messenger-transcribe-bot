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
from telegram.error import BadRequest

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

logger = logging.getLogger(__name__)


class TelegramHandler:
    # --- ДОБАВЛЕН СЛОВАРЬ ЯЗЫКОВ ---
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

    async def _send_text_as_file(self, chat_id: int, text_content: str, filename: str, caption: str = ""):
        temp_filepath = None
        try:
            with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=".txt", encoding='utf-8') as temp_f:
                temp_f.write(text_content)
                temp_filepath = temp_f.name
            with open(temp_filepath, 'rb') as file_to_send:
                await self.bot.send_document(chat_id=chat_id, document=file_to_send, filename=filename, caption=caption)
        except Exception as e:
            logger.error(f"Failed to send text as file: {e}", exc_info=True)
        finally:
            if temp_filepath and os.path.exists(temp_filepath):
                os.remove(temp_filepath)

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
        effective_user = None
        effective_chat = None
        if update.callback_query:
            effective_user = update.callback_query.from_user
            effective_chat = update.callback_query.message.chat
        elif update.message:
            effective_user = update.message.from_user
            effective_chat = update.message.chat
        if not effective_user or not effective_chat: return
        user_id = str(effective_user.id)
        chat_id = effective_chat.id
        username = effective_user.username
        lang_code = effective_user.language_code or 'en'
        user = self.database.get_user(user_id)
        if not user:
            user = self.database.create_user(user_id, username=username, language_code=lang_code)
        elif user.get('language_code') != lang_code:
            self.database.update_user(user_id, {'language_code': lang_code})
            user['language_code'] = lang_code
        user_lang = user.get('language_code', 'en')
        if update.callback_query:
            await self._handle_callback_query(update.callback_query, user_lang)
            return
        if update.message and update.message.text and update.message.text.startswith('/'):
            await self._handle_command(user_id, chat_id, username, update.message.text, user_lang)
            return
        user_state = user.get('state')
        if update.message and update.message.text and isinstance(user_state, dict) and user_state.get(
                'mode') == 'chatting':
            await self._handle_chat_message(user_id, chat_id, update.message.text, user_state, user_lang)
            return
        if update.message and update.message.photo and isinstance(user_state, dict) and user_state.get(
                'mode') == 'awaiting_payment_proof':
            await self.payment_service.handle_payment_proof(update.message)
            return
        if update.message:
            file_to_process = update.message.document or update.message.audio or update.message.video or update.message.voice or update.message.video_note
            url_match = re.search(r'https?://\S+', update.message.text or "")
            if file_to_process:
                await self._handle_file_upload(file_to_process, user_id, chat_id, user_lang)
            elif url_match:
                await self._handle_url(url_match.group(0), user_id, chat_id, user_lang)
            elif update.message.text:
                await self._handle_text_note(update.message.text, user_id, chat_id, user_lang)

    async def _handle_command(self, user_id: str, chat_id: int, username: Optional[str], text: str, lang_code: str):
        command_parts = text.split()
        command = command_parts[0]
        if command == '/start':
            await self._handle_start_command(user_id, chat_id, username, lang_code)
        elif command == '/status':
            await self._handle_status_command(user_id, chat_id)
        elif command == '/help':
            bot_user = await self.bot.get_me()
            add_to_group_url = f"https://t.me/{bot_user.username}?startgroup=true"
            await self.send_message(chat_id, self.ui.get_help_message(lang_code, add_to_group_url))
        elif command == '/cancel':
            self.database.update_user(user_id, {'state': None})
            await self.send_message(chat_id, self.localizer.get_string(lang_code, 'chat_mode_exited'))
        elif command == '/search':
            query = " ".join(command_parts[1:])
            if not query: await self.send_message(chat_id, "Usage: `/search <your query>`"); return
            await self.send_message(chat_id, f"🔍 Searching for notes matching: `{query}`...")
            notes = self.database.search_notes_by_query(user_id, query)
            response_text = self.ui.format_search_results(lang_code, notes, query)
            await self.send_message(chat_id, response_text)
        elif command == '/grant':
            if user_id != self.admin_telegram_id: await self.send_message(chat_id,
                                                                          "❌ You are not authorized to use this command."); return
            try:
                target_user_id, days = command_parts[1], int(command_parts[2])
                if self.database.grant_premium_subscription(target_user_id, days):
                    await self.send_message(chat_id, f"✅ Premium granted to user `{target_user_id}` for {days} days.")
                    try:
                        await self.send_message(int(target_user_id),
                                                f"🎉 Your premium has been extended by {days} days!")
                    except Exception as e:
                        logger.warning(f"Could not notify user {target_user_id}: {e}")
                else:
                    await self.send_message(chat_id, f"❌ Could not find user with ID `{target_user_id}`.")
            except (IndexError, ValueError):
                await self.send_message(chat_id, "Usage: `/grant <user_id> <days>`")

    async def _handle_chat_message(self, user_id: str, chat_id: int, question: str, state: dict, lang_code: str):
        if not question: await self.send_message(chat_id, "Please send a text question."); return
        note_id_str = state.get('note_id')
        if not note_id_str:
            self.database.update_user(user_id, {'state': None})
            await self.send_message(chat_id, self.localizer.get_string(lang_code, 'error_chat_context_lost'));
            return
        try:
            note = self.database.get_note_by_id(ObjectId(note_id_str))
            if not note:
                self.database.update_user(user_id, {'state': None})
                await self.send_message(chat_id, self.localizer.get_string(lang_code, 'error_note_deleted'));
                return
            await self.bot.send_chat_action(chat_id, 'typing')
            answer = self.insight_service.get_answer_from_text(note.get('content', ''), question)
            await self.send_message(chat_id, answer)
        except Exception as e:
            logger.error(f"Error during chat handling: {e}", exc_info=True)
            await self.send_message(chat_id, self.localizer.get_string(lang_code, 'error_generic'))
            self.database.update_user(user_id, {'state': None})

    async def _handle_text_note(self, text: str, user_id: str, chat_id: int, lang_code: str):
        try:
            note_id = self.database.save_note(user_id=user_id, content=text, tags=['plain_text'], source_type='text')
            await self.send_message(chat_id, f"✅ *Note saved:* ```{text[:250]}...```")
            message, reply_markup = self.ui.get_main_actions_menu(lang_code, note_id)
            await self.send_message(chat_id, message, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error creating text note for user {user_id}: {e}")
            await self.send_message(chat_id, "❌ Sorry, an error occurred while saving your note.")

    async def _handle_url(self, url: str, user_id: str, chat_id: int, lang_code: str):
        status_message = await self.send_message(chat_id, self.localizer.get_string(lang_code, 'task_accepted'))
        if not status_message: return
        if self.celery_app_client:
            platform_payload = {'platform': 'telegram', 'chat_id': chat_id, 'lang_code': lang_code,
                                'message_id': status_message.message_id}
            self.celery_app_client.send_task('tasks.process_url', args=[user_id, url, {}, platform_payload])
        else:
            await self.edit_message(chat_id, status_message.message_id,
                                    "❌ Server error: cannot queue URL for processing.")

    async def _process_local_file(self, local_file_path: str, user_id: str, chat_id: int, source_type: str,
                                  lang_code: str, status_message: Message,
                                  transcription_language: Optional[str] = None):
        try:
            object_key = f"{uuid.uuid4()}{os.path.splitext(local_file_path)[-1]}"
            if not self.s3_service.upload_file(local_file_path, object_key):
                await self.edit_message(chat_id, status_message.message_id,
                                        "❌ Server error: could not upload file to storage.");
                return
            if self.celery_app_client:
                logger.info(f"Sending task to Celery for object {object_key}")
                task_kwargs = {'language': transcription_language} if transcription_language else {}
                platform_payload = {'platform': 'telegram', 'chat_id': chat_id, 'source_type': source_type,
                                    'lang_code': lang_code, 'message_id': status_message.message_id}
                self.celery_app_client.send_task('tasks.process_media',
                                                 args=[user_id, object_key, {}, platform_payload], kwargs=task_kwargs)
                await self.edit_message(chat_id, status_message.message_id,
                                        self.localizer.get_string(lang_code, 'upload_complete'))
        except Exception as e:
            logger.error(f"Error in _process_local_file: {e}", exc_info=True)
            await self.edit_message(chat_id, status_message.message_id, "❌ An error occurred during file processing.")
        finally:
            if local_file_path and os.path.exists(local_file_path): os.remove(local_file_path)

    async def _handle_file_upload(self, file_obj: Message, user_id: str, chat_id: int, lang_code: str):
        status_message = await self.send_message(chat_id, self.localizer.get_string(lang_code, 'file_received'))
        if not status_message: return
        local_file_path = None
        try:
            tg_file = await file_obj.get_file()
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(tg_file.file_path)[-1]) as temp_f:
                local_file_path = temp_f.name
                await tg_file.download_to_drive(custom_path=local_file_path)
            await self._process_local_file(local_file_path, user_id, chat_id, 'upload', lang_code, status_message)
        except Exception as e:
            logger.error(f"Error during file download from Telegram: {e}", exc_info=True)
            await self.edit_message(chat_id, status_message.message_id, "❌ Failed to download file from Telegram.")

    async def _handle_start_command(self, user_id: str, chat_id: int, username: Optional[str], lang_code: str):
        user = self.database.get_user(user_id)
        if not user: user = self.database.create_user(user_id, username=username, language_code=lang_code)
        await self.send_message(chat_id, self.ui.get_welcome_message(lang_code))
        return user

    async def _handle_status_command(self, user_id: str, chat_id: int):
        user = self.database.get_user(user_id)
        if not user: await self.send_message(chat_id, "Please use /start first."); return
        message = self.ui.get_status_message(user)
        await self.send_message(chat_id, message)

    async def _handle_callback_query(self, query: Update.callback_query, lang_code: str):
        await query.answer()
        payload = query.data
        user_id = str(query.from_user.id)
        parts = payload.split('_')

        # --- НОВАЯ ЛОГИКА МАРШРУТИЗАЦИИ ---
        if parts[0] == 'SHOW' and parts[1] == 'LANG' and parts[2] == 'MENU':
            try:
                action_prefix = parts[3]
                page = int(parts[4])
                note_id = ObjectId(parts[5])
                text, markup = self.ui.get_language_selection_menu(lang_code, note_id, action_prefix,
                                                                   self.SUPPORTED_LANGUAGES, page=page)
                await query.edit_message_text(text, reply_markup=markup)
            except (IndexError, ValueError, bson_errors.InvalidId) as e:
                logger.error(f"Error parsing language menu callback: {payload}, error: {e}")
            return

        action = '_'.join(parts[:-1])
        note_id_str = parts[-1]

        try:
            note_id = ObjectId(note_id_str)
        except (IndexError, bson_errors.InvalidId):
            logger.warning(f"Could not parse note_id from callback data: {payload}");
            return

        note = self.database.get_note_by_id(note_id)
        if not note:
            await query.edit_message_text("This menu is no longer active.", reply_markup=None);
            return

        if parts[0] == 'TRANSLATE':
            target_lang = parts[1]
            await self._perform_translation(query, note, target_lang, lang_code)
            return

        if parts[0] == 'RETRANSCRIBE':
            target_lang = parts[1]
            await self._perform_retranscribe(query, note, target_lang, lang_code)
            return

        if action == 'ACTION_EXPORT':
            text, markup = self.ui.get_export_menu(lang_code, note_id)
            await query.edit_message_text(text, reply_markup=markup)
            return
        if action == 'ACTION_BACK_TO_MAIN':
            text, markup = self.ui.get_main_actions_menu(lang_code, note_id)
            await query.edit_message_text(text, reply_markup=markup)
            return
        if action.startswith('EXPORT'):
            file_format = action.split('_')[1].lower()
            await self._handle_export_action(query, note, file_format, lang_code)
            return
        if action == 'ACTION_CHAT':
            new_state = {'mode': 'chatting', 'note_id': str(note_id)}
            self.database.update_user(user_id, {'state': new_state})
            await self.send_message(query.message.chat_id, self.localizer.get_string(lang_code, 'chat_mode_entered'))
            return
        await self._handle_main_action(query, note, action, parts, lang_code)

    async def _perform_translation(self, query: Update.callback_query, note: dict, target_lang: str, lang_code: str):
        note_id = note['_id']
        chat_id = query.message.chat_id
        await self.bot.send_chat_action(chat_id, 'typing')
        translated_text = self.translation_service.translate_text(note['content'], target_language=target_lang)
        header = self.SUPPORTED_LANGUAGES.get(target_lang, target_lang)
        response_text = f"*{header}:*\n```\n{translated_text or 'Could not translate.'}\n```"
        await self.send_message(chat_id, response_text)
        await self._send_text_as_file(chat_id, translated_text, f"translation_{target_lang}_{note_id}.txt",
                                      f"Перевод на {header}")
        text, markup = self.ui.get_main_actions_menu(lang_code, note_id)
        await query.edit_message_text(text, reply_markup=markup)

    async def _perform_retranscribe(self, query: Update.callback_query, note: dict, target_lang: str, lang_code: str):
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

            await self._process_local_file(temp_filepath, note['user_id'], chat_id, 'retranscribe', lang_code,
                                           status_message, transcription_language=target_lang)

            self.database.delete_note(note['_id'])
            await query.edit_message_text("✅ Задание на повторную транскрибацию отправлено.", reply_markup=None)

        except Exception as e:
            logger.error(f"Failed to re-transcribe {note['_id']}: {e}", exc_info=True)
            await self.edit_message(chat_id, status_message.message_id, "❌ Ошибка при повторной транскрибации.")
        finally:
            if temp_filepath and os.path.exists(temp_filepath):
                os.remove(temp_filepath)

    async def _handle_export_action(self, query: Update.callback_query, note: dict, file_format: str, lang_code: str):
        chat_id = query.message.chat_id
        note_id = note['_id']
        status_message = await self.send_message(chat_id,
                                                 f"⏳ {self.localizer.get_string(lang_code, 'export_generating', default='Generating your file...')}")
        transcription = note.get("content", "No transcription available.")
        summary = note.get("summary")
        exporter = ExportService(transcription_text=transcription, report_text=summary, title=f"Note {note_id}")
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
                if status_message: await self.delete_message(chat_id, status_message.message_id)
            else:
                raise FileNotFoundError("Exported file was not created on disk.")
        except Exception as e:
            logger.error(f"Failed to export note {note_id} for user {query.from_user.id}: {e}", exc_info=True)
            error_message = f"❌ {self.localizer.get_string(lang_code, 'export_error', default='An error occurred.')}"
            if status_message: await self.edit_message(chat_id, status_message.message_id, error_message)
        finally:
            text, markup = self.ui.get_main_actions_menu(lang_code, note_id)
            await query.edit_message_text(text, reply_markup=markup)
            if filepath and os.path.exists(filepath): os.remove(filepath)

    async def _handle_main_action(self, query: Update.callback_query, note: dict, action: str, parts: List[str],
                                  lang_code: str):
        note_id, chat_id = note['_id'], query.message.chat_id

        def format_response(header_key: str, header_default: str, body: Optional[str]) -> str:
            header = self.localizer.get_string(lang_code, header_key, default=header_default)
            if not body: body = "Could not generate response."
            return f"*{header}:*\n```\n{body}\n```"

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
                await self._send_text_as_file(chat_id, analysis_result, f"biz_analysis_{note_id}.txt",
                                              "Бизнес-анализ в виде файла .txt")
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
            if not transcription: await self.send_message(chat_id,
                                                          "This note has no text to generate subtitles from."); return
            status_msg = await self.send_message(chat_id, "🤖 Generating subtitles from transcription...")
            srt_content = self._generate_srt_from_text(transcription)
            temp_filepath = None
            try:
                with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=".srt", encoding='utf-8') as temp_f:
                    temp_f.write(srt_content);
                    temp_filepath = temp_f.name
                with open(temp_filepath, 'rb') as srt_file:
                    await self.bot.send_document(chat_id=chat_id, document=srt_file, filename=f"{note_id}.srt",
                                                 caption="✅ Ваш SRT файл с субтитрами.")
                if status_msg: await self.delete_message(chat_id, status_msg.message_id)
            finally:
                if temp_filepath and os.path.exists(temp_filepath): os.remove(temp_filepath)

    async def send_message(self, chat_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None) -> \
    Optional[Message]:
        try:
            return await self.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN,
                                               reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to send message to Telegram chat {chat_id}: {e}")
            try:
                return await self.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
            except Exception as final_e:
                logger.error(f"Failed to send message even without parse_mode: {final_e}")
            return None

    async def edit_message(self, chat_id: int, message_id: int, text: str,
                           reply_markup: Optional[InlineKeyboardMarkup] = None):
        try:
            await self.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text,
                                             parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        except BadRequest as e:
            if "Message is not modified" not in str(e): logger.error(
                f"Failed to edit message {message_id} in chat {chat_id}: {e}")
        except Exception as e:
            logger.error(f"Failed to edit message {message_id} in chat {chat_id}: {e}")

    async def delete_message(self, chat_id: int, message_id: int):
        try:
            await self.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.error(f"Failed to delete message {message_id} in chat {chat_id}: {e}")
