# services/database.py
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from bson import ObjectId

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
        if not self.mongodb_uri: raise ValueError("MONGODB_URI environment variable is required")
        self.client = MongoClient(self.mongodb_uri, tz_aware=True, tzinfo=timezone.utc)
        self.db = self.client.transcribe_bot
        self._create_indexes()
        logger.info("Successfully connected to MongoDB")

    def _create_indexes(self):
        self.db.users.create_index("user_id", unique=True)
        self.db.notes.create_index([("user_id", 1), ("created_at", -1)])
        self.db.notes.create_index([("content", "text")], default_language="none")
        self.db.raw_transcriptions.create_index("s3_object_key", unique=True)
        self.db.raw_transcriptions.create_index("created_at", expireAfterSeconds=604800)  # 7 дней
        self.db.app_counters.create_index("name", unique=True)

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self.db.users.find_one({"user_id": str(user_id)})

    def create_user(self, user_id: str, **kwargs) -> Dict[str, Any]:
        user_count_doc = self.db.app_counters.find_one_and_update(
            {'name': 'total_users'}, {'$inc': {'count': 1}}, upsert=True, return_document=True)
        free_minutes = 10 if user_count_doc.get('count', 0) <= 50 else 5
        user_data = {
            "_id": str(user_id),
            "user_id": str(user_id),
            "username": kwargs.get('username'),
            "created_at": datetime.now(timezone.utc),
            "last_seen": datetime.now(timezone.utc),
            "plan": "free",
            "minutes_limit": free_minutes,
            "minutes_used": 0.0,
            "subscription_expires_at": None,
            "state": None  # Поле для отслеживания режима чата
        }
        self.db.users.update_one({"_id": str(user_id)}, {"$setOnInsert": user_data}, upsert=True)
        logger.info(f"Created or found user {user_id} with {free_minutes} free minutes.")
        return self.get_user(user_id)

    def save_raw_transcription(self, s3_key: str, **kwargs):
        data = {"s3_object_key": s3_key, "created_at": datetime.now(timezone.utc), **kwargs}
        self.db.raw_transcriptions.update_one({"s3_object_key": s3_key}, {"$set": data}, upsert=True)

    def get_raw_transcription(self, s3_key: str) -> Optional[Dict[str, Any]]:
        return self.db.raw_transcriptions.find_one({"s3_object_key": s3_key})

    def save_note(self, user_id: str, content: str, **kwargs) -> ObjectId:
        note_data = {
            "user_id": user_id, "content": content, "created_at": datetime.now(timezone.utc),
            "type": "note", "tags": kwargs.get('tags', []), "s3_object_key": kwargs.get('s3_object_key'),
            "source_language": kwargs.get('detected_language'), "duration_minutes": kwargs.get('duration_minutes'),
            "source_type": kwargs.get('source_type'),
            "reports": {}
        }
        result = self.db.notes.insert_one(note_data)
        logger.info(f"Saved note for user {user_id}. Note ID: {result.inserted_id}")
        return result.inserted_id

    def get_note_by_id(self, note_id: ObjectId) -> Optional[Dict[str, Any]]:
        return self.db.notes.find_one({"_id": note_id})

    def search_notes_by_query(self, user_id: str, search_query: str, limit: int = 10) -> List[Dict[str, Any]]:
        query = {
            "user_id": user_id,
            "$text": {"$search": search_query}
        }
        projection = {'score': {'$meta': 'textScore'}}
        return list(
            self.db.notes.find(query, projection)
            .sort([('score', {'$meta': 'textScore'})])
            .limit(limit)
        )

    def update_note(self, note_id: ObjectId, updates: Dict[str, Any]) -> bool:
        logger.info(f"Attempting to update note {note_id} with operators: {list(updates.keys())}")
        result = self.db.notes.update_one({"_id": note_id}, updates)

        if result.modified_count > 0:
            logger.info(f"Successfully updated note {note_id}. Documents modified: {result.modified_count}.")
            return True
        elif result.matched_count > 0 and result.modified_count == 0:
            logger.warning(f"Found note {note_id}, but no changes were made. The data might be the same.")
            return False
        else:
            logger.error(f"Failed to find note {note_id} to update.")
            return False

    def delete_note(self, note_id: ObjectId) -> bool:
        result = self.db.notes.delete_one({"_id": note_id})
        return result.deleted_count > 0

    def update_user_subscription(self, user_id: str, plan_name: str) -> Optional[Dict[str, Any]]:
        if plan_name not in PLANS: return None
        plan_details = PLANS[plan_name]
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=plan_details['duration_days'])
        update_fields = {
            "plan": plan_name, "minutes_limit": plan_details['limit_minutes'], "minutes_used": 0.0,
            "subscription_expires_at": expires_at, "last_seen": now
        }
        self.db.users.update_one({"user_id": str(user_id)}, {"$set": update_fields})
        return update_fields

    def downgrade_user_to_free(self, user_id: str):
        update_fields = {"plan": "free", "minutes_limit": 5, "minutes_used": 0.0, "subscription_expires_at": None}
        self.db.users.update_one({"user_id": str(user_id)}, {"$set": update_fields})

    def update_minutes_used(self, user_id: str, minutes_to_add: float):
        self.db.users.update_one({"user_id": str(user_id)}, {"$inc": {"minutes_used": minutes_to_add}})

    def update_user(self, user_id: str, update_data: Dict[str, Any]) -> bool:
        result = self.db.users.update_one({"user_id": str(user_id)}, {"$set": update_data})
        return result.modified_count > 0

    def grant_premium_subscription(self, user_id: str, days: int) -> bool:
        user = self.get_user(user_id)
        if not user:
            logger.warning(f"Attempted to grant premium to non-existent user: {user_id}")
            return False

        now = datetime.now(timezone.utc)
        current_expiry = user.get('subscription_expires_at')

        if current_expiry and current_expiry > now:
            new_expiry_date = current_expiry + timedelta(days=days)
        else:
            new_expiry_date = now + timedelta(days=days)

        premium_plan = PLANS['premium']

        update_data = {
            "$set": {
                "plan": "premium",
                "subscription_expires_at": new_expiry_date,
                "minutes_limit": premium_plan['limit_minutes'],
                "minutes_used": 0
            }
        }

        try:
            result = self.db.users.update_one({"user_id": user_id}, update_data)
            if result.modified_count > 0:
                logger.info(
                    f"Granted premium for {days} days to user {user_id}. New expiry: {new_expiry_date.isoformat()}")
                return True
            else:
                logger.warning(f"User {user_id} found, but subscription was not updated. Matched: {result.matched_count}")
                return False
        except Exception as e:
            logger.error(f"Failed to grant premium to user {user_id}: {e}", exc_info=True)
            return False
