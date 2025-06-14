import os
import logging
from datetime import datetime, timedelta
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        """Инициализация подключения к MongoDB"""
        try:
            mongodb_uri = os.getenv('MONGODB_URI')
            if not mongodb_uri:
                raise ValueError("MONGODB_URI environment variable is not set")

            self.client = MongoClient(
                mongodb_uri,
                serverSelectionTimeoutMS=5000,  # 5 second timeout
                connectTimeoutMS=5000,
                maxPoolSize=10
            )

            # Тест подключения
            self.client.admin.command('ping')
            logger.info("Database connected successfully")

            self.db = self.client.transcribe_bot
            self.users = self.db.users
            self.transcriptions = self.db.transcriptions
            self.payments = self.db.payments

            # Создание индексов
            self._create_indexes()

        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            raise

    def _create_indexes(self):
        """Создание индексов для оптимизации запросов"""
        try:
            # Индекс для пользователей
            self.users.create_index("user_id", unique=True)

            # Индексы для транскрипций
            self.transcriptions.create_index([("user_id", 1), ("created_at", -1)])
            self.transcriptions.create_index("created_at")

            # Индексы для платежей
            self.payments.create_index("user_id")
            self.payments.create_index("transaction_id", unique=True)

            logger.info("Database indexes created successfully")

        except Exception as e:
            logger.warning(f"Failed to create indexes: {e}")

    def get_or_create_user(self, user_id):
        """Получить или создать пользователя"""
        try:
            user = self.users.find_one({"user_id": user_id})

            if not user:
                # Создание нового пользователя
                user_data = {
                    "user_id": user_id,
                    "subscription_type": "free",
                    "created_at": datetime.utcnow(),
                    "total_transcriptions": 0,
                    "subscription_expires": None
                }

                self.users.insert_one(user_data)
                logger.info(f"Created new user: {user_id}")
                return user_data

            return user

        except Exception as e:
            logger.error(f"Error getting/creating user {user_id}: {e}")
            # Возвращаем пользователя по умолчанию в случае ошибки
            return {
                "user_id": user_id,
                "subscription_type": "free",
                "total_transcriptions": 0
            }

    def get_daily_usage(self, user_id):
        """Получить количество транскрипций за сегодня"""
        try:
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = today_start + timedelta(days=1)

            count = self.transcriptions.count_documents({
                "user_id": user_id,
                "created_at": {
                    "$gte": today_start,
                    "$lt": today_end
                }
            })

            return count

        except Exception as e:
            logger.error(f"Error getting daily usage for {user_id}: {e}")
            return 0

    def increment_user_usage(self, user_id):
        """Увеличить счетчик использования пользователя"""
        try:
            # Обновляем общий счетчик
            self.users.update_one(
                {"user_id": user_id},
                {
                    "$inc": {"total_transcriptions": 1},
                    "$set": {"last_activity": datetime.utcnow()}
                }
            )

            # Записываем транскрипцию
            transcription_record = {
                "user_id": user_id,
                "created_at": datetime.utcnow(),
                "type": "audio_transcription"
            }

            self.transcriptions.insert_one(transcription_record)
            logger.info(f"Incremented usage for user {user_id}")

        except Exception as e:
            logger.error(f"Error incrementing usage for {user_id}: {e}")

    def update_subscription(self, user_id, subscription_type, expires_at=None):
        """Обновить подписку пользователя"""
        try:
            update_data = {
                "subscription_type": subscription_type,
                "subscription_updated": datetime.utcnow()
            }

            if expires_at:
                update_data["subscription_expires"] = expires_at

            result = self.users.update_one(
                {"user_id": user_id},
                {"$set": update_data}
            )

            if result.modified_count > 0:
                logger.info(f"Updated subscription for user {user_id}: {subscription_type}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error updating subscription for {user_id}: {e}")
            return False

    def record_payment(self, user_id, transaction_id, amount, currency="USD"):
        """Записать платеж"""
        try:
            payment_record = {
                "user_id": user_id,
                "transaction_id": transaction_id,
                "amount": amount,
                "currency": currency,
                "status": "completed",
                "created_at": datetime.utcnow()
            }

            self.payments.insert_one(payment_record)
            logger.info(f"Recorded payment for user {user_id}: {amount} {currency}")

        except Exception as e:
            logger.error(f"Error recording payment for {user_id}: {e}")

    def get_user_stats(self, user_id):
        """Получить статистику пользователя"""
        try:
            user = self.get_or_create_user(user_id)
            daily_usage = self.get_daily_usage(user_id)

            # Статистика за последние 30 дней
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            monthly_usage = self.transcriptions.count_documents({
                "user_id": user_id,
                "created_at": {"$gte": thirty_days_ago}
            })

            return {
                "subscription_type": user.get("subscription_type", "free"),
                "total_transcriptions": user.get("total_transcriptions", 0),
                "daily_usage": daily_usage,
                "monthly_usage": monthly_usage,
                "created_at": user.get("created_at"),
                "subscription_expires": user.get("subscription_expires")
            }

        except Exception as e:
            logger.error(f"Error getting stats for {user_id}: {e}")
            return None

    def cleanup_old_records(self, days=90):
        """Очистка старых записей (для экономии места)"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            # Удаляем старые транскрипции
            result = self.transcriptions.delete_many({
                "created_at": {"$lt": cutoff_date}
            })

            logger.info(f"Cleaned up {result.deleted_count} old transcription records")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def get_bot_statistics(self):
        """Получить общую статистику бота"""
        try:
            total_users = self.users.count_documents({})
            premium_users = self.users.count_documents({"subscription_type": "premium"})

            # Активные пользователи за последние 7 дней
            week_ago = datetime.utcnow() - timedelta(days=7)
            active_users = self.users.count_documents({
                "last_activity": {"$gte": week_ago}
            })

            total_transcriptions = self.transcriptions.count_documents({})

            return {
                "total_users": total_users,
                "premium_users": premium_users,
                "active_users_week": active_users,
                "total_transcriptions": total_transcriptions
            }

        except Exception as e:
            logger.error(f"Error getting bot statistics: {e}")
            return None