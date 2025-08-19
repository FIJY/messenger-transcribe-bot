# fix_balance_simple.py - упрощенный скрипт без celery зависимостей
import asyncio
import sys
import os
from datetime import datetime

# Добавляем путь к проекту
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

try:
    # Простой импорт только необходимого
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv

    # Загружаем переменные окружения
    load_dotenv()

    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
    DATABASE_NAME = os.getenv('DATABASE_NAME', 'transcribe_bot_db')

except ImportError as e:
    print(f"Ошибка импорта: {e}")
    print("Установите зависимости: pip install motor python-dotenv")
    sys.exit(1)


class SimpleDatabase:
    """Упрощенный класс для работы с БД без лишних зависимостей"""

    def __init__(self):
        self.client = None
        self.db = None

    async def initialize(self):
        self.client = AsyncIOMotorClient(MONGODB_URI)
        self.db = self.client[DATABASE_NAME]

        # Проверяем подключение
        await self.client.admin.command('ping')

    async def close(self):
        if self.client:
            self.client.close()


async def fix_users_balance():
    """Дает 15 минут всем пользователям с нулевым балансом"""
    print("🔧 Начинаю исправление баланса пользователей...")

    try:
        db = SimpleDatabase()
        await db.initialize()
        print("✅ Подключение к БД установлено")

        # Считаем сколько пользователей с нулевым балансом
        zero_balance_count = await db.db.users.count_documents({"balance_minutes": {"$lte": 0}})
        print(f"📊 Найдено пользователей с нулевым балансом: {zero_balance_count}")

        # Считаем всех пользователей
        total_users = await db.db.users.count_documents({})
        print(f"👥 Всего пользователей в системе: {total_users}")

        if zero_balance_count == 0:
            print("✨ Все пользователи уже имеют положительный баланс!")
            await db.close()
            return

        # Показываем примеры пользователей с нулевым балансом
        print("\n👤 ПРИМЕРЫ ПОЛЬЗОВАТЕЛЕЙ С НУЛЕВЫМ БАЛАНСОМ:")
        sample_users = await db.db.users.find({"balance_minutes": {"$lte": 0}}).limit(3).to_list(3)
        for user in sample_users:
            user_id = user.get('telegram_id', 'unknown')
            balance = user.get('balance_minutes', 0)
            plan = user.get('plan', 'unknown')
            created = user.get('created_at', 'unknown')
            print(f"  ID: {user_id}, Баланс: {balance} мин, План: {plan}, Создан: {created}")

        # Обновляем баланс
        print(f"\n🔄 Обновляю баланс для {zero_balance_count} пользователей...")

        result = await db.db.users.update_many(
            {"balance_minutes": {"$lte": 0}},
            {
                "$set": {
                    "balance_minutes": 15.0,  # 15 минут триал баланса
                    "plan": "trial",
                    "last_activity": datetime.utcnow()
                }
            }
        )

        print(f"🎁 Успешно обновлен баланс для {result.modified_count} пользователей")
        print("💰 Каждый получил 15.0 минут триал баланса")

        # Проверяем результат
        remaining_zero = await db.db.users.count_documents({"balance_minutes": {"$lte": 0}})
        positive_balance = await db.db.users.count_documents({"balance_minutes": {"$gt": 0}})

        print(f"\n📊 РЕЗУЛЬТАТ:")
        print(f"✅ Пользователей с положительным балансом: {positive_balance}")
        print(f"❌ Пользователей с нулевым балансом осталось: {remaining_zero}")

        # Показываем примеры обновленных пользователей
        if result.modified_count > 0:
            print("\n👤 ПРИМЕРЫ ОБНОВЛЕННЫХ ПОЛЬЗОВАТЕЛЕЙ:")
            updated_users = await db.db.users.find({"balance_minutes": 15.0}).limit(3).to_list(3)
            for user in updated_users:
                user_id = user.get('telegram_id', 'unknown')
                balance = user.get('balance_minutes', 0)
                plan = user.get('plan', 'unknown')
                print(f"  ID: {user_id}, Баланс: {balance} мин, План: {plan}")

        await db.close()
        print("\n✅ Исправление завершено успешно!")

    except Exception as e:
        print(f"❌ Ошибка при исправлении баланса: {e}")
        import traceback
        traceback.print_exc()


async def show_users_stats():
    """Показывает статистику пользователей"""
    try:
        db = SimpleDatabase()
        await db.initialize()

        total_users = await db.db.users.count_documents({})
        zero_balance = await db.db.users.count_documents({"balance_minutes": {"$lte": 0}})
        positive_balance = await db.db.users.count_documents({"balance_minutes": {"$gt": 0}})

        # Статистика по планам
        trial_users = await db.db.users.count_documents({"plan": "trial"})
        starter_users = await db.db.users.count_documents({"plan": "starter"})

        print("\n📊 СТАТИСТИКА ПОЛЬЗОВАТЕЛЕЙ:")
        print(f"👥 Всего пользователей: {total_users}")
        print(f"💳 С положительным балансом: {positive_balance}")
        print(f"💸 С нулевым балансом: {zero_balance}")
        print(f"🆓 На триал плане: {trial_users}")
        print(f"💰 На платных планах: {starter_users}")

        # Показываем распределение баланса
        if total_users > 0:
            print(f"\n📈 ПРОЦЕНТНОЕ СООТНОШЕНИЕ:")
            print(f"✅ Готовы к работе: {positive_balance / total_users * 100:.1f}%")
            print(f"❌ Нужно пополнение: {zero_balance / total_users * 100:.1f}%")

        # Показываем несколько примеров
        print("\n👤 ПРИМЕРЫ ПОЛЬЗОВАТЕЛЕЙ:")
        users_sample = await db.db.users.find({}).limit(5).to_list(5)
        for user in users_sample:
            balance = user.get('balance_minutes', 0)
            plan = user.get('plan', 'неизвестно')
            user_id = user.get('telegram_id', 'unknown')
            print(f"  ID: {user_id}, Баланс: {balance:.1f} мин, План: {plan}")

        await db.close()

    except Exception as e:
        print(f"❌ Ошибка получения статистики: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("🚀 Упрощенный скрипт исправления баланса пользователей")
    print("=" * 60)

    # Проверяем подключение к БД
    try:
        # Сначала показываем статистику
        asyncio.run(show_users_stats())

        # Спрашиваем подтверждение
        answer = input("\n❓ Хотите исправить баланс для всех пользователей с нулевым балансом? (y/N): ")

        if answer.lower() in ['y', 'yes', 'да', 'д']:
            asyncio.run(fix_users_balance())
            print("\n" + "=" * 60)
            # Показываем статистику после исправления
            asyncio.run(show_users_stats())
        else:
            print("❌ Операция отменена")

    except KeyboardInterrupt:
        print("\n❌ Операция прервана пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        print("🔧 Убедитесь что:")
        print("  1. MongoDB запущен")
        print("  2. Файл .env содержит правильный MONGODB_URI")
        print("  3. Установлены зависимости: pip install motor python-dotenv")