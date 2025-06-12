import os
from datetime import datetime, timedelta
from pymongo import MongoClient
import logging

class Database:
    def __init__(self):
        # Используем MongoDB Atlas (бесплатный тариф)
        mongo_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
        self.client = MongoClient(mongo_uri)
        self.db = self.client['transcribe_bot']
        self.users = self.db['users']
        self.usage = self.db['usage']
        self.subscriptions = self.db['subscriptions']
        
        # Создание индексов
        self.users.create_index('user_id', unique=True)
        self.usage.create_index([('user_id', 1), ('date', 1)])
        self.subscriptions.create_index('user_id')
        
        logging.info("Database connected")
    
    def get_or_create_user(self, user_id):
        """Получить или создать пользователя"""
        user = self.users.find_one({'user_id': user_id})
        
        if not user:
            user = {
                'user_id': user_id,
                'created_at': datetime.utcnow(),
                'subscription_type': 'free',
                'subscription_end': None,
                'total_transcriptions': 0,
                'last_active': datetime.utcnow()
            }
            self.users.insert_one(user)
            logging.info(f"New user created: {user_id}")
        
        return user
    
    def get_daily_usage(self, user_id):
        """Получить количество использований за сегодня"""
        today = datetime.utcnow().date()
        today_start = datetime.combine(today, datetime.min.time())
        today_end = today_start + timedelta(days=1)
        
        count = self.usage.count_documents({
            'user_id': user_id,
            'timestamp': {
                '$gte': today_start,
                '$lt': today_end
            }
        })
        
        return count
    
    def increment_user_usage(self, user_id):
        """Увеличить счетчик использования"""
        # Добавляем запись об использовании
        self.usage.insert_one({
            'user_id': user_id,
            'timestamp': datetime.utcnow()
        })
        
        # Обновляем общий счетчик
        self.users.update_one(
            {'user_id': user_id},
            {
                '$inc': {'total_transcriptions': 1},
                '$set': {'last_active': datetime.utcnow()}
            }
        )
    
    def update_subscription(self, user_id, subscription_type, end_date=None):
        """Обновить подписку пользователя"""
        update_data = {
            'subscription_type': subscription_type,
            'subscription_updated': datetime.utcnow()
        }
        
        if end_date:
            update_data['subscription_end'] = end_date
        
        self.users.update_one(
            {'user_id': user_id},
            {'$set': update_data}
        )
        
        # Сохраняем историю подписок
        self.subscriptions.insert_one({
            'user_id': user_id,
            'type': subscription_type,
            'started_at': datetime.utcnow(),
            'end_date': end_date
        })
    
    def check_subscription_status(self, user_id):
        """Проверить статус подписки"""
        user = self.users.find_one({'user_id': user_id})
        
        if not user:
            return 'free'
        
        if user['subscription_type'] == 'premium' and user.get('subscription_end'):
            if datetime.utcnow() > user['subscription_end']:
                # Подписка истекла
                self.update_subscription(user_id, 'free')
                return 'free'
        
        return user['subscription_type']
    
    def get_user_stats(self):
        """Получить статистику по пользователям"""
        total_users = self.users.count_documents({})
        premium_users = self.users.count_documents({'subscription_type': 'premium'})
        
        # Активные пользователи за последние 7 дней
        week_ago = datetime.utcnow() - timedelta(days=7)
        active_users = self.users.count_documents({
            'last_active': {'$gte': week_ago}
        })
        
        # Общее количество транскрипций
        pipeline = [
            {'$group': {
                '_id': None,
                'total': {'$sum': '$total_transcriptions'}
            }}
        ]
        result = list(self.users.aggregate(pipeline))
        total_transcriptions = result[0]['total'] if result else 0
        
        return {
            'total_users': total_users,
            'premium_users': premium_users,
            'active_users_7d': active_users,
            'total_transcriptions': total_transcriptions
        }
    
    def cleanup_old_usage(self):
        """Очистка старых записей использования (опционально)"""
        # Удаляем записи старше 30 дней
        cutoff_date = datetime.utcnow() - timedelta(days=30)
        self.usage.delete_many({
            'timestamp': {'$lt': cutoff_date}
        })
        
    def export_user_data(self, user_id):
        """Экспорт данных пользователя (для GDPR)"""
        user = self.users.find_one({'user_id': user_id})
        usage_records = list(self.usage.find({'user_id': user_id}))
        subscription_history = list(self.subscriptions.find({'user_id': user_id}))
        
        return {
            'user': user,
            'usage': usage_records,
            'subscriptions': subscription_history
        }
    
    def delete_user_data(self, user_id):
        """Удаление всех данных пользователя"""
        self.users.delete_one({'user_id': user_id})
        self.usage.delete_many({'user_id': user_id})
        self.subscriptions.delete_many({'user_id': user_id})