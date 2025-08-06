# services/database.py - Сервис работы с базой данных
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import asyncio

from config_del import settings

logger = logging.getLogger(__name__)


class DatabaseService:
    """Асинхронный сервис для работы с MongoDB"""

    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None

    async def initialize(self):
        """Инициализация подключения к базе данных"""
        try:
            self.client = AsyncIOMotorClient(settings.MONGODB_URI)
            self.db = self.client[settings.DATABASE_NAME]

            # Проверяем подключение
            await self.client.admin.command('ping')

            # Создаем индексы
            await self._create_indexes()

            logger.info("✅ База данных инициализирована успешно")

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации БД: {e}", exc_info=True)
            raise

    async def close(self):
        """Закрытие подключения к базе данных"""
        if self.client:
            self.client.close()
            logger.info("✅ Подключение к БД закрыто")

    async def _create_indexes(self):
        """Создание индексов для оптимизации запросов"""
        # Индексы для пользователей
        await self.db.users.create_index("telegram_id", unique=True)
        await self.db.users.create_index("created_at")

        # Индексы для аудио файлов
        await self.db.audio_files.create_index("user_id")
        await self.db.audio_files.create_index("created_at")
        await self.db.audio_files.create_index("status")

        # Индексы для транскрипций
        await self.db.transcriptions.create_index("audio_file_id")
        await self.db.transcriptions.create_index("user_id")
        await self.db.transcriptions.create_index("created_at")

        logger.info("✅ Индексы БД созданы")

    # === ПОЛЬЗОВАТЕЛИ ===

    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Получение пользователя по Telegram ID"""
        user = await self.db.users.find_one({"telegram_id": telegram_id})
        if user:
            user['_id'] = str(user['_id'])
        return user

    async def create_user(self, telegram_id: int, username: Optional[str] = None,
                          language_code: str = "ru") -> Dict[str, Any]:
        """Создание нового пользователя"""
        user_data = {
            "telegram_id": telegram_id,
            "username": username,
            "language": language_code,
            "plan": "free",
            "balance_minutes": 0,
            "created_at": datetime.utcnow(),
            "last_activity": datetime.utcnow(),
            "settings": {
                "notifications": True,
                "auto_export": False
            }
        }

        result = await self.db.users.insert_one(user_data)
        user_data['_id'] = str(result.inserted_id)

        logger.info(f"👤 Создан новый пользователь: {telegram_id}")
        return user_data

    async def get_or_create_user(self, telegram_id: int, username: Optional[str] = None,
                                 language_code: str = "ru") -> Dict[str, Any]:
        """Получение существующего пользователя или создание нового"""
        user = await self.get_user_by_telegram_id(telegram_id)

        if not user:
            user = await self.create_user(telegram_id, username, language_code)
        else:
            # Обновляем последнюю активность
            await self.update_user(telegram_id, {"last_activity": datetime.utcnow()})

        return user

    async def update_user(self, telegram_id: int, update_data: Dict[str, Any]) -> bool:
        """Обновление данных пользователя"""
        result = await self.db.users.update_one(
            {"telegram_id": telegram_id},
            {"$set": update_data}
        )
        return result.modified_count > 0

    async def get_user_usage_current_month(self, telegram_id: int) -> int:
        """Получение использованных минут в текущем месяце"""
        # Начало текущего месяца
        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)

        # Агрегация использованных минут
        pipeline = [
            {
                "$match": {
                    "user_id": telegram_id,
                    "created_at": {"$gte": month_start},
                    "status": "completed"
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_seconds": {"$sum": "$duration_seconds"}
                }
            }
        ]

        result = await self.db.audio_files.aggregate(pipeline).to_list(1)

        if result:
            total_seconds = result[0]["total_seconds"]
            return int(total_seconds / 60)  # Конвертируем в минуты

        return 0

    # === АУДИО ФАЙЛЫ ===

    async def create_audio_file(self, user_id: int, telegram_file_id: str, file_type: str,
                                duration_seconds: int, file_size_mb: float) -> Dict[str, Any]:
        """Создание записи об аудио файле"""
        audio_file_data = {
            "user_id": user_id,
            "telegram_file_id": telegram_file_id,
            "file_type": file_type,
            "duration_seconds": duration_seconds,
            "file_size_mb": file_size_mb,
            "status": "pending",
            "s3_path": None,
            "processing_options": [],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        result = await self.db.audio_files.insert_one(audio_file_data)
        audio_file_data['_id'] = str(result.inserted_id)
        audio_file_data['id'] = str(result.inserted_id)

        logger.info(f"🎵 Создан аудио файл: {result.inserted_id}")
        return audio_file_data

    async def get_audio_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Получение аудио файла по ID"""
        try:
            audio_file = await self.db.audio_files.find_one({"_id": ObjectId(file_id)})
            if audio_file:
                audio_file['_id'] = str(audio_file['_id'])
                audio_file['id'] = str(audio_file['_id'])
            return audio_file
        except Exception as e:
            logger.error(f"Ошибка получения аудио файла {file_id}: {e}")
            return None

    async def update_audio_file(self, file_id: str, update_data: Dict[str, Any]) -> bool:
        """Обновление данных аудио файла"""
        try:
            update_data["updated_at"] = datetime.utcnow()
            result = await self.db.audio_files.update_one(
                {"_id": ObjectId(file_id)},
                {"$set": update_data}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Ошибка обновления аудио файла {file_id}: {e}")
            return False

    async def get_user_audio_files(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Получение аудио файлов пользователя"""
        cursor = self.db.audio_files.find(
            {"user_id": user_id}
        ).sort("created_at", -1).limit(limit)

        files = []
        async for file_doc in cursor:
            file_doc['_id'] = str(file_doc['_id'])
            file_doc['id'] = str(file_doc['_id'])
            files.append(file_doc)

        return files

    # === ТРАНСКРИПЦИИ ===

    async def create_transcription(self, audio_file_id: str, user_id: int,
                                   text: str, language: str, confidence: float = None) -> Dict[str, Any]:
        """Создание записи транскрипции"""
        transcription_data = {
            "audio_file_id": audio_file_id,
            "user_id": user_id,
            "text": text,
            "language": language,
            "confidence": confidence,
            "processing_results": {},
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        result = await self.db.transcriptions.insert_one(transcription_data)
        transcription_data['_id'] = str(result.inserted_id)
        transcription_data['id'] = str(result.inserted_id)

        logger.info(f"📝 Создана транскрипция: {result.inserted_id}")
        return transcription_data

    async def get_transcription_by_audio_file(self, audio_file_id: str) -> Optional[Dict[str, Any]]:
        """Получение транскрипции по ID аудио файла"""
        transcription = await self.db.transcriptions.find_one({"audio_file_id": audio_file_id})
        if transcription:
            transcription['_id'] = str(transcription['_id'])
            transcription['id'] = str(transcription['_id'])
        return transcription

    async def update_transcription_results(self, transcription_id: str,
                                           processing_results: Dict[str, Any]) -> bool:
        """Обновление результатов обработки транскрипции"""
        try:
            result = await self.db.transcriptions.update_one(
                {"_id": ObjectId(transcription_id)},
                {
                    "$set": {
                        "processing_results": processing_results,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Ошибка обновления результатов транскрипции {transcription_id}: {e}")
            return False

    async def get_transcription(self, transcription_id: str) -> Optional[Dict[str, Any]]:
        """Получение транскрипции по ID"""
        try:
            transcription = await self.db.transcriptions.find_one({"_id": ObjectId(transcription_id)})
            if transcription:
                transcription['_id'] = str(transcription['_id'])
                transcription['id'] = str(transcription['_id'])
            return transcription
        except Exception as e:
            logger.error(f"Ошибка получения транскрипции {transcription_id}: {e}")
            return None

    # === СТАТИСТИКА ===

    async def get_user_statistics(self, user_id: int) -> Dict[str, Any]:
        """Получение статистики пользователя"""
        # Общее количество файлов
        total_files = await self.db.audio_files.count_documents({"user_id": user_id})

        # Количество завершенных обработок
        completed_files = await self.db.audio_files.count_documents({
            "user_id": user_id,
            "status": "completed"
        })

        # Общее время обработанных файлов
        pipeline = [
            {
                "$match": {
                    "user_id": user_id,
                    "status": "completed"
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_seconds": {"$sum": "$duration_seconds"}
                }
            }
        ]

        result = await self.db.audio_files.aggregate(pipeline).to_list(1)
        total_seconds = result[0]["total_seconds"] if result else 0

        return {
            "total_files": total_files,
            "completed_files": completed_files,
            "total_minutes": int(total_seconds / 60),
            "total_hours": round(total_seconds / 3600, 1)
        }

    # === ПОИСК ===

    async def search_user_transcriptions(self, user_id: int, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Поиск по транскрипциям пользователя"""
        # Простой текстовый поиск (можно улучшить с помощью text indexes)
        cursor = self.db.transcriptions.find({
            "user_id": user_id,
            "text": {"$regex": query, "$options": "i"}
        }).sort("created_at", -1).limit(limit)

        results = []
        async for transcription in cursor:
            transcription['_id'] = str(transcription['_id'])
            results.append(transcription)

        return results

    # === АДМИНИСТРИРОВАНИЕ ===

    async def get_system_statistics(self) -> Dict[str, Any]:
        """Получение системной статистики (для админов)"""
        total_users = await self.db.users.count_documents({})
        total_files = await self.db.audio_files.count_documents({})
        total_transcriptions = await self.db.transcriptions.count_documents({})

        # Активные пользователи за последние 7 дней
        week_ago = datetime.utcnow() - timedelta(days=7)
        active_users = await self.db.users.count_documents({
            "last_activity": {"$gte": week_ago}
        })

        return {
            "total_users": total_users,
            "active_users_week": active_users,
            "total_files": total_files,
            "total_transcriptions": total_transcriptions
        }

    async def cleanup_old_files(self, days: int = 30) -> int:
        """Очистка старых файлов (задача для cron)"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Удаляем старые аудио файлы
        result = await self.db.audio_files.delete_many({
            "created_at": {"$lt": cutoff_date},
            "status": {"$in": ["completed", "failed"]}
        })

        deleted_count = result.deleted_count
        logger.info(f"🧹 Удалено {deleted_count} старых файлов")

        return deleted_count