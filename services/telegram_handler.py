# services/telegram_handler.py
import os
import logging
import tempfile
import httpx
import uuid
from typing import Dict, Any, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import CallbackContext

from .database import Database
from .s3_service import S3Service
from .celery_client import get_celery_app_client
from config.transcrib_suggestion_config import (
    DEFAULT_POPULAR_TRANSCRIPTION_LANGS,
    DEFAULT_POPULAR_TRANSLATION_LANGS,
    SUPPORTED_LANGUAGES_MAP
)

logger = logging.getLogger(__name__)


class TelegramHandler:
    def __init__(self, token: str, database: Database, s3_service: S3Service):
        if not token: raise ValueError("Telegram token is required.")
        self.token = token
        self.bot = Bot(token=self.token)
        self.database = database
        self.s3_service = s3_service
        self.celery_app_client = get_celery_app_client()
        # ===> ИЗМЕНЕНИЕ: Создаем единый http-клиент <===
        self.http_client = httpx.AsyncClient(timeout=30.0)

    async def handle_update(self, update_data: dict):
        # ... (этот метод без изменений) ...
        update = Update.de_json(update_data, bot=self.bot)
        if update.callback_query:
            await self._handle_callback_query(update.callback_query)
            return
        if not update.message or not update.message.from_user:
            logger.warning("Received an update without a message or user.")
            return
        user_id = str(update.message.from_user.id)
        user = self.database.get_user(user_id)
        if not user:
            user = self.database.create_user(user_id)
            await self.send_message(user_id, "🎉 Welcome! Send me an audio, video, or voice message to start.")
            return
        if update.message.text:
            if user.get('state') == 'awaiting_language_input_transcription':
                await self._handle_language_text_input(user_id, user, update.message.text, 'transcription')
            elif user.get('state') == 'awaiting_language_input_translation':
                await self._handle_language_text_input(user_id, user, update.message.text, 'translation')
            else:
                await self.send_message(user_id, "ℹ️ To get started, please send me an audio, video, or voice message.")
            return
        file_to_process = update.message.document or update.message.audio or update.message.video or update.message.voice
        if file_to_process:
            await self._handle_file(file_to_process, user_id, update.message.chat_id)

    # ... (все методы до _handle_file без изменений) ...
    async def _handle_callback_query(self, query: Update.callback_query):
        await query.answer()
        payload = query.data
        user_id = str(query.from_user.id)
        chat_id = query.message.chat_id
        user = self.database.get_user(user_id)
        if not user:
            logger.warning(f"CallbackQuery received from an unknown user: {user_id}")
            return
        if payload.startswith('RETRY_AS_'):
            lang_code = payload.replace('RETRY_AS_', '').lower()
            self.database.increment_language_usage(user_id, lang_code, 'transcription')
            await self._handle_retry_request(user_id, chat_id, lang_code)
        elif payload.startswith('TRANSLATE_'):
            target_lang_code = payload.replace('TRANSLATE_', '').lower()
            self.database.increment_language_usage(user_id, target_lang_code, 'translation')
            await self._handle_translation_request(user_id, chat_id, target_lang_code)
        elif payload == 'CHOOSE_OTHER_LANGUAGE':
            await self.send_language_correction_options(chat_id, user)
        elif payload == 'CONFIRM_TRANSCRIPTION_OK':
            await self.send_translation_options(chat_id, user)
        elif payload == 'INPUT_OTHER_TRANSCRIPTION_LANG':
            self.database.update_user(user_id, {'state': 'awaiting_language_input_transcription'})
            await self.send_message(chat_id,
                                    "Please type the source language name or its 2-letter code (e.g., 'German' or 'de').")
        elif payload == 'INPUT_OTHER_TRANSLATION_LANG':
            self.database.update_user(user_id, {'state': 'awaiting_language_input_translation'})
            await self.send_message(chat_id, "Please type the target language for translation.")

    def _build_smart_buttons(self, user: Dict[str, Any], context: str) -> List[List[InlineKeyboardButton]]:
        if context == 'transcription':
            default_popular_langs = DEFAULT_POPULAR_TRANSCRIPTION_LANGS
            usage_stats = user.get('transcription_lang_usage', {})
            payload_prefix = "RETRY_AS_"
            other_payload = "INPUT_OTHER_TRANSCRIPTION_LANG"
        else:
            default_popular_langs = DEFAULT_POPULAR_TRANSLATION_LANGS
            usage_stats = user.get('translation_lang_usage', {})
            payload_prefix = "TRANSLATE_"
            other_payload = "INPUT_OTHER_TRANSLATION_LANG"
        sorted_user_langs = sorted(usage_stats.keys(), key=usage_stats.get, reverse=True)
        button_row, added_codes = [], set()
        for lang_code in sorted_user_langs[:3]:
            lang_info = next((lang for lang in default_popular_langs if lang['code'] == lang_code), None)
            title = lang_info['title'] if lang_info else lang_code.upper()
            button_row.append(InlineKeyboardButton(title, callback_data=f"{payload_prefix}{lang_code}"))
            added_codes.add(lang_code)
        for lang in default_popular_langs:
            if len(button_row) >= 5: break
            if lang['code'] not in added_codes:
                button_row.append(InlineKeyboardButton(lang['title'], callback_data=f"{payload_prefix}{lang['code']}"))
                added_codes.add(lang['code'])
        other_button_row = [InlineKeyboardButton("✍️ Type other...", callback_data=other_payload)]
        return [button_row, other_button_row]

    async def send_language_correction_options(self, chat_id: int, user: Dict[str, Any]):
        keyboard = self._build_smart_buttons(user, 'transcription')
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_message(chat_id, "Got it. What was the language, actually?", reply_markup)

    async def send_translation_options(self, chat_id: int, user: Dict[str, Any]):
        keyboard = self._build_smart_buttons(user, 'translation')
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.send_message(chat_id, "What language would you like to translate to?", reply_markup)

    async def _handle_language_text_input(self, user_id: str, user: Dict[str, Any], text: str, context: str):
        lang_input = text.lower().strip()
        lang_code = SUPPORTED_LANGUAGES_MAP.get(lang_input)
        if lang_code:
            self.database.update_user(user_id, {'state': None})
            self.database.increment_language_usage(user_id, lang_code, context)
            chat_id = int(user_id)
            if context == 'transcription':
                await self._handle_retry_request(user_id, chat_id, lang_code)
            else:
                await self._handle_translation_request(user_id, chat_id, lang_code)
        else:
            await self.send_message(int(user_id), f"Sorry, I don't recognize '{text}'. Please try again.")

    async def _handle_retry_request(self, user_id: str, chat_id: int, lang_code: str):
        last_doc = self.database.get_last_transcription(user_id)
        if not last_doc or not last_doc.get('s3_object_key'):
            await self.send_message(chat_id, "❌ Couldn't find the previous file to re-process.");
            return
        lang_name = next((lang['title'] for lang in DEFAULT_POPULAR_TRANSCRIPTION_LANGS if lang['code'] == lang_code),
                         lang_code.upper())
        await self.send_message(chat_id, f"✅ Got it! Retrying the process, assuming it's {lang_name}...")
        if self.celery_app_client:
            platform_payload = {'platform': 'telegram', 'chat_id': chat_id}
            self.celery_app_client.send_task('tasks.process_media', args=[user_id, last_doc['s3_object_key'],
                                                                          {'preferred_language': lang_code},
                                                                          platform_payload])

    async def _handle_translation_request(self, user_id: str, chat_id: int, target_lang_code: str):
        last_doc = self.database.get_last_transcription(user_id)
        if not last_doc or not last_doc.get('transcription'):
            await self.send_message(chat_id, "❌ Nothing to translate.");
            return
        original_text, source_lang = last_doc['transcription'], last_doc['detected_language']
        if target_lang_code == source_lang:
            await self.send_message(chat_id, "🤔 The text is already in this language!");
            return
        translation_result = self.translation_service.translate_text(original_text, target_lang_code, source_lang)
        if translation_result.get('success'):
            response_text = f"🔄 *Translation ({target_lang_code.upper()}):*\n\n{translation_result['translated_text']}"
            await self.send_message(chat_id, response_text)
        else:
            await self.send_message(chat_id, f"❌ Translation failed: {translation_result.get('error')}")

    async def _handle_file(self, file_obj, user_id: int, chat_id: int):
        await self.send_message(chat_id, "✅ File received. Processing...")
        local_file_path = None
        try:
            tg_file = await file_obj.get_file()
            # ===> ИЗМЕНЕНИЕ: Используем единый http-клиент <===
            response = await self.http_client.get(tg_file.file_path)
            response.raise_for_status()

            original_filename = file_obj.file_name if hasattr(file_obj, 'file_name') and file_obj.file_name else ''
            file_extension = os.path.splitext(original_filename)[-1] if original_filename else '.tmp'

            with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_f:
                local_file_path = temp_f.name
                temp_f.write(response.content)

            object_key = f"{uuid.uuid4()}{file_extension}"
            if not self.s3_service.upload_file(local_file_path, object_key):
                await self.send_message(chat_id, "❌ Server error: could not save the file.");
                return
            if self.celery_app_client:
                task_payload = {'platform': 'telegram', 'chat_id': chat_id}
                self.celery_app_client.send_task('tasks.process_media',
                                                 args=[str(user_id), object_key, {}, task_payload])
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
            # ===> ИЗМЕНЕНИЕ: Используем единый http-клиент <===
            response = await self.http_client.post(url, json=payload)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to send message to Telegram chat {chat_id}: {e}")