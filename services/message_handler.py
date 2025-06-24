# services/message_handler.py
import logging
import os
import tempfile
import requests
import uuid
from typing import Dict, Any, Optional, List
from celery import Celery

from config.transcrib_suggestion_config import (
    DEFAULT_POPULAR_TRANSCRIPTION_LANGS,
    DEFAULT_POPULAR_TRANSLATION_LANGS,
    SUPPORTED_LANGUAGES_MAP
)
from .database import Database
from .s3_service import S3Service
from .translation_service import TranslationService

logger = logging.getLogger(__name__)

redis_url = os.getenv('REDIS_URL')
if not redis_url:
    logger.warning("REDIS_URL not found, Celery client will not work.")
    celery_app_client = None
else:
    celery_app_client = Celery('tasks_client', broker=redis_url)


class MessageHandler:
    def __init__(self, database: Database, translation_service: TranslationService):
        self.database = database
        self.s3_service = S3Service()
        self.translation_service = translation_service
        self.page_access_token = os.getenv('PAGE_ACCESS_TOKEN')

    def handle_message(self, webhook_event: Dict[str, Any]):
        try:
            messaging = webhook_event['entry'][0]['messaging'][0]
            sender_id = messaging['sender']['id']

            user = self.database.get_user(sender_id)
            if not user:
                user = self.database.create_user(sender_id)
                self._send_text_message(sender_id, "🎉 Welcome! Please send an audio or video file to start.")
                return

            if 'message' in messaging:
                message = messaging['message']
                if 'quick_reply' in message:
                    self._handle_quick_reply(sender_id, user, message['quick_reply']['payload'])
                    return
                if 'text' in message:
                    if user.get('state') == 'awaiting_language_input_transcription':
                        self._handle_language_text_input(sender_id, user, message['text'], 'transcription')
                    elif user.get('state') == 'awaiting_language_input_translation':
                        self._handle_language_text_input(sender_id, user, message['text'], 'translation')
                    else:
                        self._send_text_message(sender_id, "ℹ️ To get started, just send me an audio or video file.")
                    return
                if 'attachments' in message:
                    self._handle_attachments(sender_id, message['attachments'])
        except (KeyError, IndexError) as e:
            logger.warning(f"Received a webhook event with unexpected structure: {e}")
        except Exception as e:
            logger.error(f"Error in handle_message: {e}", exc_info=True)

    def _build_smart_buttons(self, user: Dict[str, Any], context: str) -> List[Dict]:
        """Builds a list of quick reply buttons based on user history and global defaults."""
        if context == 'transcription':
            default_popular_langs = DEFAULT_POPULAR_TRANSCRIPTION_LANGS
            usage_stats = user.get('transcription_lang_usage', {})
            payload_prefix = "RETRY_AS_"
            other_payload = "INPUT_OTHER_TRANSCRIPTION_LANG"
        else:  # context == 'translation'
            default_popular_langs = DEFAULT_POPULAR_TRANSLATION_LANGS
            usage_stats = user.get('translation_lang_usage', {})
            payload_prefix = "TRANSLATE_"
            other_payload = "INPUT_OTHER_TRANSLATION_LANG"

        # Get user's personal top languages
        sorted_user_langs = sorted(usage_stats.keys(), key=usage_stats.get, reverse=True)

        final_buttons = []
        added_codes = set()

        # Add up to 3 personal languages
        for lang_code in sorted_user_langs[:3]:
            # Find the title for the button
            lang_info = next((lang for lang in default_popular_langs if lang['code'] == lang_code), None)
            title = lang_info['title'] if lang_info else lang_code.upper()
            final_buttons.append({"content_type": "text", "title": title, "payload": f"{payload_prefix}{lang_code}"})
            added_codes.add(lang_code)

        # Add up to 4 global popular languages, avoiding duplicates
        for lang in default_popular_langs:
            if len(final_buttons) >= 7: break
            if lang['code'] not in added_codes:
                final_buttons.append(
                    {"content_type": "text", "title": lang['title'], "payload": f"{payload_prefix}{lang['code']}"})
                added_codes.add(lang['code'])

        # Add the 'Type other' button
        final_buttons.append({"content_type": "text", "title": "✍️ Type other...", "payload": other_payload})

        return final_buttons

    def send_language_correction_options(self, sender_id: str, user: Dict[str, Any]):
        quick_replies = self._build_smart_buttons(user, 'transcription')
        message_data = {
            "recipient": {"id": sender_id}, "messaging_type": "RESPONSE",
            "message": {"text": "Got it. What was the language, actually?", "quick_replies": quick_replies}
        }
        self._send_api_request(message_data)

    def send_translation_options(self, sender_id: str, user: Dict[str, Any]):
        quick_replies = self._build_smart_buttons(user, 'translation')
        message_data = {
            "recipient": {"id": sender_id}, "messaging_type": "RESPONSE",
            "message": {"text": "What language would you like to translate to?", "quick_replies": quick_replies}
        }
        self._send_api_request(message_data)

    def _handle_quick_reply(self, sender_id: str, user: Dict[str, Any], payload: str) -> bool:
        self.database.update_user(sender_id, {'state': None})  # Reset state on any button press

        if payload.startswith('RETRY_AS_'):
            lang_code = payload.replace('RETRY_AS_', '').lower()
            self.database.increment_language_usage(sender_id, lang_code, 'transcription')
            self._handle_retry_request(sender_id, lang_code)
            return True
        elif payload.startswith('TRANSLATE_'):
            target_lang_code = payload.replace('TRANSLATE_', '').lower()
            self.database.increment_language_usage(sender_id, target_lang_code, 'translation')
            self._handle_translation_request(sender_id, target_lang_code)
            return True
        elif payload == 'CHOOSE_OTHER_LANGUAGE':
            self.send_language_correction_options(sender_id, user)
            return True
        elif payload == 'CONFIRM_TRANSCRIPTION_OK':
            self.send_translation_options(sender_id, user)
            return True
        elif payload == 'INPUT_OTHER_TRANSCRIPTION_LANG':
            self.database.update_user(sender_id, {'state': 'awaiting_language_input_transcription'})
            self._send_text_message(sender_id,
                                    "Please type the source language name or its 2-letter code (e.g., 'German' or 'de').")
            return True
        elif payload == 'INPUT_OTHER_TRANSLATION_LANG':
            self.database.update_user(sender_id, {'state': 'awaiting_language_input_translation'})
            self._send_text_message(sender_id, "Please type the target language for translation.")
            return True

        return False

    def _handle_language_text_input(self, sender_id: str, user: Dict[str, Any], text: str, context: str):
        lang_input = text.lower().strip()
        lang_code = SUPPORTED_LANGUAGES_MAP.get(lang_input)

        if lang_code:
            self.database.update_user(sender_id, {'state': None})
            self.database.increment_language_usage(sender_id, lang_code, context)
            if context == 'transcription':
                self._handle_retry_request(sender_id, lang_code)
            else:  # context == 'translation'
                self._handle_translation_request(sender_id, lang_code)
        else:
            self._send_text_message(sender_id, f"Sorry, I don't recognize '{text}'. Please try again.")

    def _handle_retry_request(self, sender_id: str, lang_code: str):
        last_doc = self.database.get_last_transcription(sender_id)
        if not last_doc or not last_doc.get('s3_object_key'):
            self._send_text_message(sender_id, "❌ Couldn't find the previous file to re-process.");
            return

        lang_name = lang_code.upper()  # Fallback name
        for lang in DEFAULT_POPULAR_TRANSCRIPTION_LANGS:
            if lang['code'] == lang_code: lang_name = lang['title']; break

        self._send_text_message(sender_id, f"✅ Got it! Retrying the process, assuming it's {lang_name}...")
        if celery_app_client:
            celery_app_client.send_task('tasks.process_media',
                                        args=[sender_id, last_doc['s3_object_key'], {'preferred_language': lang_code}])

    def _handle_translation_request(self, sender_id: str, target_lang_code: str):
        last_doc = self.database.get_last_transcription(sender_id)
        if not last_doc or not last_doc.get('transcription'):
            self._send_text_message(sender_id, "❌ Nothing to translate.");
            return
        original_text = last_doc['transcription']
        source_lang = last_doc['detected_language']
        if target_lang_code == source_lang:
            self._send_text_message(sender_id, "🤔 The text is already in this language!");
            return

        translation_result = self.translation_service.translate_text(original_text, target_lang_code, source_lang)
        if translation_result.get('success'):
            # Using the agreed-upon format
            response_text = f"🔄 **Translation ({target_lang_code.upper()}):**\n\n{translation_result['translated_text']}"
            self._send_text_message(sender_id, response_text)
        else:
            self._send_text_message(sender_id, f"❌ Translation failed: {translation_result.get('error')}")

    def _handle_attachments(self, sender_id: str, attachments: List[Dict]):
        local_file_path = None
        try:
            if attachments[0].get('type') not in ['audio', 'video']:
                self._send_text_message(sender_id, "Please send an audio or video file.");
                return
            local_file_path = self._download_file_locally(attachments[0])
            if not local_file_path:
                self._send_text_message(sender_id, "❌ Could not download the file.");
                return
            object_key = f"{uuid.uuid4()}{os.path.splitext(local_file_path)[-1]}"
            if not self.s3_service.upload_file(local_file_path, object_key):
                self._send_text_message(sender_id, "❌ Server error: could not save the file.");
                return
            self._send_text_message(sender_id,
                                    "✅ Your file has been received. I'll send the result as soon as it's ready.")
            if celery_app_client:
                celery_app_client.send_task('tasks.process_media', args=[sender_id, object_key, {}])
        except Exception as e:
            logger.error(f"Error queuing task: {e}", exc_info=True)
        finally:
            if local_file_path and os.path.exists(local_file_path): os.remove(local_file_path)

    def _download_file_locally(self, attachment: Dict) -> Optional[str]:
        try:
            file_url = attachment.get('payload', {}).get('url')
            if not file_url: return None
            with requests.get(file_url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as f:
                    for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
                    return f.name
        except Exception as e:
            logger.error(f"Error downloading file locally: {e}", exc_info=True);
            return None

    def _send_text_message(self, recipient_id: str, message_text: str):
        self._send_api_request({'recipient': {'id': recipient_id}, 'message': {'text': message_text}})

    def _send_api_request(self, message_data: Dict[str, Any]):
        try:
            params = {'access_token': self.page_access_token}
            requests.post("https://graph.facebook.com/v18.0/me/messages", params=params, json=message_data,
                          timeout=10).raise_for_status()
        except Exception as e:
            logger.error(f"Error sending API request: {e}", exc_info=True)