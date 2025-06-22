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
                "daily_usage": 0,
                "total_transcriptions": 0,
                "is_premium": False,
                "preferred_language": None,
                "target_language": "en",
            }
            self.db.users.insert_one(user_data)
            return user_data
        except PyMongoError as e:
            logger.error(f"Error creating user {user_id}: {e}")
            raise

    def increment_usage(self, user_id: str):
        try:
            self.db.users.update_one(
                {"user_id": user_id},
                {"$inc": {"daily_usage": 1, "total_transcriptions": 1}}
            )
            logger.info(f"Incremented usage for user {user_id}")
        except PyMongoError as e:
            logger.error(f"Error incrementing usage for user {user_id}: {e}")

    def save_transcription(self, user_id: str, transcription: str, detected_language: str, object_key: str, **kwargs):
        """Сохраняет результат транскрипции, включая ключ объекта в S3/R2."""
        try:
            # Убираем ненужные для сохранения поля из kwargs
            kwargs.pop('success', None)
            kwargs.pop('processed_audio_path', None)

            transcription_data = {
                "user_id": user_id,
                "transcription": transcription,
                "detected_language": detected_language,
                "s3_object_key": object_key,
                "created_at": datetime.now(timezone.utc),
                **kwargs
            }
            self.db.transcriptions.insert_one(transcription_data)
            logger.info(f"Saved transcription for user {user_id} with S3 key {object_key}")
        except PyMongoError as e:
            logger.error(f"Error saving transcription for user {user_id}: {e}")

    def get_last_transcription(self, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            return self.db.transcriptions.find_one(
                {"user_id": user_id},
                sort=[("created_at", -1)]
            )
        except PyMongoError as e:
            logger.error(f"Error getting last transcription for user {user_id}: {e}")
            return None

    def set_user_language_preference(self, user_id: str, language: Optional[str]) -> bool:
        try:
            self.db.users.update_one({"user_id": user_id}, {"$set": {"preferred_language": language}})
            logger.info(f"Set language preference for user {user_id} to: {language}")
            return True
        except PyMongoError as e:
            logger.error(f"Error setting language preference for {user_id}: {e}")
            return False