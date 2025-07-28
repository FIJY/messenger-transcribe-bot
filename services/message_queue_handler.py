# services/message_queue_handler.py
import os
import logging
import asyncio
import time
from typing import Optional
from telegram import Bot
from bson import ObjectId

logger = logging.getLogger(__name__)


class MessageQueueHandler:
    def __init__(self, bot: Bot, database):
        self.bot = bot
        self.db = database
        self.is_running = False
        self._task: Optional[asyncio.Task] = None

    async def start_processing(self):
        """
        Запускает обработку очереди сообщений
        """
        if self.is_running:
            logger.warning("Message queue processor уже запущен")
            return

        self.is_running = True
        self._task = asyncio.create_task(self._process_queue_loop())
        logger.info("Message queue processor запущен")

    async def stop_processing(self):
        """
        Останавливает обработку очереди
        """
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Message queue processor остановлен")

    async def _process_queue_loop(self):
        """
        Основной цикл обработки очереди
        """
        while self.is_running:
            try:
                await self._process_pending_messages()
                await asyncio.sleep(2)  # Проверяем очередь каждые 2 секунды
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле обработки очереди: {e}", exc_info=True)
                await asyncio.sleep(5)  # Пауза при ошибке

    async def _process_pending_messages(self):
        """
        Обрабатывает ожидающие сообщения из очереди
        """
        try:
            # Получаем сообщения из очереди (сортируем по приоритету и времени)
            messages = list(self.db.db.message_queue.find({
                'status': 'pending',
                'attempts': {'$lt': 3}
            }).sort([('priority', 1), ('created_at', 1)]).limit(10))

            if not messages:
                return

            logger.info(f"Обрабатываем {len(messages)} сообщений из очереди")

            for msg in messages:
                try:
                    # Отправляем сообщение через Telegram Bot
                    await self.bot.send_message(
                        chat_id=msg['chat_id'],
                        text=msg['text'],
                        parse_mode='Markdown'
                    )

                    # Помечаем как отправленное
                    self.db.db.message_queue.update_one(
                        {'_id': msg['_id']},
                        {'$set': {'status': 'sent', 'sent_at': time.time()}}
                    )

                    logger.info(f"Сообщение {msg['_id']} отправлено в чат {msg['chat_id']}")

                    # Небольшая задержка между сообщениями (лимиты Telegram)
                    await asyncio.sleep(0.5)

                except Exception as e:
                    # Увеличиваем счетчик попыток
                    self.db.db.message_queue.update_one(
                        {'_id': msg['_id']},
                        {'$inc': {'attempts': 1}, '$set': {'last_error': str(e)}}
                    )
                    logger.error(f"Ошибка отправки сообщения {msg['_id']}: {e}")

                    # Если ошибка связана с rate limiting, делаем паузу
                    if "too many requests" in str(e).lower():
                        logger.warning("Rate limit от Telegram, делаем паузу 30 секунд")
                        await asyncio.sleep(30)
                        break

            # Очистка старых сообщений
            await self._cleanup_old_messages()

        except Exception as e:
            logger.error(f"Ошибка в _process_pending_messages: {e}", exc_info=True)

    async def _cleanup_old_messages(self):
        """
        Удаляет старые сообщения из очереди
        """
        try:
            cutoff_time = time.time() - 3600  # 1 час назад

            # Удаляем старые отправленные сообщения
            result = self.db.db.message_queue.delete_many({
                'status': 'sent',
                'sent_at': {'$lt': cutoff_time}
            })

            if result.deleted_count > 0:
                logger.info(f"Удалено {result.deleted_count} старых отправленных сообщений")

            # Помечаем как failed сообщения с 3+ попытками
            result = self.db.db.message_queue.update_many(
                {'attempts': {'$gte': 3}, 'status': 'pending'},
                {'$set': {'status': 'failed', 'failed_at': time.time()}}
            )

            if result.modified_count > 0:
                logger.warning(f"Помечено как failed {result.modified_count} сообщений")

        except Exception as e:
            logger.error(f"Ошибка очистки очереди: {e}")

    async def queue_message(self, chat_id: int, text: str, priority: int = 5):
        """
        Добавляет сообщение в очередь
        """
        try:
            # Обрезаем слишком длинные сообщения
            if len(text) > 4000:
                text = text[:3990] + "\n\n[Сообщение обрезано]"

            message_doc = {
                'chat_id': chat_id,
                'text': text,
                'priority': priority,
                'status': 'pending',
                'created_at': time.time(),
                'attempts': 0
            }

            result = self.db.db.message_queue.insert_one(message_doc)
            logger.info(f"Сообщение добавлено в очередь: {result.inserted_id}")
            return True

        except Exception as e:
            logger.error(f"Ошибка добавления сообщения в очередь: {e}")
            return False

    def get_queue_stats(self):
        """
        Возвращает статистику очереди
        """
        try:
            stats = {
                'pending': self.db.db.message_queue.count_documents({'status': 'pending'}),
                'sent': self.db.db.message_queue.count_documents({'status': 'sent'}),
                'failed': self.db.db.message_queue.count_documents({'status': 'failed'}),
                'total': self.db.db.message_queue.count_documents({})
            }
            return stats
        except Exception as e:
            logger.error(f"Ошибка получения статистики очереди: {e}")
            return None