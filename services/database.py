import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import json

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

            # Проверяем подключение
            self.client.admin.command('ping')
            logger.info("Successfully connected to MongoDB")

            # Создаем индексы
            self._create_indexes()

        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    def _create_indexes(self):
        """Создает необходимые индексы"""
        try:
            # Индекс для пользователей
            self.db.users.create_index("user_id", unique=True)
            self.db.users.create_index("created_at")

            # Индексы для транскрипций
            self.db.transcriptions.create_index([("user_id", 1), ("created_at", -1)])
            self.db.transcriptions.create_index("created_at")

            logger.info("Database indexes created successfully")
        except Exception as e:
            logger.warning(f"Failed to create indexes: {e}")

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Получает пользователя по ID

        Args:
            user_id: Facebook user ID

        Returns:
            Данные пользователя или None если не найден
        """
        try:
            user = self.db.users.find_one({"user_id": user_id})
            if user:
                # Сбрасываем дневной счетчик если прошел день
                self._reset_daily_usage_if_needed(user)
                # Обновляем last_seen
                self.db.users.update_one(
                    {"user_id": user_id},
                    {"$set": {"last_seen": datetime.now(timezone.utc)}}
                )
            return user
        except PyMongoError as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None

    def create_user(self, user_id: str, **kwargs) -> Dict[str, Any]:
        """
        Создает нового пользователя

        Args:
            user_id: Facebook user ID
            **kwargs: дополнительные поля пользователя

        Returns:
            Данные созданного пользователя
        """
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
                "preferred_language": "en",
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
        """
        Обновляет данные пользователя

        Args:
            user_id: Facebook user ID
            update_data: данные для обновления

        Returns:
            True если обновление прошло успешно
        """
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

    def increment_usage(self, user_id: str) -> bool:
        """
        Увеличивает счетчик использования для пользователя

        Args:
            user_id: Facebook user ID

        Returns:
            True если обновление прошло успешно
        """
        try:
            today = datetime.now(timezone.utc).date().isoformat()

            result = self.db.users.update_one(
                {"user_id": user_id},
                {
                    "$inc": {
                        "daily_usage": 1,
                        "total_transcriptions": 1
                    },
                    "$set": {
                        "daily_reset_date": today,
                        "last_seen": datetime.now(timezone.utc)
                    }
                }
            )

            logger.info(f"Incremented usage for user {user_id}")
            return result.modified_count > 0

        except PyMongoError as e:
            logger.error(f"Error incrementing usage for user {user_id}: {e}")
            return False

    def save_transcription(self, user_id: str, transcription: str, detected_language: str,
                           file_type: str = "unknown", translation: Optional[str] = None) -> bool:
        """
        Сохраняет результат транскрипции

        Args:
            user_id: Facebook user ID
            transcription: текст транскрипции
            detected_language: определенный язык
            file_type: тип файла (audio/video)
            translation: перевод (если есть)

        Returns:
            True если сохранение прошло успешно
        """
        try:
            transcription_data = {
                "user_id": user_id,
                "transcription": transcription,
                "detected_language": detected_language,
                "file_type": file_type,
                "translation": translation,
                "created_at": datetime.now(timezone.utc),
                "character_count": len(transcription)
            }

            result = self.db.transcriptions.insert_one(transcription_data)

            logger.info(f"Saved transcription for user {user_id}")
            return result.inserted_id is not None

        except PyMongoError as e:
            logger.error(f"Error saving transcription for user {user_id}: {e}")
            return False

    def get_last_transcription(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Получает последнюю транскрипцию пользователя

        Args:
            user_id: Facebook user ID

        Returns:
            Данные последней транскрипции или None
        """
        try:
            transcription = self.db.transcriptions.find_one(
                {"user_id": user_id},
                sort=[("created_at", -1)]
            )
            return transcription
        except PyMongoError as e:
            logger.error(f"Error getting last transcription for user {user_id}: {e}")
            return None

    def get_user_transcriptions(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Получает последние транскрипции пользователя

        Args:
            user_id: Facebook user ID
            limit: максимальное количество записей

        Returns:
            Список транскрипций
        """
        try:
            transcriptions = list(
                self.db.transcriptions.find(
                    {"user_id": user_id}
                ).sort("created_at", -1).limit(limit)
            )
            return transcriptions
        except PyMongoError as e:
            logger.error(f"Error getting transcriptions for user {user_id}: {e}")
            return []

    def get_usage_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Получает статистику использования пользователя

        Args:
            user_id: Facebook user ID

        Returns:
            Словарь со статистикой
        """
        try:
            user = self.get_user(user_id)
            if not user:
                return {}

            # Статистика по языкам
            language_stats = list(
                self.db.transcriptions.aggregate([
                    {"$match": {"user_id": user_id}},
                    {"$group": {
                        "_id": "$detected_language",
                        "count": {"$sum": 1}
                    }},
                    {"$sort": {"count": -1}}
                ])
            )

            # Статистика за последние 30 дней
            thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
            recent_count = self.db.transcriptions.count_documents({
                "user_id": user_id,
                "created_at": {"$gte": thirty_days_ago}
            })

            return {
                "daily_usage": user.get("daily_usage", 0),
                "total_transcriptions": user.get("total_transcriptions", 0),
                "is_premium": user.get("is_premium", False),
                "language_stats": language_stats,
                "recent_30_days": recent_count,
                "created_at": user.get("created_at"),
                "last_seen": user.get("last_seen")
            }

        except PyMongoError as e:
            logger.error(f"Error getting usage stats for user {user_id}: {e}")
            return {}

    def get_global_stats(self) -> Dict[str, Any]:
        """
        Получает глобальную статистику сервиса

        Returns:
            Словарь с глобальной статистикой
        """
        try:
            total_users = self.db.users.count_documents({})
            total_transcriptions = self.db.transcriptions.count_documents({})

            # Активные пользователи за последние 7 дней
            week_ago = datetime.now(timezone.utc) - timedelta(days=7)
            active_users = self.db.users.count_documents({
                "last_seen": {"$gte": week_ago}
            })

            # Статистика по языкам
            language_stats = list(
                self.db.transcriptions.aggregate([
                    {"$group": {
                        "_id": "$detected_language",
                        "count": {"$sum": 1}
                    }},
                    {"$sort": {"count": -1}},
                    {"$limit": 10}
                ])
            )

            return {
                "total_users": total_users,
                "total_transcriptions": total_transcriptions,
                "active_users_7_days": active_users,
                "top_languages": language_stats
            }

        except PyMongoError as e:
            logger.error(f"Error getting global stats: {e}")
            return {}

    def _reset_daily_usage_if_needed(self, user: Dict[str, Any]) -> bool:
        """
        Сбрасывает дневной счетчик если прошел день

        Args:
            user: данные пользователя

        Returns:
            True если счетчик был сброшен
        """
        try:
            today = datetime.now(timezone.utc).date().isoformat()
            last_reset = user.get("daily_reset_date")

            if last_reset != today:
                self.db.users.update_one(
                    {"user_id": user["user_id"]},
                    {
                        "$set": {
                            "daily_usage": 0,
                            "daily_reset_date": today
                        }
                    }
                )
                logger.info(f"Reset daily usage for user {user['user_id']}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error resetting daily usage: {e}")
            return False

    def set_premium_status(self, user_id: str, is_premium: bool) -> bool:
        """
        Устанавливает премиум статус пользователя

        Args:
            user_id: Facebook user ID
            is_premium: премиум статус

        Returns:
            True если обновление прошло успешно
        """
        try:
            result = self.db.users.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "is_premium": is_premium,
                        "premium_updated_at": datetime.now(timezone.utc)
                    }
                }
            )

            logger.info(f"Updated premium status for user {user_id}: {is_premium}")
            return result.modified_count > 0

        except PyMongoError as e:
            logger.error(f"Error updating premium status for user {user_id}: {e}")
            return False

    def cleanup_old_transcriptions(self, days_old: int = 90) -> int:
        """
        Удаляет старые транскрипции

        Args:
            days_old: количество дней после которых удалять записи

        Returns:
            Количество удаленных записей
        """
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)

            result = self.db.transcriptions.delete_many({
                "created_at": {"$lt": cutoff_date}
            })

            deleted_count = result.deleted_count
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old transcriptions")

            return deleted_count

        except PyMongoError as e:
            logger.error(f"Error cleaning up old transcriptions: {e}")
            return 0

    def get_daily_usage_report(self, date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Получает отчет об использовании за день

        Args:
            date: дата для отчета (по умолчанию сегодня)

        Returns:
            Отчет за день
        """
        try:
            if date is None:
                date = datetime.now(timezone.utc)

            start_of_day = datetime.combine(date.date(), datetime.min.time())
            end_of_day = start_of_day + timedelta(days=1)

            # Транскрипции за день
            daily_transcriptions = self.db.transcriptions.count_documents({
                "created_at": {
                    "$gte": start_of_day,
                    "$lt": end_of_day
                }
            })

            # Новые пользователи за день
            new_users = self.db.users.count_documents({
                "created_at": {
                    "$gte": start_of_day,
                    "$lt": end_of_day
                }
            })

            # Активные пользователи за день
            active_users = self.db.users.count_documents({
                "last_seen": {
                    "$gte": start_of_day,
                    "$lt": end_of_day
                }
            })

            return {
                "date": date.date().isoformat(),
                "daily_transcriptions": daily_transcriptions,
                "new_users": new_users,
                "active_users": active_users
            }

        except PyMongoError as e:
            logger.error(f"Error getting daily usage report: {e}")
            return {}

    def close(self):
        """Закрывает соединение с базой данных"""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")

    def store_retry_info(self, user_id: str, retry_data: Dict[str, Any]):
        """Сохраняет информацию для повторной обработки"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO retry_info (user_id, retry_data, created_at)
                VALUES (?, ?, ?)
            """, (user_id, json.dumps(retry_data), datetime.utcnow().isoformat()))

            self.connection.commit()

        except Exception as e:
            logger.error(f"Ошибка при сохранении retry info: {e}")

    def get_retry_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Получает информацию для повторной обработки"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                SELECT retry_data FROM retry_info 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT 1
            """, (user_id,))

            result = cursor.fetchone()
            if result:
                return json.loads(result[0])
            return None

        except Exception as e:
            logger.error(f"Ошибка при получении retry info: {e}")
            return None

    def set_user_language_preference(self, user_id: str, language: str):
        """Устанавливает предпочтение языка для пользователя"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                UPDATE users SET preferred_language = ? WHERE user_id = ?
            """, (language, user_id))

            self.connection.commit()

        except Exception as e:
            logger.error(f"Ошибка при установке языкового предпочтения: {e}")

    def _create_tables(self):
        """Создает необходимые таблицы в базе данных - ОБНОВЛЕННАЯ ВЕРСИЯ"""
        cursor = self.connection.cursor()

        # Таблица пользователей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                daily_usage INTEGER DEFAULT 0,
                total_transcriptions INTEGER DEFAULT 0,
                is_premium BOOLEAN DEFAULT 0,
                preferred_language TEXT DEFAULT NULL,
                target_language TEXT DEFAULT 'en',
                auto_translate BOOLEAN DEFAULT 0,
                created_at TEXT,
                last_reset TEXT
            )
        """)

        # Таблица транскрипций
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transcriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                transcription TEXT,
                detected_language TEXT,
                file_type TEXT,
                created_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)

        # 🔧 НОВАЯ таблица для retry информации
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS retry_info (
                user_id TEXT PRIMARY KEY,
                retry_data TEXT,
                created_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)

        self.connection.commit()