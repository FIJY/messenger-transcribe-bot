# services/promo_service.py - Новый сервис для промокодов
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from config import settings, SUBSCRIPTION_PLANS

logger = logging.getLogger(__name__)


class PromoCodeService:
    """Сервис для работы с промокодами"""

    def __init__(self, db_service):
        self.db = db_service.db
        # Предустановленные коды
        self.default_codes = {
            "ADMIN500": {
                "plan": "pro",
                "minutes": 500,
                "uses_limit": 1,
                "expires_at": None,  # Никогда не истекает
                "description": "Админский код на 500 минут PRO",
                "auto_create": True
            },
            "WELCOME100": {
                "plan": "starter",
                "minutes": 100,
                "uses_limit": 10,
                "expires_at": datetime.utcnow() + timedelta(days=30),
                "description": "Приветственный код на 100 минут",
                "auto_create": True
            },
            'YOUTUBE': {
                'minutes': 30,
                'plan': 'trial',
                'description': '🎬 Тестовые минуты для YouTube',
                'max_uses': 1000,
                'active': True
            },
            "TEST50": {
                "plan": "trial",
                "minutes": 50,
                "uses_limit": 100,
                "expires_at": datetime.utcnow() + timedelta(days=7),
                "description": "Тестовый код на 50 минут",
                "auto_create": True
            }
        }

    async def initialize(self):
        """Инициализация - создаем предустановленные коды"""
        try:
            # Создаем индекс для промокодов
            await self.db.promo_codes.create_index("code", unique=True)
            await self.db.promo_codes.create_index("expires_at")

            # Создаем предустановленные коды
            for code, info in self.default_codes.items():
                if info.get("auto_create"):
                    await self._create_default_code(code, info)

            logger.info("✅ PromoCodeService инициализирован")

        except Exception as e:
            logger.error(f"Ошибка инициализации PromoCodeService: {e}")

    async def _create_default_code(self, code: str, info: Dict):
        """Создает предустановленный код если его еще нет"""
        try:
            existing = await self.db.promo_codes.find_one({"code": code})
            if not existing:
                promo_data = {
                    "code": code,
                    "plan": info["plan"],
                    "minutes": info["minutes"],
                    "uses_limit": info["uses_limit"],
                    "uses_count": 0,
                    "expires_at": info["expires_at"],
                    "description": info["description"],
                    "created_at": datetime.utcnow(),
                    "is_active": True,
                    "is_default": True
                }

                await self.db.promo_codes.insert_one(promo_data)
                logger.info(f"🎫 Создан промокод: {code}")

        except Exception as e:
            logger.warning(f"Не удалось создать код {code}: {e}")

    async def use_promo_code(self, user_id: int, code: str) -> Dict[str, Any]:
        """Использование промокода пользователем"""
        try:
            # Приводим код к верхнему регистру
            code = code.upper().strip()

            # Проверяем существование кода
            promo = await self.db.promo_codes.find_one({
                "code": code,
                "is_active": True
            })

            if not promo:
                return {
                    "success": False,
                    "error": "❌ Промокод не найден или неактивен"
                }

            # Проверяем срок действия
            if promo.get("expires_at") and promo["expires_at"] < datetime.utcnow():
                return {
                    "success": False,
                    "error": "❌ Промокод истек"
                }

            # Проверяем лимит использований
            if promo["uses_count"] >= promo["uses_limit"]:
                return {
                    "success": False,
                    "error": "❌ Промокод исчерпан"
                }

            # Проверяем не использовал ли уже этот пользователь данный код
            usage = await self.db.promo_usage.find_one({
                "user_id": user_id,
                "code": code
            })

            if usage:
                return {
                    "success": False,
                    "error": "❌ Вы уже использовали этот промокод"
                }

            # Применяем промокод к пользователю
            from services.database import DatabaseService
            db_service = DatabaseService()
            db_service.db = self.db

            # Получаем текущий баланс пользователя
            user = await db_service.get_user_by_telegram_id(user_id)
            if not user:
                return {
                    "success": False,
                    "error": "❌ Пользователь не найден"
                }

            current_balance = user.get("balance_minutes", 0)
            new_balance = current_balance + promo["minutes"]

            # Обновляем пользователя
            update_data = {
                "balance_minutes": new_balance,
                "plan": promo["plan"],
                "last_activity": datetime.utcnow()
            }

            # Если план платный - устанавливаем срок действия
            if promo["plan"] != "trial":
                update_data["subscription_expires"] = datetime.utcnow() + timedelta(days=30)

            await db_service.update_user(user_id, update_data)

            # Записываем использование промокода
            await self.db.promo_usage.insert_one({
                "user_id": user_id,
                "code": code,
                "used_at": datetime.utcnow(),
                "minutes_added": promo["minutes"],
                "plan_set": promo["plan"]
            })

            # Увеличиваем счетчик использований
            await self.db.promo_codes.update_one(
                {"code": code},
                {"$inc": {"uses_count": 1}}
            )

            plan_info = SUBSCRIPTION_PLANS.get(promo["plan"], {})
            plan_name = plan_info.get("name", promo["plan"])

            logger.info(f"✅ Промокод {code} активирован пользователем {user_id}")

            return {
                "success": True,
                "message": f"✅ Промокод активирован!",
                "details": {
                    "minutes_added": promo["minutes"],
                    "new_balance": new_balance,
                    "plan": plan_name,
                    "description": promo.get("description", "")
                }
            }

        except Exception as e:
            logger.error(f"Ошибка использования промокода {code}: {e}")
            return {
                "success": False,
                "error": "❌ Ошибка активации промокода"
            }

    async def create_promo_code(self, code: str, plan: str, minutes: int,
                                uses_limit: int = 1, expires_days: int = 30,
                                description: str = "") -> Dict[str, Any]:
        """Создание нового промокода (для админов)"""
        try:
            code = code.upper().strip()

            # Проверяем что код не существует
            existing = await self.db.promo_codes.find_one({"code": code})
            if existing:
                return {
                    "success": False,
                    "error": f"Промокод {code} уже существует"
                }

            expires_at = datetime.utcnow() + timedelta(days=expires_days) if expires_days > 0 else None

            promo_data = {
                "code": code,
                "plan": plan,
                "minutes": minutes,
                "uses_limit": uses_limit,
                "uses_count": 0,
                "expires_at": expires_at,
                "description": description,
                "created_at": datetime.utcnow(),
                "is_active": True,
                "is_default": False
            }

            await self.db.promo_codes.insert_one(promo_data)

            return {
                "success": True,
                "message": f"✅ Промокод {code} создан",
                "code": code
            }

        except Exception as e:
            logger.error(f"Ошибка создания промокода: {e}")
            return {
                "success": False,
                "error": "Ошибка создания промокода"
            }

    async def get_promo_stats(self, code: str) -> Dict[str, Any]:
        """Получение статистики по промокоду"""
        try:
            promo = await self.db.promo_codes.find_one({"code": code.upper()})
            if not promo:
                return {"success": False, "error": "Промокод не найден"}

            # Получаем список использований
            usages = await self.db.promo_usage.find({"code": code.upper()}).to_list(100)

            return {
                "success": True,
                "code": promo["code"],
                "description": promo.get("description", ""),
                "plan": promo["plan"],
                "minutes": promo["minutes"],
                "uses_count": promo["uses_count"],
                "uses_limit": promo["uses_limit"],
                "expires_at": promo.get("expires_at"),
                "is_active": promo["is_active"],
                "recent_uses": [
                    {
                        "user_id": usage["user_id"],
                        "used_at": usage["used_at"],
                        "minutes_added": usage["minutes_added"]
                    }
                    for usage in usages[-5:]  # Последние 5 использований
                ]
            }

        except Exception as e:
            logger.error(f"Ошибка получения статистики промокода: {e}")
            return {"success": False, "error": "Ошибка получения статистики"}