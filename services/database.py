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
        """
        Получение или создание пользователя

        Args:
            user_id: ID пользователя из Messenger

        Returns:
            dict: Документ пользователя
        """
        try:
            user = self.users.find_one({"user_id": user_id})

            if not user:
                user = {
                    "user_id": user_id,
                    "created_at": datetime.utcnow(),
                    "subscription_type": "free",
                    "subscription_expires": None,
                    "total_transcriptions": 0,
                    "last_activity": datetime.utcnow()
                }
                self.users.insert_one(user)
                logger.info(f"Created new user: {user_id}")
            else:
                # Обновляем последнюю активность
                self.users.update_one(
                    {"user_id": user_id},
                    {"$set": {"last_activity": datetime.utcnow()}}
                )

            return user

        except Exception as e:
            logger.error(f"Error in get_or_create_user: {e}")
            return None

    def get_daily_usage(self, user_id):
        """
        Получение количества транскрипций пользователя за сегодня

        Args:
            user_id: ID пользователя

        Returns:
            int: Количество транскрипций
        """
        try:
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

            count = self.transcriptions.count_documents({
                "user_id": user_id,
                "created_at": {"$gte": today_start}
            })

            return count

        except Exception as e:
            logger.error(f"Error in get_daily_usage: {e}")
            return 0

    def increment_user_usage(self, user_id):
        """
        Увеличение счетчика использования

        Args:
            user_id: ID пользователя
        """
        try:
            self.users.update_one(
                {"user_id": user_id},
                {
                    "$inc": {"total_transcriptions": 1},
                    "$set": {"last_activity": datetime.utcnow()}
                }
            )
            logger.info(f"Incremented usage for user {user_id}")

        except Exception as e:
            logger.error(f"Error in increment_user_usage: {e}")

    def update_subscription(self, user_id, subscription_type, expires_at=None):
        """
        Обновление подписки пользователя

        Args:
            user_id: ID пользователя
            subscription_type: Тип подписки ('free' или 'premium')
            expires_at: Дата окончания подписки
        """
        try:
            update_data = {
                "subscription_type": subscription_type,
                "subscription_updated": datetime.utcnow()
            }

            if expires_at:
                update_data["subscription_expires"] = expires_at

            self.users.update_one(
                {"user_id": user_id},
                {"$set": update_data}
            )

            logger.info(f"Updated subscription for user {user_id} to {subscription_type}")

        except Exception as e:
            logger.error(f"Error in update_subscription: {e}")

    def record_payment(self, user_id, transaction_id, amount, currency="USD"):
        """
        Запись платежа

        Args:
            user_id: ID пользователя
            transaction_id: ID транзакции
            amount: Сумма платежа
            currency: Валюта
        """
        try:
            payment = {
                "user_id": user_id,
                "transaction_id": transaction_id,
                "amount": amount,
                "currency": currency,
                "created_at": datetime.utcnow(),
                "status": "completed"
            }

            self.payments.insert_one(payment)
            logger.info(f"Recorded payment for user {user_id}: {amount} {currency}")

        except Exception as e:
            logger.error(f"Error in record_payment: {e}")

    def get_user_stats(self, user_id):
        """
        Получение статистики пользователя

        Args:
            user_id: ID пользователя

        Returns:
            dict: Статистика использования
        """
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
                "total_transcriptions": user.get("total_transcriptions", 0),
                "daily_usage": daily_usage,
                "monthly_usage": monthly_usage,
                "subscription_type": user.get("subscription_type", "free"),
                "member_since": user.get("created_at", datetime.utcnow())
            }

        except Exception as e:
            logger.error(f"Error in get_user_stats: {e}")
            return {}

    def cleanup_old_records(self, days=90):
        """
        Очистка старых записей

        Args:
            days: Количество дней для хранения
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            # Удаляем старые транскрипции
            result = self.transcriptions.delete_many({
                "created_at": {"$lt": cutoff_date}
            })

            logger.info(f"Deleted {result.deleted_count} old transcriptions")

        except Exception as e:
            logger.error(f"Error in cleanup_old_records: {e}")

    def get_bot_statistics(self):
        """
        Получение общей статистики бота

        Returns:
            dict: Общая статистика
        """
        try:
            total_users = self.users.count_documents({})
            total_transcriptions = self.transcriptions.count_documents({})

            # Активные пользователи за последние 7 дней
            week_ago = datetime.utcnow() - timedelta(days=7)
            active_users = self.users.count_documents({
                "last_activity": {"$gte": week_ago}
            })

            # Премиум пользователи
            premium_users = self.users.count_documents({
                "subscription_type": "premium"
            })

            return {
                "total_users": total_users,
                "active_users_week": active_users,
                "premium_users": premium_users,
                "total_transcriptions": total_transcriptions
            }

        except Exception as e:
            logger.error(f"Error in get_bot_statistics: {e}")
            return {}

    def save_transcription(self, user_id, media_type, media_url, transcription,
                           translation=None, language=None, duration_seconds=0):
        """
        Сохранение транскрипции в базу данных

        Args:
            user_id: ID пользователя
            media_type: Тип медиа ('audio' или 'video')
            media_url: URL исходного файла
            transcription: Текст транскрипции
            translation: Текст перевода (опционально)
            language: Определенный язык
            duration_seconds: Длительность в секундах

        Returns:
            str: ID созданной записи
        """
        try:
            transcription_doc = {
                "user_id": user_id,
                "media_type": media_type,
                "media_url": media_url,
                "transcription": transcription,
                "translation": translation,
                "language": language,
                "duration_seconds": duration_seconds,
                "created_at": datetime.utcnow()
            }

            result = self.transcriptions.insert_one(transcription_doc)
            logger.info(f"Saved transcription for user {user_id}")

            return str(result.inserted_id)

        except Exception as e:
            logger.error(f"Failed to save transcription: {e}")
            return None

    def update_transcription_translation(self, transcription_id, translation):
        """
        Обновление перевода для существующей транскрипции

        Args:
            transcription_id: ID транскрипции
            translation: Текст перевода

        Returns:
            bool: Успешность операции
        """
        try:
            from bson import ObjectId

            result = self.transcriptions.update_one(
                {"_id": ObjectId(transcription_id)},
                {"$set": {
                    "translation": translation,
                    "translated_at": datetime.utcnow()
                }}
            )

            return result.modified_count > 0

        except Exception as e:
            logger.error(f"Failed to update translation: {e}")
            return False

    def get_active_users_today(self):
        """
        Получение количества активных пользователей за сегодня

        Returns:
            int: Количество активных пользователей
        """
        try:
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

            active_users = self.transcriptions.distinct(
                "user_id",
                {"created_at": {"$gte": today_start}}
            )

            return len(active_users)

        except Exception as e:
            logger.error(f"Failed to get active users: {e}")
            return 0

    def check_connection(self):
        """
        Проверка соединения с базой данных

        Returns:
            bool: True если соединение активно
        """
        try:
            self.client.admin.command('ping')
            return True
        except Exception:
            return False