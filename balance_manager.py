# balance_manager.py - Быстрое управление балансом пользователей
import asyncio
import sys
import os
from datetime import datetime

# Добавляем путь к проекту
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

try:
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv

    load_dotenv()

    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
    DATABASE_NAME = os.getenv('DATABASE_NAME', 'transcribe_bot_db')

except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("💡 Установите: pip install motor python-dotenv")
    sys.exit(1)


class BalanceManager:
    """Простой менеджер баланса пользователей"""

    def __init__(self):
        self.client = None
        self.db = None

    async def initialize(self):
        """Подключение к БД"""
        self.client = AsyncIOMotorClient(MONGODB_URI)
        self.db = self.client[DATABASE_NAME]
        await self.client.admin.command('ping')
        print("✅ Подключение к БД установлено")

    async def close(self):
        """Закрытие подключения"""
        if self.client:
            self.client.close()

    async def find_user(self, telegram_id: int = None, username: str = None):
        """Поиск пользователя по ID или username"""
        if telegram_id:
            user = await self.db.users.find_one({"telegram_id": telegram_id})
        elif username:
            user = await self.db.users.find_one({"username": {"$regex": username, "$options": "i"}})
        else:
            return None

        if user:
            balance = user.get('balance_minutes', 0)
            plan = user.get('plan', 'trial')
            created = user.get('created_at', 'unknown')

            print(f"\n👤 Пользователь найден:")
            print(f"  🆔 Telegram ID: {user.get('telegram_id')}")
            print(f"  👤 Имя: {user.get('username', 'не указано')}")
            print(f"  💰 Баланс: {balance} минут")
            print(f"  📋 План: {plan}")
            print(f"  📅 Создан: {created}")

        return user

    async def add_balance(self, telegram_id: int, minutes: int, plan: str = None):
        """Добавление баланса пользователю"""
        user = await self.find_user(telegram_id)
        if not user:
            print(f"❌ Пользователь с ID {telegram_id} не найден")
            return False

        current_balance = user.get('balance_minutes', 0)
        new_balance = current_balance + minutes

        update_data = {
            "balance_minutes": new_balance,
            "last_activity": datetime.utcnow()
        }

        if plan:
            update_data["plan"] = plan
            update_data["subscription_expires"] = datetime.utcnow()
            print(f"📋 План обновлен на: {plan}")

        result = await self.db.users.update_one(
            {"telegram_id": telegram_id},
            {"$set": update_data}
        )

        if result.modified_count > 0:
            print(f"✅ Баланс обновлен:")
            print(f"  Было: {current_balance} минут")
            print(f"  Добавлено: +{minutes} минут")
            print(f"  Стало: {new_balance} минут")
            return True
        else:
            print("❌ Не удалось обновить баланс")
            return False

    async def set_balance(self, telegram_id: int, minutes: int, plan: str = None):
        """Установка точного баланса"""
        user = await self.find_user(telegram_id)
        if not user:
            print(f"❌ Пользователь с ID {telegram_id} не найден")
            return False

        current_balance = user.get('balance_minutes', 0)

        update_data = {
            "balance_minutes": minutes,
            "last_activity": datetime.utcnow()
        }

        if plan:
            update_data["plan"] = plan

        result = await self.db.users.update_one(
            {"telegram_id": telegram_id},
            {"$set": update_data}
        )

        if result.modified_count > 0:
            print(f"✅ Баланс установлен:")
            print(f"  Было: {current_balance} минут")
            print(f"  Установлено: {minutes} минут")
            if plan:
                print(f"  План: {plan}")
            return True
        else:
            print("❌ Не удалось установить баланс")
            return False

    async def list_users(self, limit: int = 10):
        """Показать список пользователей"""
        print(f"\n👥 Последние {limit} пользователей:")
        print("-" * 80)

        users = await self.db.users.find({}).sort("last_activity", -1).limit(limit).to_list(limit)

        for user in users:
            telegram_id = user.get('telegram_id')
            username = user.get('username', 'без имени')
            balance = user.get('balance_minutes', 0)
            plan = user.get('plan', 'trial')
            last_activity = user.get('last_activity', 'никогда')

            print(f"🆔 {telegram_id:<12} | 👤 {username:<15} | 💰 {balance:>5} мин | 📋 {plan:<8} | 📅 {last_activity}")

    async def give_trial_to_all(self, minutes: int = 60):
        """Дать минуты всем пользователям с нулевым балансом"""
        result = await self.db.users.update_many(
            {"balance_minutes": {"$lte": 0}},
            {
                "$set": {
                    "balance_minutes": minutes,
                    "plan": "trial",
                    "last_activity": datetime.utcnow()
                }
            }
        )

        print(f"✅ Дано {minutes} минут {result.modified_count} пользователям")
        return result.modified_count


