# services/database.py
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
import logging

class Database:
    # Получаем зависимости в конструкторе
    def __init__(self, mongo_uri: str, db_name: str):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.users = self.db["users"]
        self.notes = self.db["notes"]
        logging.info("Database service initialized.")

    # ... остальной код класса без изменений ...
    def get_user(self, user_id):
        return self.users.find_one({"user_id": user_id})

    def create_user(self, user_id, username):
        user_data = {
            "user_id": user_id,
            "username": username,
            "registration_date": datetime.utcnow(),
            "balance": 0.0,
            "is_premium": False,
        }
        self.users.insert_one(user_data)
        return user_data

    def get_or_create_user(self, user_id, username):
        user = self.get_user(user_id)
        if not user:
            user = self.create_user(user_id, username)
        return user

    def create_note(self, user_id, file_id, file_type, file_unique_id, duration):
        note_data = {
            "user_id": user_id,
            "file_id": file_id,
            "file_type": file_type,
            "file_unique_id": file_unique_id,
            "duration": duration,
            "status": "pending",
            "created_at": datetime.utcnow(),
            "content": None,
            "processing_options": None,
            "s3_path": None,
        }
        result = self.notes.insert_one(note_data)
        return str(result.inserted_id)

    def get_note(self, note_id):
        return self.notes.find_one({"_id": ObjectId(note_id)})

    def update_note(self, note_id, update_data):
        self.notes.update_one({"_id": ObjectId(note_id)}, {"$set": update_data})

    def update_user_balance(self, user_id, amount):
        self.users.update_one({"user_id": user_id}, {"$inc": {"balance": amount}})