# database.py - ПОЛНАЯ ИСПРАВЛЕННАЯ ВЕРСИЯ
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
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
        """Подключение к MongoDB"""
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
        """Создает необходимые индексы"""
        try:
            self.db.users.create_index("user_id", unique=True)
            self.db.transcriptions.create_index([("user_id", 1), ("created_at", -1)])
            self.db.retry_info.create_index("user_id", unique=True)
            logger.info("Database indexes created/verified successfully")
        except Exception as e:
            logger.warning(f"Failed to create indexes: {e}")

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Получает пользователя по ID"""
        try:
            user = self.db.users.find_one({"user_id": user_id})
            if user:
                self._reset_daily_usage_if_needed(user)
                self.db.users.update_one(
                    {"user_id": user_id},
                    {"$set": {"last_seen": datetime.now(timezone.utc)}}
                )
            return user
        except PyMongoError as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None

    def create_user(self, user_id: str, **kwargs) -> Dict[str, Any]:
        """Создает нового пользователя"""
        try:
            now = datetime.now(timezone.utc)
            user_data = {
                "user_id": user_id,
                "created_at": now,
                "last_seen": now,
                "daily_usage": 0,
                "daily_reset_date": now.date().isoformat(),
                "total_transcriptions": 0,
                "is_premium": False,
                "preferred_language": None,
                "target_language": "en",
                "auto_translate": False,
                **kwargs
            }
            result = self.db.users.insert_one(user_data)
            user_data["_id"] = result.inserted_id
            logger.info(f"Created new user: {user_id}")
            return user_data
        except PyMongoError as e:
            logger.error(f"Error creating user {user_id}: {e}")
            raise

    def update_user(self, user_id: str, update_data: Dict[str, Any]) -> bool:
        """Обновляет данные пользователя"""
        try:
            update_data["last_seen"] = datetime.now(timezone.utc)
            result = self.db.users.update_one(
                {"user_id": user_id},
                {"$set": update_data}
            )
            return result.modified_count > 0
        except PyMongoError as e:
            logger.error(f"Error updating user {user_id}: {e}")
            return False

    def increment_usage(self, user_id: str):
        """Увеличивает счетчик использования для пользователя"""
        try:
            today = datetime.now(timezone.utc).date().isoformat()
            self.db.users.update_one(
                {"user_id": user_id},
                {
                    "$inc": {"daily_usage": 1, "total_transcriptions": 1},
                    "$set": {"daily_reset_date": today, "last_seen": datetime.now(timezone.utc)}
                }
            )
            logger.info(f"Incremented usage for user {user_id}")
        except PyMongoError as e:
            logger.error(f"Error incrementing usage for user {user_id}: {e}")

    def save_transcription(self, user_id: str, **kwargs):
        """Сохраняет результат транскрипции"""
        try:
            data = {"user_id": user_id, "created_at": datetime.now(timezone.utc), **kwargs}
            del data['success'] # Не храним поле success в БД
            self.db.transcriptions.insert_one(data)
            logger.info(f"Saved transcription for user {user_id}")
        except PyMongoError as e:
            logger.error(f"Error saving transcription for user {user_id}: {e}")

    def get_last_transcription(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Получает последнюю транскрипцию пользователя"""
        try:
            return self.db.transcriptions.find_one(
                {"user_id": user_id},
                sort=[("created_at", -1)]
            )
        except PyMongoError as e:
            logger.error(f"Error getting last transcription for user {user_id}: {e}")
            return None

    def _reset_daily_usage_if_needed(self, user: Dict[str, Any]):
        """Сбрасывает дневной счетчик если прошел день"""
        try:
            today = datetime.now(timezone.utc).date().isoformat()
            last_reset = user.get("daily_reset_date")
            if last_reset != today:
                self.db.users.update_one(
                    {"user_id": user["user_id"]},
                    {"$set": {"daily_usage": 0, "daily_reset_date": today}}
                )
                logger.info(f"Reset daily usage for user {user['user_id']}")
        except Exception as e:
            logger.error(f"Error resetting daily usage: {e}")

    def set_user_language_preference(self, user_id: str, language: Optional[str]) -> bool:
        """Устанавливает или сбрасывает предпочтительный язык для пользователя."""
        logger.info(f"Setting language preference for user {user_id} to: {language}")
        return self.update_user(user_id, {"preferred_language": language})

    def store_retry_info(self, user_id: str, retry_data: Dict[str, Any]):
        """Сохраняет информацию для повторной обработки в коллекцию retry_info."""
        try:
            self.db.retry_info.update_one(
                {'user_id': user_id},
                {'$set': {**retry_data, 'created_at': datetime.now(timezone.utc)}},
                upsert=True
            )
            logger.info(f"Stored retry info for user {user_id}")
        except PyMongoError as e:
            logger.error(f"Ошибка при сохранении retry info: {e}")

    def get_retry_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Получает информацию для повторной обработки."""
        try:
            return self.db.retry_info.find_one({'user_id': user_id})
        except PyMongoError as e:
            logger.error(f"Ошибка при получении retry info: {e}")
            return None

    def close(self):
        """Закрывает соединение с базой данных"""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")