async def main():
    """Главная функция - интерактивное меню"""
    manager = BalanceManager()

    try:
        await manager.initialize()

        while True:
            print("\n" + "=" * 60)
            print("💰 УПРАВЛЕНИЕ БАЛАНСОМ ПОЛЬЗОВАТЕЛЕЙ")
            print("=" * 60)
            print("1. 🔍 Найти пользователя по ID")
            print("2. 👤 Найти пользователя по имени")
            print("3. ➕ Добавить баланс")
            print("4. 📝 Установить точный баланс")
            print("5. 📋 Изменить план")
            print("6. 👥 Показать всех пользователей")
            print("7. 🎁 Дать триал всем (60 мин)")
            print("8. ⚡ БЫСТРО: дать себе 500 минут")
            print("0. 🚪 Выход")
            print("-" * 60)

            choice = input("Выберите действие (0-8): ").strip()

            if choice == "0":
                break

            elif choice == "1":
                telegram_id = input("Введите Telegram ID: ").strip()
                try:
                    await manager.find_user(int(telegram_id))
                except ValueError:
                    print("❌ Некорректный ID")

            elif choice == "2":
                username = input("Введите имя пользователя: ").strip()
                await manager.find_user(username=username)

            elif choice == "3":
                try:
                    telegram_id = int(input("Telegram ID: ").strip())
                    minutes = int(input("Добавить минут: ").strip())
                    plan = input("Новый план (enter=без изменений): ").strip() or None
                    await manager.add_balance(telegram_id, minutes, plan)
                except ValueError:
                    print("❌ Некорректные данные")

            elif choice == "4":
                try:
                    telegram_id = int(input("Telegram ID: ").strip())
                    minutes = int(input("Установить баланс (минут): ").strip())
                    plan = input("План (trial/starter/work/pro): ").strip() or None
                    await manager.set_balance(telegram_id, minutes, plan)
                except ValueError:
                    print("❌ Некорректные данные")

            elif choice == "5":
                try:
                    telegram_id = int(input("Telegram ID: ").strip())
                    print("Доступные планы: trial, starter, work, pro")
                    plan = input("Новый план: ").strip()
                    if plan in ["trial", "starter", "work", "pro"]:
                        await manager.set_balance(telegram_id, None, plan)
                    else:
                        print("❌ Неизвестный план")
                except ValueError:
                    print("❌ Некорректный ID")

            elif choice == "6":
                limit = input("Показать пользователей (по умолчанию 10): ").strip()
                try:
                    limit = int(limit) if limit else 10
                    await manager.list_users(limit)
                except ValueError:
                    await manager.list_users(10)

            elif choice == "7":
                confirm = input("Дать 60 минут ВСЕМ пользователям с нулевым балансом? (y/N): ")
                if confirm.lower() in ['y', 'yes', 'да']:
                    await manager.give_trial_to_all(60)
                else:
                    print("❌ Отменено")

            elif choice == "8":
                print("⚡ БЫСТРАЯ АКТИВАЦИЯ")
                print("Поищите свой Telegram ID в списке пользователей...")
                await manager.list_users(20)

                telegram_id = input("\nВведите ваш Telegram ID: ").strip()
                try:
                    telegram_id = int(telegram_id)
                    await manager.set_balance(telegram_id, 500, "pro")
                    print("🎉 Готово! У вас 500 минут и план PRO!")
                except ValueError:
                    print("❌ Некорректный ID")
            else:
                print("❌ Неизвестная команда")

    except KeyboardInterrupt:
        print("\n👋 До свидания!")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        await manager.close()


if __name__ == "__main__":
    print("🚀 Запуск менеджера баланса...")
    asyncio.run(main())