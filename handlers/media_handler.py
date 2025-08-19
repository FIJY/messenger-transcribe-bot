# handlers/media_handler.py - ИСПРАВЛЕННАЯ версия с посекундной тарификацией
import logging
import base64
import tempfile
import os
import uuid
from typing import Dict, Any, Optional

from services.telegram_client import TelegramClient
from ui.localization import LocalizationService

logger = logging.getLogger(__name__)


class MediaHandler:
    """
    Обработчик медиа файлов с ПОСЕКУНДНОЙ тарификацией:
    - ТРАНСКРИПЦИЯ = платно (по секундам)
    - ОБРАБОТКА ТЕКСТА = бесплатно
    """

    def __init__(self,
                 telegram: TelegramClient,
                 localization: LocalizationService):
        self.telegram = telegram
        self.localization = localization
        # Лимит для Redis Starter - файлы больше 15MB идут через файловую систему
        self.redis_size_limit_mb = 15

    def _extract_file_info(self, message: Dict[str, Any]) -> Optional[Dict]:
        """Извлечение информации о файле с правильными расширениями."""
        for media_type in ['audio', 'voice', 'video', 'video_note', 'document']:
            if media_type in message:
                media_obj = message[media_type]

                original_filename = media_obj.get('file_name', '')

                if original_filename and '.' in original_filename:
                    file_extension = original_filename.split('.')[-1].lower()
                else:
                    extension_map = {
                        'voice': 'oga',
                        'audio': 'mp3',
                        'video': 'mp4',
                        'video_note': 'mp4',
                        'document': 'mp3'
                    }
                    file_extension = extension_map.get(media_type, 'oga')

                logger.info(f"Определено расширение для {media_type}: .{file_extension}")

                return {
                    'file_id': media_obj['file_id'],
                    'file_unique_id': media_obj['file_unique_id'],
                    'file_size': media_obj.get('file_size', 0),
                    'duration': media_obj.get('duration', 0),
                    'file_name': original_filename or f"{media_type}.{file_extension}",
                    'media_type': media_type,
                    'original_extension': file_extension
                }
        return None

    async def handle(self, message: Dict[str, Any], user: Dict[str, Any]):
        """Главная обработка с ПОСЕКУНДНОЙ тарификацией"""
        chat_id = message['chat']['id']
        lang = user.get('language', 'ru')

        file_info = self._extract_file_info(message)
        if not file_info:
            logger.warning(f"Не удалось извлечь file_info из сообщения")
            return

        file_size_mb = file_info.get('file_size', 0) / (1024 * 1024)
        duration_seconds = file_info.get('duration', 0)

        # Проверяем лимит на размер файла (2GB = 2048MB)
        if file_size_mb > 2048:
            await self.telegram.send_message(
                chat_id,
                f"❌ Файл слишком большой ({file_size_mb:.1f}MB). Максимум: 2GB"
            )
            return

        # ИСПРАВЛЕННАЯ ЛОГИКА: ПОСЕКУНДНАЯ тарификация
        user_balance_minutes = user.get('balance_minutes', 0)
        user_balance_seconds = user_balance_minutes * 60  # Переводим минуты в секунды

        # Минимум 3 секунды за любой файл
        transcription_cost_seconds = max(3, duration_seconds)
        transcription_cost_minutes = transcription_cost_seconds / 60

        logger.info(f"Размер файла: {file_size_mb:.1f}MB, длительность: {duration_seconds}с")
        logger.info(f"Стоимость ТРАНСКРИПЦИИ: {transcription_cost_seconds}с ({transcription_cost_minutes:.2f} мин)")
        logger.info(f"Баланс пользователя: {user_balance_seconds}с ({user_balance_minutes:.2f} мин)")

        # Проверяем баланс ДЛЯ ТРАНСКРИПЦИИ (в секундах)
        if user_balance_seconds < transcription_cost_seconds:
            await self._send_insufficient_balance_message(
                chat_id, transcription_cost_seconds, user_balance_seconds, duration_seconds
            )
            return

        try:
            # ОБНОВЛЕННОЕ уведомление с посекундной тарификацией
            if transcription_cost_minutes < 1.0:
                cost_display = f"{transcription_cost_seconds}с"
            else:
                cost_display = f"{transcription_cost_minutes:.1f} мин"

            pricing_message = f"""✅ Файл получен ({self._format_duration(duration_seconds)})

💰 ТРАНСКРИПЦИЯ: {cost_display} (платно)
✨ ОБРАБОТКА: бесплатна!

💳 Ваш баланс: {user_balance_minutes:.1f} мин
🔄 Начинаю транскрипцию..."""

            await self.telegram.send_message(chat_id, pricing_message)

            # Скачиваем файл
            local_file_path = await self.telegram.download_file(file_info['file_id'])
            if not local_file_path:
                raise IOError("Не удалось скачать файл с серверов Telegram.")

            logger.info(f"Файл скачан: {local_file_path}")

            # Выбираем стратегию обработки
            if file_size_mb <= self.redis_size_limit_mb:
                await self._handle_small_file_via_redis(chat_id, user, local_file_path, file_info)
            else:
                await self._handle_large_file_via_filesystem(chat_id, user, local_file_path, file_info)

        except Exception as e:
            logger.error(f"Ошибка при обработке файла для {user['telegram_id']}: {e}", exc_info=True)
            error_text = "❌ Произошла ошибка при обработке файла. Попробуйте еще раз."
            await self.telegram.send_message(chat_id, error_text)

    async def _send_insufficient_balance_message(self, chat_id: int, required_seconds: int,
                                                 current_balance_seconds: int, file_duration: int):
        """Отправка сообщения о недостатке баланса с посекундной тарификацией"""
        from ui.keyboards import create_insufficient_balance_keyboard

        # Форматирование для отображения
        if required_seconds < 60:
            required_display = f"{required_seconds}с"
        else:
            required_display = f"{required_seconds / 60:.1f} мин"

        if current_balance_seconds < 60:
            balance_display = f"{current_balance_seconds:.0f}с"
        else:
            balance_display = f"{current_balance_seconds / 60:.1f} мин"

        shortage_seconds = required_seconds - current_balance_seconds
        if shortage_seconds < 60:
            shortage_display = f"{shortage_seconds:.0f}с"
        else:
            shortage_display = f"{shortage_seconds / 60:.1f} мин"

        message = f"""⚠️ Недостаточно баланса для ТРАНСКРИПЦИИ

🎵 Длительность файла: {self._format_duration(file_duration)}
💰 Нужно: {required_display}
💳 У вас: {balance_display}
📉 Не хватает: {shortage_display}

✨ Зато ОБРАБОТКА текста всегда бесплатна!
💎 Купите минуты только для транскрипции:"""

        # Рассчитываем сколько минут нужно минимально купить
        required_minutes = max(1, shortage_seconds // 60 + 1)
        keyboard = create_insufficient_balance_keyboard(required_minutes)
        await self.telegram.send_message(chat_id, message, reply_markup=keyboard)

    async def _handle_small_file_via_redis(self, chat_id: int, user: dict, local_file_path: str, file_info: dict):
        """Обработка маленьких файлов через Redis"""
        from services.transcription import process_transcription_task

        try:
            with open(local_file_path, 'rb') as f:
                file_content = f.read()

            file_content_b64 = base64.b64encode(file_content).decode('utf-8')
            file_size_mb = len(file_content) / (1024 * 1024)
            logger.info(f"Маленький файл ({file_size_mb:.1f}MB) → Redis base64")

            # Удаляем временный файл
            os.remove(local_file_path)

            # Передаем через Redis
            enhanced_file_info = {**file_info, 'file_content_b64': file_content_b64}
            process_transcription_task.delay(chat_id, user['telegram_id'], enhanced_file_info)

            logger.info(f"Задача для маленького файла отправлена через Redis")

        except Exception as e:
            logger.error(f"Ошибка обработки маленького файла: {e}")
            if os.path.exists(local_file_path):
                os.remove(local_file_path)
            raise

    async def _handle_large_file_via_filesystem(self, chat_id: int, user: dict, local_file_path: str, file_info: dict):
        """Обработка больших файлов через файловую систему"""
        from services.transcription import process_large_file_task

        try:
            # Создаем общую директорию для больших файлов
            shared_dir = "/tmp/shared_large_files"
            os.makedirs(shared_dir, exist_ok=True)

            # Создаем уникальное имя файла
            file_extension = file_info.get('original_extension', 'mp4')
            unique_filename = f"large_{uuid.uuid4().hex}.{file_extension}"
            shared_file_path = os.path.join(shared_dir, unique_filename)

            # Перемещаем файл в общую директорию
            os.rename(local_file_path, shared_file_path)
            file_size_mb = os.path.getsize(shared_file_path) / (1024 * 1024)
            logger.info(f"Большой файл ({file_size_mb:.1f}MB) перемещен: {shared_file_path}")

            # Передаем метаданные
            enhanced_file_info = {
                **file_info,
                'shared_file_path': shared_file_path,
                'is_large_file': True,
                'processing_method': 'filesystem'
            }

            # Используем специальную задачу для больших файлов
            process_large_file_task.delay(chat_id, user['telegram_id'], enhanced_file_info)

            logger.info(f"Задача для большого файла отправлена: {shared_file_path}")

        except Exception as e:
            logger.error(f"Ошибка обработки большого файла: {e}")
            # Очищаем файлы при ошибке
            if os.path.exists(local_file_path):
                os.remove(local_file_path)
            if 'shared_file_path' in locals() and os.path.exists(shared_file_path):
                os.remove(shared_file_path)
            raise

    def _format_duration(self, seconds: int) -> str:
        """Форматирование длительности"""
        if seconds < 60:
            return f"{seconds}с"
        elif seconds < 3600:
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            if remaining_seconds > 0:
                return f"{minutes}м {remaining_seconds}с"
            return f"{minutes}м"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            if minutes > 0:
                return f"{hours}ч {minutes}м"
            return f"{hours}ч"