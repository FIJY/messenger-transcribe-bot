# services/database.py
import os
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from pymongo import MongoClient
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.mongodb_uri = os.getenv('MONGODB_URI')
        if not self.mongodb_uri:
            raise ValueError("MONGODB_URI environment variable is required")
        self.client = None
        self.db = None
        self.connect()

    def connect(self):
        try:
            self.client = MongoClient(self.mongodb_uri)
            self.db = self.client.messenger_transcribe_bot
            self.client.admin.command('ping')
            logger.info("Successfully connected to MongoDB")
            self._create_indexes()
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    def _create_indexes(self):
        self.db.users.create_index("user_id", unique=True)
        self.db.transcriptions.create_index([("user_id", 1), ("created_at", -1)])

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            return self.db.users.find_one({"user_id": user_id})
        except PyMongoError as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None

    def create_user(self, user_id: str, **kwargs) -> Dict[str, Any]:
        try:
            now = datetime.now(timezone.utc)
            user_data = {
                "user_id": user_id,
                "created_at": now,
                "last_seen": now,
                "is_premium": False,
                "state": None,
                # ===> НОВЫЕ ПОЛЯ ДЛЯ СТАТИСТИКИ <===
                "transcription_lang_usage": {}, # e.g. {'km': 10, 'en': 5}
                "translation_lang_usage": {}    # e.g. {'en': 8, 'ru': 2}
            }
            self.db.users.insert_one(user_data)
            logger.info(f"Created new user {user_id}")
            return user_data
        except PyMongoError as e:
            logger.error(f"Error creating user {user_id}: {e}")
            raise

    def update_user(self, user_id: str, update_data: Dict[str, Any]) -> bool:
        try:
            result = self.db.users.update_one({"user_id": user_id}, {"$set": update_data})
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Error updating user {user_id}: {e}")
            return False

    # ===> НОВЫЙ МЕТОД ДЛЯ ОБНОВЛЕНИЯ СТАТИСТИКИ <===
    def increment_language_usage(self, user_id: str, lang_code: str, context: str):
        """
        Increments the usage count for a specific language in a given context.
        :param user_id: The user's ID.
        :param lang_code: The two-letter language code (e.g., 'km').
        :param context: 'transcription' or 'translation'.
        """
        if context not in ['transcription', 'translation']:
            logger.error(f"Invalid context '{context}' for language usage increment.")
            return

        field_to_update = f"{context}_lang_usage.{lang_code}"
        try:
            self.db.users.update_one(
                {"user_id": user_id},
                {"$inc": {field_to_update: 1}}
            )
            logger.info(f"Incremented {context} usage for lang '{lang_code}' for user {user_id}")
        except PyMongoError as e:
            logger.error(f"Error incrementing language usage for user {user_id}: {e}")


    def save_transcription(self, user_id: str, object_key: str, **kwargs):
        try:
            kwargs.pop('success', None)
            kwargs.pop('processed_audio_path', None)
            kwargs.pop('original_file_path', None)

            transcription_data = { "user_id": user_id, "s3_object_key": object_key, "created_at": datetime.now(timezone.utc), **kwargs }
            self.db.transcriptions.insert_one(transcription_data)
            logger.info(f"Saved transcription for user {user_id} with S3 key {object_key}")
        except PyMongoError as e:
            logger.error(f"Error saving transcription for user {user_id}: {e}")

    def get_last_transcription(self, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            return self.db.transcriptions.find_one( {"user_id": user_id}, sort=[("created_at", -1)])
        except PyMongoError as e:
            logger.error(f"Error getting last transcription for user {user_id}: {e}")
            return None