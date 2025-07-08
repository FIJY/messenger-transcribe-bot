# services/database.py
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from bson import ObjectId
import re

from pymongo import MongoClient
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)

PLANS = {
    'free': {'limit_minutes': 10, 'duration_days': 9999, 'price_usd': 0},
    'basic': {'limit_minutes': 60, 'duration_days': 30, 'price_usd': 5},
    'premium': {'limit_minutes': 150, 'duration_days': 30, 'price_usd': 10}
}


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
            self.client = MongoClient(self.mongodb_uri, tz_aware=True, tzinfo=timezone.utc)
            self.db = self.client.messenger_transcribe_bot
            self.client.admin.command('ping')
            logger.info("Successfully connected to MongoDB")
            self._create_indexes()
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    def _create_indexes(self):
        self.db.users.create_index("user_id", unique=True)
        self.db.notes.create_index([("user_id", 1), ("created_at", -1)])
        self.db.notes.create_index([("content", "text")])
        self.db.app_counters.create_index("name", unique=True)

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            return self.db.users.find_one({"user_id": str(user_id)})
        except PyMongoError as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None

    def create_user(self, user_id: str, **kwargs) -> Dict[str, Any]:
        try:
            now = datetime.now(timezone.utc)
            user_count_doc = self.db.app_counters.find_one_and_update(
                {'name': 'total_users'}, {'$inc': {'count': 1}}, upsert=True, return_document=True
            )
            user_count = user_count_doc.get('count', 0)
            free_minutes = 10 if user_count <= 50 else 5
            user_data = {
                "user_id": str(user_id), "username": kwargs.get('username'), "created_at": now,
                "last_seen": now, "plan": "free", "minutes_limit": free_minutes, "minutes_used": 0.0,
                "subscription_expires_at": None, "state": None, "transcription_lang_usage": {},
                "translation_lang_usage": {}
            }
            self.db.users.insert_one(user_data)
            logger.info(f"Created new user {user_id} with {free_minutes} free minutes (user #{user_count}).")
            return user_data
        except PyMongoError as e:
            logger.error(f"Error creating user {user_id}: {e}")
            raise

    def save_note(self, user_id: str, content: str, **kwargs) -> ObjectId:
        try:
            note_data = {
                "user_id": user_id, "content": content, "created_at": datetime.now(timezone.utc),
                "type": "note", "tags": [], "s3_object_key": kwargs.get('s3_object_key'),
                "source_language": kwargs.get('detected_language'), "duration_minutes": kwargs.get('duration_minutes'),
            }
            result = self.db.notes.insert_one(note_data)
            logger.info(f"Saved note for user {user_id}. Note ID: {result.inserted_id}")
            return result.inserted_id
        except PyMongoError as e:
            logger.error(f"Error saving note for user {user_id}: {e}")
            raise

    def get_note_by_id(self, note_id: ObjectId) -> Optional[Dict[str, Any]]:
        try:
            return self.db.notes.find_one({"_id": note_id})
        except PyMongoError as e:
            logger.error(f"Error getting note {note_id}: {e}")
            return None

    def find_notes_by_keywords(self, user_id: str, keywords: List[str], limit: int = 5) -> List[Dict[str, Any]]:
        try:
            query = {
                "user_id": user_id,
                "$or": [{"content": re.compile(keyword, re.IGNORECASE)} for keyword in keywords]
            }
            return list(self.db.notes.find(query).sort("created_at", -1).limit(limit))
        except PyMongoError as e:
            logger.error(f"Error finding notes by keywords for user {user_id}: {e}")
            return []

    def get_notes_for_period(self, user_id: str, days: int) -> List[Dict[str, Any]]:
        try:
            start_date = datetime.now(timezone.utc) - timedelta(days=days)
            query = {"user_id": user_id, "created_at": {"$gte": start_date}}
            return list(self.db.notes.find(query).sort("created_at", 1))
        except PyMongoError as e:
            logger.error(f"Error getting notes for period for user {user_id}: {e}")
            return []

    def update_note(self, note_id: ObjectId, updates: Dict[str, Any]) -> bool:
        try:
            result = self.db.notes.update_one({"_id": note_id}, {"$set": updates})
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Error updating note {note_id}: {e}")
            return False

    def delete_note(self, note_id: ObjectId) -> bool:
        try:
            result = self.db.notes.delete_one({"_id": note_id})
            return result.deleted_count > 0
        except PyMongoError as e:
            logger.error(f"Error deleting note {note_id}: {e}")
            return False

    def update_user_subscription(self, user_id: str, plan_name: str) -> Optional[Dict[str, Any]]:
        if plan_name not in PLANS: return None
        plan_details = PLANS[plan_name]
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=plan_details['duration_days'])
        update_fields = {
            "plan": plan_name, "minutes_limit": plan_details['limit_minutes'], "minutes_used": 0.0,
            "subscription_expires_at": expires_at, "last_seen": now
        }
        try:
            self.db.users.update_one({"user_id": str(user_id)}, {"$set": update_fields})
            return update_fields
        except PyMongoError:
            return None

    def downgrade_user_to_free(self, user_id: str):
        try:
            update_fields = {
                "plan": "free", "minutes_limit": 5, "minutes_used": 0.0, "subscription_expires_at": None
            }
            self.db.users.update_one({"user_id": str(user_id)}, {"$set": update_fields})
        except PyMongoError:
            pass

    def update_minutes_used(self, user_id: str, minutes_to_add: float):
        try:
            self.db.users.update_one({"user_id": str(user_id)}, {"$inc": {"minutes_used": minutes_to_add}})
        except PyMongoError:
            pass

    def update_user(self, user_id: str, update_data: Dict[str, Any]) -> bool:
        try:
            result = self.db.users.update_one({"user_id": str(user_id)}, {"$set": update_data})
            return result.modified_count > 0
        except PyMongoError:
            return False