# services/telegram_handler.py
import os
import logging
import tempfile
import httpx
import uuid
import asyncio  # <== ФИНАЛЬНОЕ ИСПРАВЛЕНИЕ
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

    def __init__(self, token: str, database: Database, s3_service: S3Service, translation_service: TranslationService):
        if not token: raise ValueError("Telegram token is required.")
        self.token = token
        self.bot = Bot(token=self.token)
        self.database = database
        self.s3_service = s3_service
        # ===> ИЗМЕНЕНИЕ: Сохраняем сервис <===
        self.translation_service = translation_service
        self.celery_app_client = get_celery_app_client()

    async def handle_update(self, update_data: dict):
        update = Update.de_json(update_data, bot=self.bot)
        if update.callback_query:
            await self._handle_callback_query(update.callback_query)
            return
        if not update.message or not update.message.from_user:
            return
        user_id = str(update.message.from_user.id)
        user = self.database.get_user(user_id)
        if not user:
            user = self.database.create_user(user_id)
            await self.send_message(user_id, "🎉 Welcome! Please send an audio or video file to start.")
            return
        if update.message.text:
            state = user.get('state')
            if state == 'awaiting_language_input_transcription':
                await self._handle_language_text_input(user_id, user, update.message.text, 'transcription')
            elif state == 'awaiting_language_input_translation':
                await self._handle_language_text_input(user_id, user, update.message.text, 'translation')
            else:
                await self.send_message(user_id, "ℹ️ To get started, please send me an audio or video file.")
            return
        file_to_process = update.message.document or update.message.audio or update.message.video or update.message.voice
        if file_to_process:
            await self._handle_file(file_to_process, user_id, update.message.chat_id)

    async def _handle_callback_query(self, query: Update.callback_query):
        await query.answer()
        payload = query.data
        user_id = str(query.from_user.id)
        chat_id = query.message.chat_id
        user = self.database.get_user(user_id)
        if not user: return

        # Словарь для простых действий
        action_map = {
            'CHOOSE_OTHER_LANGUAGE': self.send_language_correction_options,
            'CONFIRM_TRANSCRIPTION_OK': self.send_translation_options,
        }

        # Словарь для действий с вводом текста
        input_action_map = {
            'INPUT_OTHER_TRANSCRIPTION_LANG': ('awaiting_language_input_transcription',
                                               "Please type the source language name or its 2-letter code (e.g., 'German' or 'de')."),
            'INPUT_OTHER_TRANSLATION_LANG': (
            'awaiting_language_input_translation', "Please type the target language for translation.")
        }

        if payload in action_map:
            await action_map[payload](chat_id, user)
            return

        if payload in input_action_map:
            state, message = input_action_map[payload]
            self.database.update_user(user_id, {'state': state})
            await self.send_message(chat_id, message)
            return

        # Обработка динамических payload'ов
        context_map = {'RETRY_AS_': 'transcription', 'TRANSLATE_': 'translation'}
        for prefix, context in context_map.items():
            if payload.startswith(prefix):
                code = payload.replace(prefix, '').lower()
                self.database.increment_language_usage(user_id, code, context)
                handler = self._handle_retry_request if context == 'transcription' else self._handle_translation_request
                await handler(user_id, chat_id, code)
                return

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
            title = title_info['title'] if title_info else lang_code.upper()
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

    async def _handle_language_text_input(self, user_id: str, user: Dict[str, Any], text: str, context: str):
        lang_code = SUPPORTED_LANGUAGES_MAP.get(text.lower().strip())
        chat_id = int(user_id)
        if lang_code:
            self.database.update_user(user_id, {'state': None})
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

    async def _handle_file(self, file_obj, user_id: int, chat_id: int):
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
                self.celery_app_client.send_task('tasks.process_media', args=[str(user_id), object_key, {},
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