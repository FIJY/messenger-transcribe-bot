# services/message_handler.py
import logging
import os
import tempfile
import requests
import uuid
from typing import Dict, Any, Optional, List
from celery import Celery

from config.transcrib_suggestion_config import SUPPORTED_LANGUAGES_FOR_RETRY, MESSENGER_QUICK_REPLIES_LIMIT
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
            entry = webhook_event.get('entry', [])
            if not entry: return
            messaging = entry[0].get('messaging', [])
            if not messaging: return
            messaging_event = messaging[0]
            sender_id = messaging_event.get('sender', {}).get('id')
            if not sender_id: return

            user = self.database.get_user(sender_id)
            if not user:
                user = self.database.create_user(sender_id)
                self._send_text_message(sender_id, "🎉 Welcome! Please send an audio or video file to start.")
                return

            if 'message' in messaging_event:
                message = messaging_event['message']
                if 'quick_reply' in message and message['quick_reply'].get('payload'):
                    if self._handle_quick_reply(sender_id, message['quick_reply']['payload']):
                        return
                if 'text' in message and message.get('text'):
                    self._send_text_message(sender_id, "ℹ️ To get started, just send me an audio or video file.")
                    return
                if 'attachments' in message:
                    self._handle_attachments(sender_id, message['attachments'])
                    return
        except Exception as e:
            logger.error(f"Error in handle_message: {e}", exc_info=True)

    def send_language_correction_options(self, sender_id: str):
        try:
            quick_replies = []
            for lang in SUPPORTED_LANGUAGES_FOR_RETRY[:MESSENGER_QUICK_REPLIES_LIMIT]:
                quick_replies.append(
                    {"content_type": "text", "title": lang['title'], "payload": f"RETRY_AS_{lang['code']}"})
            message_data = {
                "recipient": {"id": sender_id},
                "messaging_type": "RESPONSE",
                "message": {"text": "Got it. What was the language, actually?", "quick_replies": quick_replies}
            }
            self._send_api_request(message_data)
        except Exception as e:
            logger.error(f"Error sending language correction options: {e}", exc_info=True)

    def send_translation_options(self, sender_id: str):
        try:
            translate_buttons = [
                {"content_type": "text", "title": "to English", "payload": "TRANSLATE_EN"},
                {"content_type": "text", "title": "на Русский", "payload": "TRANSLATE_RU"},
                {"content_type": "text", "title": "เป็นภาษาไทย", "payload": "TRANSLATE_TH"},
                {"content_type": "text", "title": "ទៅជាភាសាខ្មែរ", "payload": "TRANSLATE_KM"}
            ]
            message_data = {
                "recipient": {"id": sender_id},
                "messaging_type": "RESPONSE",
                "message": {"text": "What's next?", "quick_replies": translate_buttons}
            }
            self._send_api_request(message_data)
        except Exception as e:
            logger.error(f"Error sending translation options: {e}", exc_info=True)

    def _handle_quick_reply(self, sender_id: str, payload: str) -> bool:
        if payload.startswith('RETRY_AS_'):
            lang_code = payload.replace('RETRY_AS_', '').lower()
            self._handle_retry_request(sender_id, lang_code)
            return True
        elif payload.startswith('TRANSLATE_'):
            target_lang_code = payload.replace('TRANSLATE_', '').lower()
            self._handle_translation_request(sender_id, target_lang_code)
            return True
        elif payload == 'CHOOSE_OTHER_LANGUAGE':
            self.send_language_correction_options(sender_id)
            return True
        # ===> НОВЫЙ ОБРАБОТЧИК <===
        elif payload == 'CONFIRM_TRANSCRIPTION_OK':
            self.send_translation_options(sender_id)
            return True
        return False

    def _handle_retry_request(self, sender_id: str, lang_code: str):
        last_doc = self.database.get_last_transcription(sender_id)
        if not last_doc or not last_doc.get('s3_object_key'):
            self._send_text_message(sender_id, "❌ Couldn't find the previous file to re-process.")
            return
        lang_name = next((lang['title'] for lang in SUPPORTED_LANGUAGES_FOR_RETRY if lang['code'] == lang_code),
                         lang_code.upper())
        self._send_text_message(sender_id, f"✅ Got it! Retrying the process, assuming it's {lang_name}...")
        if celery_app_client:
            celery_app_client.send_task('tasks.process_media',
                                        args=[sender_id, last_doc['s3_object_key'], {'preferred_language': lang_code}])

    def _handle_translation_request(self, sender_id: str, target_lang_code: str):
        last_doc = self.database.get_last_transcription(sender_id)
        if not last_doc or not last_doc.get('transcription'):
            self._send_text_message(sender_id, "❌ Nothing to translate.")
            return
        original_text = last_doc['transcription']
        source_lang = last_doc['detected_language']
        if target_lang_code == source_lang:
            self._send_text_message(sender_id, "🤔 The text is already in this language!")
            return
        translation_result = self.translation_service.translate_text(original_text, target_lang_code, source_lang)
        if translation_result.get('success'):
            self._send_text_message(sender_id,
                                    f"🔄 **Translation ({target_lang_code.upper()}):**\n\n{translation_result['translated_text']}")
        else:
            self._send_text_message(sender_id, f"❌ Translation failed: {translation_result.get('error')}")

    def _handle_attachments(self, sender_id: str, attachments: List[Dict]):
        local_file_path = None
        try:
            if attachments[0].get('type') not in ['audio', 'video']:
                self._send_text_message(sender_id, "Please send an audio or video file.")
                return
            local_file_path = self._download_file_locally(attachments[0])
            if not local_file_path:
                self._send_text_message(sender_id, "❌ Could not download the file.")
                return
            object_key = f"{uuid.uuid4()}{os.path.splitext(local_file_path)[-1]}"
            if not self.s3_service.upload_file(local_file_path, object_key):
                self._send_text_message(sender_id, "❌ Server error: could not save the file.")
                return
            self._send_text_message(sender_id,
                                    "✅ Your file has been received. I'll send the result as soon as it's ready.")
            if celery_app_client:
                celery_app_client.send_task('tasks.process_media', args=[sender_id, object_key, {}])
        except Exception as e:
            logger.error(f"Error queuing task: {e}", exc_info=True)
        finally:
            if local_file_path and os.path.exists(local_file_path):
                os.remove(local_file_path)

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
            logger.error(f"Error downloading file locally: {e}", exc_info=True)
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