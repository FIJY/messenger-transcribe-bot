# handlers/text_handler.py - Исправленная версия
import logging
import os
from typing import Dict, Any, Optional

from services.telegram_client import TelegramClient
from services.database import DatabaseService
from ui.localization import LocalizationService

# Импортируем YouTube сервис
try:
    from services.smart_video_service import (
        SmartVideoService, SmartVideoError, SubtitleNotFoundError,
        DownloadError, YouTubeBlockedError
    )

    YOUTUBE_AVAILABLE = True
except ImportError:
    YOUTUBE_AVAILABLE = False
    SmartVideoService = None
    SmartVideoError = Exception
    SubtitleNotFoundError = Exception
    DownloadError = Exception
    YouTubeBlockedError = Exception

logger = logging.getLogger(__name__)


class TextHandler:
    """Обработчик текстовых сообщений с поддержкой YouTube видео"""

    def __init__(self,
                 telegram: TelegramClient,
                 db: DatabaseService,
                 localization: LocalizationService):
        self.telegram = telegram
        self.db = db
        self.localization = localization

        # Инициализируем YouTube сервис
        if YOUTUBE_AVAILABLE:
            try:
                self.smart_video_service = SmartVideoService()
                capabilities = self.smart_video_service.get_capabilities()
                logger.info(f"✅ YouTube сервис инициализирован: {capabilities}")
            except Exception as e:
                logger.warning(f"❌ YouTube сервис недоступен: {e}")
                self.smart_video_service = None
        else:
            logger.warning("❌ YouTube сервис не импортирован (установите: pip install youtube-transcript-api yt-dlp)")
            self.smart_video_service = None

    async def handle(self, message: Dict[str, Any], user: Dict[str, Any]):
        """Обработка текстовых сообщений"""
        chat_id = message['chat']['id']
        text = message.get('text', '').strip()

        if not text:
            return

        logger.info(f"📨 Текст от пользователя {user.get('telegram_id')}: {text[:100]}...")

        # Проверяем YouTube ссылки
        if self.smart_video_service and self.smart_video_service.is_youtube_url(text):
            await self._handle_youtube_video(chat_id, user, text)
            return

        # Обычный текст - показываем подсказку
        await self._handle_regular_text(chat_id, user, text)

    async def _handle_youtube_video(self, chat_id: int, user: dict, url: str):
        """Обработка YouTube видео с новым методом"""

        status_message = await self.telegram.send_message(
            chat_id,
            "🎬 Обрабатываю YouTube видео через Tor...\n⏳ Это может занять 30-60 секунд"
        )

        try:
            # Получаем информацию о видео
            video_info = await self.smart_video_service.get_video_info(url)
            video_id = video_info.get('video_id', 'unknown')

            # Обновляем статус
            await self.telegram.edit_message_text(
                chat_id,
                status_message['message_id'],
                f"🎬 YouTube видео найдено!\n\n"
                f"🆔 ID: {video_id}\n"
                f"📄 Скачиваю аудио для транскрипции..."
            )

            # Используем исправленный метод
            result = await self.smart_video_service.enhanced_download_youtube_content(url)

            if result and result.get('success'):
                # Обрабатываем успешный результат
                await self._handle_enhanced_result(
                    chat_id, user, status_message['message_id'],
                    result, url
                )
            else:
                # Обработка ошибок
                await self._handle_enhanced_error(
                    chat_id, status_message['message_id'], result, video_id
                )

        except Exception as e:
            logger.error(f"❌ Ошибка обработки YouTube: {e}", exc_info=True)
            await self.telegram.edit_message_text(
                chat_id,
                status_message['message_id'],
                f"❌ Ошибка при обработке видео\n"
                f"🔧 Техническая информация: {str(e)[:200]}"
            )

    async def _handle_enhanced_result(self, chat_id: int, user: dict, message_id: int,
                                      result: dict, url: str):
        """Обработка результата из enhanced_download_youtube_content"""

        video_id = result.get('video_id', 'unknown')
        content_type = result.get('content_type', 'unknown')
        content = result.get('content')  # Это локальный путь к файлу

        if content_type == 'audio_file':
            # У нас есть аудиофайл для транскрипции
            await self._handle_audio_result_fixed(
                chat_id, user, message_id,
                content, result, url
            )
        else:
            # Неизвестный тип контента
            await self.telegram.edit_message_text(
                chat_id, message_id,
                f"❌ Неизвестный тип контента: {content_type}\n"
                f"🎬 Видео: {video_id}"
            )

    async def _handle_enhanced_error(self, chat_id: int, message_id: int,
                                     result: dict, video_id: str):
        """Обработка ошибок из enhanced_download_youtube_content"""

        error_type = result.get('error_type', 'Unknown')
        error_msg = result.get('error', 'Неизвестная ошибка')

        if error_type == 'YouTubeBlockedError':
            await self.telegram.edit_message_text(
                chat_id, message_id,
                f"🚫 YouTube заблокировал загрузку\n\n"
                f"🎬 Видео: {video_id}\n"
                f"❌ Причина: {error_msg}\n\n"
                f"💡 **Что попробовать:**\n"
                f"• Подождать несколько минут и попробовать снова\n"
                f"• Использовать VPN\n"
                f"• Отправить аудиофайл напрямую\n"
                f"• Попробовать другое видео"
            )
        else:
            await self.telegram.edit_message_text(
                chat_id, message_id,
                f"❌ Ошибка обработки видео:\n{error_msg}\n\n"
                f"💡 Попробуйте другую ссылку или отправьте аудиофайл напрямую"
            )

    async def _handle_audio_result_fixed(self, chat_id: int, user: dict, message_id: int,
                                         audio_path: str, result: dict, url: str):
        """ИСПРАВЛЕННАЯ обработка аудио результата"""

        video_id = result.get('video_id', 'unknown')

        # ИСПРАВЛЕНИЕ: Определяем, что у нас - локальный файл
        try:
            file_size = os.path.getsize(audio_path)
            file_size_mb = file_size / (1024 * 1024)

            # Получаем длительность из метаданных видео
            video_info = result.get('video_info', {})
            duration_seconds = video_info.get('duration', 0)

            logger.info(f"📊 Размер файла: {file_size} байт ({file_size_mb:.2f} МБ)")
            logger.info(f"⏱️ Длительность: {duration_seconds} секунд")

        except OSError as e:
            logger.error(f"Не удалось получить размер локального файла {audio_path}: {e}")
            await self.telegram.edit_message_text(
                chat_id, message_id,
                f"❌ Ошибка доступа к загруженному файлу\n\n"
                f"🎬 Видео: {video_id}\n"
                f"Попробуйте еще раз"
            )
            return

        # Если размер 0 - используем оценку
        if not file_size or file_size <= 0:
            duration_seconds = result.get('video_info', {}).get('duration', 180)  # 3 минуты
            file_size = duration_seconds * 16 * 1024  # 16KB/сек для MP3 128kbps
            file_size_mb = file_size / (1024 * 1024)
            logger.warning(f"⚠️ Используем оценочный размер: {file_size} байт")

        # Примерная оценка стоимости
        estimated_cost_seconds = max(3, duration_seconds)

        # Проверяем баланс
        user_balance_minutes = user.get('balance_minutes', 0)
        user_balance_seconds = user_balance_minutes * 60

        if user_balance_seconds < estimated_cost_seconds:
            await self.telegram.edit_message_text(
                chat_id, message_id,
                f"💰 Недостаточно баланса для транскрипции\n\n"
                f"🎬 YouTube видео: {video_id}\n"
                f"📁 Размер: {file_size_mb:.1f} МБ\n"
                f"💳 Нужно: ~{estimated_cost_seconds / 60:.1f} мин\n"
                f"💰 У вас: {user_balance_minutes:.1f} мин\n\n"
                f"Купите минуты: /subscription"
            )
            # Очищаем локальный файл
            self.smart_video_service.cleanup_temp_files(audio_path)
            return

        # Обновляем статус с ПРАВИЛЬНЫМ размером
        status_text = f"🔥 Аудио загружено из YouTube!\n\n"
        status_text += f"🎬 Видео: {video_id}\n"
        status_text += f"📁 {file_size_mb:.1f} МБ\n"

        if duration_seconds > 0:
            status_text += f"⏱️ ~{duration_seconds // 60}:{duration_seconds % 60:02d}\n"

        status_text += f"💰 Примерная стоимость: {estimated_cost_seconds / 60:.1f} мин\n"

        if result.get('title'):
            status_text += f"🎭 {result['title'][:50]}...\n"

        metadata = result.get('metadata', {})
        if metadata.get('current_ip'):
            status_text += f"🌐 IP: {metadata['current_ip']}\n"

        status_text += f"\n🔄 Передаю в систему транскрипции..."

        await self.telegram.edit_message_text(
            chat_id, message_id, status_text
        )

        try:
            # Создаем file_info с ПРАВИЛЬНЫМИ данными
            file_info = {
                'file_id': f'youtube_{video_id}',
                'file_unique_id': f'yt_{video_id}',
                'file_size': file_size,  # Теперь гарантированно > 0
                'duration': duration_seconds,
                'file_name': f'YouTube_{video_id}.mp3',
                'media_type': 'youtube_audio',
                'original_extension': 'mp3',
                'source': 'youtube_audio',
                'original_url': url,
                'video_id': video_id,
                'title': result.get('title'),
                'method': metadata.get('method'),
                'ip_used': metadata.get('current_ip')
            }

            logger.info(f"📦 Отправляем в транскрипцию: размер={file_size}, длительность={duration_seconds}")

            # Определяем способ обработки
            if file_size_mb <= 15:
                # Небольшой файл - через Redis
                import base64
                with open(audio_path, 'rb') as f:
                    file_content = f.read()
                file_content_b64 = base64.b64encode(file_content).decode('utf-8')
                file_info['file_content_b64'] = file_content_b64
                file_info['processing_method'] = 'redis'

                # Удаляем исходный файл
                self.smart_video_service.cleanup_temp_files(audio_path)

                from services.transcription import process_transcription_task
                process_transcription_task.delay(chat_id, user['telegram_id'], file_info)

            else:
                # Большой файл - через файловую систему
                from services.transcription import process_large_file_task
                import uuid
                import shutil

                shared_dir = "/tmp/shared_large_files"
                os.makedirs(shared_dir, exist_ok=True)
                unique_filename = f"youtube_{uuid.uuid4().hex}.mp3"
                shared_file_path = os.path.join(shared_dir, unique_filename)
                shutil.move(audio_path, shared_file_path)

                file_info['shared_file_path'] = shared_file_path
                file_info['is_large_file'] = True
                file_info['processing_method'] = 'filesystem'

                process_large_file_task.delay(chat_id, user['telegram_id'], file_info)

            # Финальный статус
            final_status = f"✅ YouTube аудио передано в обработку!\n\n"
            final_status += f"🎬 Видео: {video_id}\n"
            final_status += f"📁 {file_size_mb:.1f} МБ\n"

            if duration_seconds > 0:
                final_status += f"⏱️ ~{duration_seconds // 60}:{duration_seconds % 60:02d}\n"

            final_status += f"🤖 Транскрипция началась...\n"

            if result.get('title'):
                final_status += f"🎭 {result['title'][:50]}...\n"

            final_status += f"\n⏳ Ожидайте результат через ~1-2 минуты"
            final_status += f"\n\n🔍 ID задачи: {video_id}"  # Для отладки

            await self.telegram.edit_message_text(
                chat_id, message_id, final_status
            )

            logger.info(f"✅ YouTube аудио передано в систему транскрипции: {video_id}, размер: {file_size_mb:.1f}MB")

        except Exception as e:
            logger.error(f"Ошибка интеграции с системой транскрипции: {e}", exc_info=True)
            await self.telegram.edit_message_text(
                chat_id, message_id,
                f"❌ Ошибка передачи в систему транскрипции: {str(e)}\n\n"
                f"🔍 Для отладки: {video_id}"
            )
            # Удаляем файл при ошибке
            self.smart_video_service.cleanup_temp_files(audio_path)

    async def _handle_regular_text(self, chat_id: int, user: dict, text: str):
        """Обработка обычного текста"""
        youtube_status = "✅ YouTube ссылки" if self.smart_video_service else "❌ YouTube (нет зависимостей)"

        response = f"""💬 Получен текст: "{text[:50]}{'...' if len(text) > 50 else ''}"

🤖 Что я умею:

📤 **Загружайте контент:**
• Аудиофайлы для транскрипции  
• {youtube_status}

🎯 **Команды:**
/start - Главное меню
/balance - Проверить баланс
/help - Полная справка

🎬 **Попробуйте YouTube:**
Отправьте ссылку на YouTube видео!"""

        await self.telegram.send_message(chat_id, response)