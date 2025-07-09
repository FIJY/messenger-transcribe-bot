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
from datetime import datetime, timezone
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
        self.downloader_service = DownloaderService()  # Добавляем новый сервис
        self.celery_app_client = get_celery_app_client()
        self.payment_service = payment_service
        self.admin_telegram_id = os.getenv('ADMIN_TELEGRAM_ID')
        self.ui = TelegramUI()
        self.insight_service = insight_service
        self.translation_service = translation_service

    async def set_bot_commands(self):
        # ... (код без изменений)
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

        # Сначала проверяем на команды
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

        # Определяем, что прислал пользователь
        file_to_process = update.message.document or update.message.audio or update.message.video or update.message.voice
        url_match = re.search(r'https?://\S+', update.message.text or "")

        if file_to_process:
            await self._handle_file_upload(file_to_process, user_id, chat_id)
        elif url_match:
            await self._handle_url(url_match.group(0), user_id, chat_id)
        elif update.message.text:
            await self._handle_text_note(update.message.text, user_id, chat_id)

    # НОВЫЙ МЕТОД для обработки ссылок
    async def _handle_url(self, url: str, user_id: str, chat_id: int):
        await self.send_message(chat_id, "🔗 Link received. Starting download, this may take a while...")

        local_file_path = None
        try:
            local_file_path = self.downloader_service.download_audio(url)
            if not local_file_path:
                await self.send_message(chat_id,
                                        "❌ Failed to download audio from the link. The link might be broken or private.")
                return

            # Теперь у нас есть локальный файл, используем общую логику обработки
            await self._process_local_file(local_file_path, user_id, chat_id, from_url=True)

        except Exception as e:
            logger.error(f"Error handling URL {url}: {e}", exc_info=True)
            await self.send_message(chat_id, "❌ An error occurred while processing your link.")
        finally:
            # Важно: удаляем временный файл после обработки
            if local_file_path and os.path.exists(local_file_path):
                os.remove(local_file_path)

    # ОБЩИЙ МЕТОД для обработки файла, который уже есть на диске
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
                # Если файл был из ссылки, даем пользователю знать, что все ок
                if from_url:
                    await self.send_message(chat_id, "✅ Download complete. Your file is now being processed...")

        except Exception as e:
            logger.error(f"Error in _process_local_file: {e}", exc_info=True)
            await self.send_message(chat_id, "❌ An error occurred during file processing.")

    # Переименованный и упрощенный метод для загрузки из Telegram
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

    async def _handle_callback_query(self, query: Update.callback_query):
        await query.answer()
        payload = query.data
        chat_id = query.message.chat_id
        user_id = str(query.from_user.id)

        # ... (код для SHOW_PAYMENT_QR без изменений)
        if payload == 'SHOW_PAYMENT_QR':
            qr_file_id = self.payment_service.payment_qr_file_id
            if qr_file_id:
                try:
                    await self.bot.send_photo(chat_id, photo=qr_file_id,
                                              caption="Please use this QR code for your payment.")
                except Exception as e:
                    logger.error(f"Failed to send QR code photo: {e}")
                    await self.send_message(chat_id, "Sorry, could not display the QR code at the moment.")
            else:
                await self.send_message(chat_id, "Sorry, the payment QR code is not configured.")
            return

        parts = payload.split('_')
        action_type = parts[0]

        # ИЗМЕНЕННАЯ ЛОГИКА: После подтверждения транскрипции предлагаем шаблоны
        if action_type == 'CONFIRM' and parts[1] == 'OK':
            s3_key = "_".join(parts[2:])
            message, reply_markup = self.ui.get_template_selection_message(s3_key)
            await query.edit_message_text(message, reply_markup=reply_markup)
            return

        # НОВАЯ ЛОГИКА для обработки шаблонов
        if action_type == 'TEMPLATE':
            template_key = parts[1]
            s3_key = "_".join(parts[2:])

            raw_transcription = self.database.get_raw_transcription(s3_key)
            if not raw_transcription or not raw_transcription.get('transcription'):
                await query.edit_message_text("❌ Error: Could not find the original transcription.")
                return

            text_content = raw_transcription.get('transcription')

            # Если пользователь выбрал "просто сохранить текст"
            if template_key == 'SKIP':
                await query.edit_message_text("✅ OK, saving transcription as a plain text note...")
                note_id = self.database.save_note(
                    user_id=user_id,
                    content=text_content,
                    s3_object_key=s3_key,
                    detected_language=raw_transcription.get('detected_language'),
                    duration_minutes=raw_transcription.get('duration_minutes', 0),
                    tags=['plain_text']
                )
                message, reply_markup = self.ui.get_note_actions_message(note_id)
                await self.send_message(chat_id, "📝 *Note Saved*\n\n" + message, reply_markup=reply_markup)
                return

            await query.edit_message_text(
                f"🤖 Generating your report with template '{template_key}'. This might take a minute...")

            report_text = self.insight_service.create_report(text_content, template_key)

            if not report_text:
                await query.edit_message_text(
                    "❌ Sorry, failed to generate the report. The note has been saved as plain text.")
                self.database.save_note(user_id=user_id, content=text_content, s3_object_key=s3_key)
                return

            # Сохраняем и текст отчета, и исходную транскрипцию
            report_name = self.insight_service.REPORT_PROMPTS.get(template_key, {}).get('name', 'Report')
            final_content = f"# {report_name}\n\n{report_text}\n\n---\n\n## Original Transcription\n\n{text_content}"
            note_id = self.database.save_note(
                user_id=user_id,
                content=final_content,
                s3_object_key=s3_key,
                detected_language=raw_transcription.get('detected_language'),
                duration_minutes=raw_transcription.get('duration_minutes', 0),
                tags=[template_key.lower()]
            )

            await query.edit_message_text("✅ Your report has been generated and saved!")
            message, reply_markup = self.ui.get_note_actions_message(note_id)
            await self.send_message(chat_id, f"📊 *Report Saved*\n\n{message}", reply_markup=reply_markup)
            return

        # ... (остальные обработчики без изменений, но они теперь менее актуальны)

    # ... (все остальные методы, включая send_message, остаются без изменений)
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