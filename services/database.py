# services/database.py
import os
import logging
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        # ИСПРАВЛЕНО: Используем правильное имя переменной MONGODB_URI
        mongo_uri = os.getenv('MONGODB_URI')
        if not mongo_uri:
            # ИСПРАВЛЕНО: Сообщение об ошибке тоже должно быть правильным
            raise ValueError("MONGODB_URI environment variable not set.")
        self.client = MongoClient(mongo_uri)
        self.db = self.client.get_default_database()
        self.users = self.db.users
        self.notes = self.db.notes
        logger.info("Successfully connected to MongoDB")

    def create_user(self, user_id: str, username: str, language_code: str):
        user_data = {
            'user_id': user_id,
            'username': username,
            'language_code': language_code,
            'plan': 'free',
            'created_at': datetime.utcnow(),
            'state': None
        }
        self.users.insert_one(user_data.copy())
        logger.info(f"New user created with ID: {user_id}")
        return user_data

    def get_user(self, user_id: str):
        return self.users.find_one({'user_id': user_id})

    def update_user(self, user_id: str, updates: dict):
        self.users.update_one({'user_id': user_id}, {'$set': updates})

    def save_note(self, **kwargs):
        note_data = {
            'created_at': datetime.utcnow(),
            **kwargs
        }
        result = self.notes.insert_one(note_data)
        return result.inserted_id

    def get_note_by_id(self, note_id: ObjectId):
        return self.notes.find_one({'_id': note_id})

    def update_note(self, note_id: ObjectId, updates: dict):
        self.notes.update_one({'_id': note_id}, updates)

    def delete_note(self, note_id: ObjectId):
        result = self.notes.delete_one({'_id': note_id})
        return result.deleted_count > 0

    def grant_premium_subscription(self, user_id: str, days: int):
        user = self.get_user(user_id)
        if not user:
            return False

        expires_at = user.get('subscription_expires_at', datetime.utcnow())
        if expires_at < datetime.utcnow():
            expires_at = datetime.utcnow()

        new_expires_at = expires_at + timedelta(days=days)

        self.update_user(user_id, {
            'plan': 'pro',
            'subscription_expires_at': new_expires_at
        })
        return True
