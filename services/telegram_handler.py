# services/telegram_handler.py
import os
import logging
import tempfile
import httpx
import uuid
import asyncio
from typing import Dict, Any, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot, Message
from datetime import datetime, timezone

from .database import Database
from .s3_service import S3Service
from .celery_client import get_celery_app_client
from .translation_service import TranslationService
from .payment_service import PaymentService
from config.transcrib_suggestion_config import (
    DEFAULT_POPULAR_TRANSCRIPTION_LANGS,
    DEFAULT_POPULAR_TRANSLATION_LANGS,
    SUPPORTED_LANGUAGES_MAP
)

logger = logging.getLogger(__name__)


class TelegramHandler:
    def __init__(self, token: str, database: Database, s3_service: S3Service,
                 translation_service: TranslationService, payment_service: PaymentService):
        if not token: raise ValueError("Telegram token is required.")
        self.token = token
        self.bot = Bot(token=self.token)
        self.database = database
        self.s3_service = s3_service
        self.translation_service = translation_service
        self.celery_app_client = get_celery_app_client()
        self.payment_service = payment_service
        self.admin_telegram_id = os.getenv('ADMIN_TELEGRAM_ID')
        self.payment_qr_file_id = os.getenv('PAYMENT_QR_CODE_FILE_ID')
        self.support_contact = os.getenv('SUPPORT_CONTACT')

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
            command_parts = update.message.text.split()
            command = command_parts[0]

            if command == '/start':
                await self._handle_start_command(user_id, chat_id, username)
                return
            if command == '/status':
                await self._handle_status_command(user_id, chat_id)
                return
            if command == '/help':
                await self._handle_help_command(chat_id)
                return

            if user_id == self.admin_telegram_id:
                if command == '/confirm':
                    await self._handle_confirm_command(command_parts, chat_id)
                    return
                if command == '/check':
                    await self._handle_check_command(command_parts, chat_id)
                    return

        user = self.database.get_user(user_id)
        if not user:
            user = await self._handle_start_command(user_id, chat_id, username)

        if update.message.photo:
            if user.get('state') == 'awaiting_payment_proof':
                await self._handle_payment_proof(update.message)
                return

        if update.message.text:
            state = user.get('state')
            if state == 'awaiting_language_input_transcription':
                await self._handle_language_text_input(user_id, user, update.message.text, 'transcription')
            elif state == 'awaiting_language_input_translation':
                await self._handle_language_text_input(user_id, user, update.message.text, 'translation')
            else:
                await self.send_message(chat_id, "ℹ️ To get started, please send me an audio or video file.")
            return

        file_to_process = update.message.document or update.message.audio or update.message.video or update.message.voice
        if file_to_process:
            await self._handle_file(file_to_process, user_id, chat_id)

    async def _handle_start_command(self, user_id: str, chat_id: int, username: Optional[str]):
        user = self.database.get_user(user_id)
        if not user:
            user = self.database.create_user(user_id, username=username)

        welcome_message = (
            "🎉 *Welcome to the Transcription Bot!*\n\n"
            "To get started, just send me an audio or video file.\n\n"
            "Type /help to see all available commands and features."
        )
        await self.send_message(chat_id, welcome_message)
        return user

    async def _handle_help_command(self, chat_id: int):
        """Отправляет пользователю справочное сообщение."""
        # ===> ИЗМЕНЕНИЕ: Добавлена информация о сроке действия <===
        help_text = (
            "🤖 *Bot Help & Information*\n\n"
            "**How to Use Me:**\n"
            "Simply send me an audio or video file (as a file or a voice message), and I will transcribe it into text for you.\n\n"
            "**Available Commands:**\n"
            "`/start` - Start or restart the bot.\n"
            "`/status` - Check your current plan, remaining minutes, and subscription status.\n"
            "`/help` - Show this help message.\n\n"
            "**Our Monthly Plans:**\n"
            "🔹 **Basic ($2/month):** A package of 100 minutes for high-quality transcription.\n"
            "💎 **Premium ($5/month):** An extended package of 200 minutes with access to all features, including text translation.\n\n"
            "_All paid plans are valid for 30 days from the date of activation._\n\n"
        )
        if self.support_contact:
            help_text += f"If you have any questions, please contact our support: {self.support_contact}"

        await self.send_message(chat_id, help_text)

    async def _handle_status_command(self, user_id: str, chat_id: int):
        user = self.database.get_user(user_id)
        if not user:
            await self.send_message(chat_id, "Please use /start first.")
            return

        plan = user.get('plan', 'free').capitalize()
        minutes_used = user.get('minutes_used', 0)
        minutes_limit = user.get('minutes_limit', 0)

        if plan == 'Free':
            minutes_left = minutes_limit - minutes_used
            message = (f"📊 *Your Status*\n\n"
                       f"Plan: {plan}\n"
                       f"Minutes left: {minutes_left:.1f} / {minutes_limit} minutes")
        else:
            expires_at = user.get('subscription_expires_at')
            expires_str = expires_at.strftime('%d %B %Y') if expires_at else 'N/A'
            message = (f"📊 *Your Status*\n\n"
                       f"Plan: {plan} 💎\n"
                       f"Subscription valid until: {expires_str}\n"
                       f"Minutes used this period: {minutes_used:.1f} / {minutes_limit} minutes")
        await self.send_message(chat_id, message)

    async def _handle_confirm_command(self, command_parts: List[str], chat_id: int):
        if len(command_parts) != 3:
            await self.send_message(chat_id,
                                    "❌ Incorrect format. Use: `/confirm <user_id> <plan_name>` (e.g., basic or premium)")
            return

        user_to_activate, plan_name = command_parts[1], command_parts[2].lower()

        if plan_name not in ['basic', 'premium']:
            await self.send_message(chat_id, f"❌ Unknown plan '{plan_name}'. Use 'basic' or 'premium'.")
            return

        target_user = self.database.get_user(user_to_activate)
        if not target_user:
            await self.send_message(chat_id, f"❌ User with ID `{user_to_activate}` not found.")
            return

        if target_user.get('plan') == plan_name:
            expires_at = target_user.get('subscription_expires_at')
            if expires_at and expires_at > datetime.now(timezone.utc):
                await self.send_message(chat_id, f"⚠️ **Warning:** User `{user_to_activate}` is already on the `{plan_name}` plan. No action was taken to prevent duplicate activation.")
                return

        self.database.update_user_subscription(user_to_activate, plan_name)

        confirmation_message_admin = f"✅ User `{user_to_activate}` has been successfully upgraded to the *{plan_name.capitalize()}* plan."
        await self.send_message(chat_id, confirmation_message_admin)

        try:
            confirmation_message_user = f"🎉 Your *{plan_name.capitalize()}* plan is now active! Thank you for your subscription."
            await self.send_message(int(user_to_activate), confirmation_message_user)
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

        plan = user_data.get('plan', 'free').capitalize()
        minutes_used = user_data.get('minutes_used', 0)
        minutes_limit = user_data.get('minutes_limit', 0)
        expires_at = user_data.get('subscription_expires_at')
        expires_str = expires_at.strftime('%d %B %Y') if expires_at else 'N/A'

        message = (
            f"ℹ️ *Status for user `{user_to_check}`*\n\n"
            f"Plan: {plan}\n"
            f"Usage: {minutes_used:.1f} / {minutes_limit} min\n"
            f"Expires: {expires_str}"
        )
        await self.send_message(chat_id, message)

    async def _handle_callback_query(self, query: Update.callback_query):
        await query.answer()
        payload = query.data
        user_id = str(query.from_user.id)
        chat_id = query.message.chat_id
        user = self.database.get_user(user_id)
        if not user: return

        if payload.startswith('RETRY_AS_'):
            lang_code = payload.replace('RETRY_AS_', '').lower()
            await self._handle_retry_request(user_id, chat_id, lang_code)
        elif payload.startswith('TRANSLATE_'):
            if user.get('plan') != 'premium':
                await self.send_message(chat_id, "Translation is a Premium feature. Please upgrade to use it.")
                return
            target_lang_code = payload.replace('TRANSLATE_', '').lower()
            await self._handle_translation_request(user_id, chat_id, target_lang_code)
        elif payload == 'CHOOSE_OTHER_LANGUAGE':
            await self.send_language_correction_options(chat_id, user)
        elif payload == 'CONFIRM_TRANSCRIPTION_OK':
            if user.get('plan') == 'premium':
                await self.send_translation_options(chat_id, user)
            else:
                await query.edit_message_text(text="✅ Done! Send another file to continue.")
        elif payload == 'SHOW_PAYMENT_QR':
            if self.payment_qr_file_id:
                await self.bot.send_photo(chat_id, photo=self.payment_qr_file_id,
                                          caption="Scan this QR code in your ABA app.")
            else:
                await self.send_message(chat_id, "Sorry, the QR code is temporarily unavailable.")
        elif payload == 'INPUT_OTHER_TRANSCRIPTION_LANG':
            self.database.update_user(user_id, {'state': 'awaiting_language_input_transcription'})
            await self.send_message(chat_id, "Please type the source language name or its 2-letter code.")
        elif payload == 'INPUT_OTHER_TRANSLATION_LANG':
            self.database.update_user(user_id, {'state': 'awaiting_language_input_translation'})
            await self.send_message(chat_id, "Please type the target language for translation.")

    async def _handle_payment_proof(self, message: Message):
        """Обрабатывает полученный скриншот об оплате."""
        user = message.from_user
        user_id = str(user.id)
        chat_id = message.chat_id
        admin_id = self.admin_telegram_id

        if not admin_id:
            logger.warning("Admin ID not set, cannot forward payment proof.")
            await self.send_message(chat_id, "Thank you! Your proof is in the queue and will be reviewed shortly.")
            return

        try:
            await self.send_message(chat_id,
                                    "🙏 Thank you! Your payment proof has been received and sent for verification. Your plan will be activated shortly.")

            user_mention = f"@{user.username}" if user.username else f"ID: `{user_id}`"
            admin_caption = (
                f"🔔 *Payment Proof Received*\n\n"
                f"From User: {user_mention}\n"
                f"Please verify and activate their plan using `/confirm {user_id} <plan_name>`."
            )

            await message.forward(chat_id=admin_id)
            await self.bot.send_message(chat_id=admin_id, text=admin_caption, parse_mode='Markdown')
            self.database.update_user(user_id, {'state': None})

        except Exception as e:
            logger.error(f"Failed to process payment proof for user {user_id}: {e}", exc_info=True)

    def _build_smart_buttons(self, user: Dict[str, Any], context: str) -> List[List[InlineKeyboardButton]]:
        if context == 'transcription':
            defaults, stats, prefix, other_payload = DEFAULT_POPULAR_TRANSCRIPTION_LANGS, user.get(
                'transcription_lang_usage', {}), "RETRY_AS_", "INPUT_OTHER_TRANSCRIPTION_LANG"
        else:
            defaults, stats, prefix, other_payload = DEFAULT_POPULAR_TRANSLATION_LANGS, user.get(
                'translation_lang_usage', {}), "TRANSLATE_", "INPUT_OTHER_TRANSLATION_LANG"
        sorted_user_langs = sorted(stats.keys(), key=stats.get, reverse=True)
        buttons, added_codes = [], set()

        def add_button(lang_code):
            title_info = next((lang for lang in defaults if lang['code'] == lang_code), None)
            if title_info:
                flag = title_info.get('flag', '')
                title_text = title_info.get('title', lang_code.upper())
                title = f"{flag} {title_text}".strip()
            else:
                title = lang_code.upper()

            buttons.append(InlineKeyboardButton(title, callback_data=f"{prefix}{lang_code}"))
            added_codes.add(lang_code)

        for lang_code in sorted_user_langs[:3]: add_button(lang_code)
        for lang in defaults:
            if len(buttons) >= 5: break
            if lang['code'] not in added_codes: add_button(lang['code'])
        return [buttons, [InlineKeyboardButton("✍️ Type other...", callback_data=other_payload)]]

    async def send_language_correction_options(self, chat_id: int, user: Dict[str, Any]):
        reply_markup = InlineKeyboardMarkup(self._build_smart_buttons(user, 'transcription'))
        await self.send_message(chat_id, "Got it. What was the language, actually?", reply_markup)

    async def send_translation_options(self, chat_id: int, user: Dict[str, Any]):
        reply_markup = InlineKeyboardMarkup(self._build_smart_buttons(user, 'translation'))
        await self.send_message(chat_id, "What language would you like to translate to?", reply_markup)

    async def send_limit_exceeded_message(self, chat_id: int, user_id: str):
        # ===> ИЗМЕНЕНИЕ: Добавлена информация о сроке действия <===
        payment_link = "https://pay.ababank.com/qLuyZbAyLDpyq9VSA"
        message = (
            f"⏳ *You have used all your available minutes.*\n\n"
            f"To continue, please choose a monthly package:\n\n"
            f"🔹 **Basic: $2/month**\n"
            f"• 100 minutes of transcription\n"
            f"• Files up to 20 minutes\n\n"
            f"💎 **Premium: $5/month**\n"
            f"• 200 minutes for all features\n"
            f"• Files up to 60 minutes\n\n"
            f"💳 **Payment Options:**\n\n"
            f"**1. ABA Bank Transfer**\n"
            f"   Account Name: `SHMYKOVA OLGA`\n"
            f"   Account Number: `000 686 883`\n\n"
            f"**2. ABA Pay Link**\n"
            f"   [Tap here to pay with ABA Pay]({payment_link})\n\n"
            f"❗️**Important:** After payment, please **send a screenshot of the receipt** to this chat for verification."
        )
        keyboard = [[InlineKeyboardButton("📱 Show QR Code for Payment", callback_data="SHOW_PAYMENT_QR")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await self.send_message(chat_id, message, reply_markup)
        self.database.update_user(user_id, {'state': 'awaiting_payment_proof'})

    async def _handle_language_text_input(self, user_id: str, user: Dict[str, Any], text: str, context: str):
        lang_code = SUPPORTED_LANGUAGES_MAP.get(text.lower().strip())
        chat_id = int(user_id)
        if lang_code:
            self.database.update_user(user_id, {'state': None})
            if context == 'translation' and user.get('plan') != 'premium':
                await self.send_message(chat_id, "Translation is a Premium feature.")
                return
            self.database.increment_language_usage(user_id, lang_code, context)
            handler = self._handle_retry_request if context == 'transcription' else self._handle_translation_request
            await handler(user_id, chat_id, lang_code)
        else:
            await self.send_message(chat_id, f"Sorry, I don't recognize '{text}'. Please try again.")

    async def _handle_retry_request(self, user_id: str, chat_id: int, lang_code: str):
        last_doc = self.database.get_last_transcription(user_id)
        if not last_doc or not last_doc.get('s3_object_key'):
            await self.send_message(chat_id, "❌ Couldn't find the previous file...");
            return
        lang_name = next((l['title'] for l in DEFAULT_POPULAR_TRANSCRIPTION_LANGS if l['code'] == lang_code),
                         lang_code.upper())
        await self.send_message(chat_id, f"✅ Got it! Retrying as {lang_name}...")
        if self.celery_app_client:
            self.celery_app_client.send_task('tasks.process_media', args=[user_id, last_doc['s3_object_key'],
                                                                          {'preferred_language': lang_code},
                                                                          {'platform': 'telegram', 'chat_id': chat_id}])

    async def _handle_translation_request(self, user_id: str, chat_id: int, target_lang_code: str):
        last_doc = self.database.get_last_transcription(user_id)
        if not last_doc or not last_doc.get('transcription'):
            await self.send_message(chat_id, "❌ Nothing to translate.");
            return
        text, source_lang = last_doc['transcription'], last_doc['detected_language']
        if target_lang_code == source_lang:
            await self.send_message(chat_id, "🤔 The text is already in this language!");
            return
        res = self.translation_service.translate_text(text, target_lang_code, source_lang)
        if res.get('success'):
            await self.send_message(chat_id,
                                    f"🔄 *Translation ({target_lang_code.upper()}):*\n\n{res['translated_text']}")
        else:
            await self.send_message(chat_id, f"❌ Translation failed: {res.get('error')}")

    async def _handle_file(self, file_obj, user_id: str, chat_id: int):
        await self.send_message(chat_id, "✅ File received. Processing...")
        local_file_path = None
        try:
            tg_file = await file_obj.get_file()
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.get(tg_file.file_path)
                response.raise_for_status()
                with tempfile.NamedTemporaryFile(delete=False,
                                                 suffix=os.path.splitext(tg_file.file_path)[-1]) as temp_f:
                    local_file_path = temp_f.name
                    temp_f.write(response.content)
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

    async def send_message(self, chat_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None):
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'}
        if reply_markup:
            payload['reply_markup'] = reply_markup.to_json()
        try:
            async with httpx.AsyncClient() as client:
                await client.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"Failed to send message to Telegram chat {chat_id}: {e}")