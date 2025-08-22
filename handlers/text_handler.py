# handlers/text_handler.py - Обработчик текстовых сообщений с поддержкой YouTube
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
        """Обработка YouTube видео с новым Tor методом"""

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
                f"🔄 Пытаюсь получить субтитры..."
            )

            # Используем улучшенный метод с Tor
            result = await self.smart_video_service.enhanced_download_youtube_content(url)

            if result and result.get('type') == 'subtitles':
                # Успешно получили субтитры
                await self._handle_subtitles_result(
                    chat_id, user, status_message['message_id'],
                    result['content'], {
                        'video_id': video_id,
                        'title': result.get('title'),
                        'duration': result.get('duration'),
                        'method': result.get('method'),
                        'ip_used': result.get('ip_used')
                    }, url
                )

            elif result and result.get('type') == 'audio':
                # Скачали аудио, нужно транскрибировать
                await self._handle_audio_transcription_result(
                    chat_id, user, status_message['message_id'],
                    result['file_path'], {
                        'video_id': video_id,
                        'title': result.get('title'),
                        'duration': result.get('duration'),
                        'method': result.get('method'),
                        'ip_used': result.get('ip_used')
                    }, url
                )

            else:
                # Fallback на старый метод
                await self._handle_youtube_video_fallback(chat_id, user, status_message['message_id'], url, video_id)

        except Exception as e:
            logger.error(f"❌ Ошибка обработки YouTube: {e}", exc_info=True)

            await self.telegram.edit_message_text(
                chat_id,
                status_message['message_id'],
                f"❌ Ошибка при обработке видео\n"
                f"🔧 Техническая информация: {str(e)[:200]}"
            )

    async def _handle_youtube_video_fallback(self, chat_id: int, user: dict, message_id: int, url: str, video_id: str):
        """Fallback на старый метод обработки YouTube"""

        try:
            # Обновляем статус
            await self.telegram.edit_message_text(
                chat_id,
                message_id,
                f"🔄 Tor метод не сработал, пробуем стандартный способ...\n"
                f"🎬 Видео: {video_id}"
            )

            # Умное получение текста (сначала субтитры, потом аудио)
            result, source, metadata = await self.smart_video_service.get_text_smart(url)

            if source == 'subtitles' or source == 'subtitles_invidious':
                # ✅ Субтитры найдены - БЕСПЛАТНО!
                await self._handle_subtitles_result(
                    chat_id, user, message_id,
                    result, metadata, url
                )

            elif source == 'audio_file':
                # 🔥 Нужна транскрипция аудио - платно
                await self._handle_audio_transcription_result(
                    chat_id, user, message_id,
                    result, metadata, url
                )

        except SubtitleNotFoundError:
            # Субтитры не найдены, пробуем загрузить аудио
            await self.telegram.edit_message_text(
                chat_id,
                message_id,
                f"🔄 Субтитры не найдены\n🔄 Загружаю аудиодорожку..."
            )

            try:
                # Пытаемся загрузить аудио
                result, source, metadata = await self.smart_video_service.get_text_smart(
                    url, prefer_subtitles=False
                )

                if source == 'audio_file':
                    await self._handle_audio_transcription_result(
                        chat_id, user, message_id,
                        result, metadata, url
                    )

            except YouTubeBlockedError as blocked_error:
                await self._handle_youtube_blocked_error(chat_id, message_id, video_id, blocked_error)

            except DownloadError as download_error:
                await self._handle_download_error(chat_id, message_id, video_id, download_error)

            except SmartVideoError as video_error:
                await self.telegram.edit_message_text(
                    chat_id,
                    message_id,
                    f"❌ Ошибка обработки видео:\n{str(video_error)}\n\n"
                    f"💡 Попробуйте другую ссылку или отправьте аудиофайл напрямую"
                )

        except YouTubeBlockedError as blocked_error:
            await self._handle_youtube_blocked_error(chat_id, message_id, video_id, blocked_error)

        except DownloadError as download_error:
            await self._handle_download_error(chat_id, message_id, video_id, download_error)

        except SmartVideoError as e:
            await self.telegram.edit_message_text(
                chat_id,
                message_id,
                f"❌ Ошибка обработки видео:\n{str(e)}\n\n"
                f"💡 Попробуйте другую ссылку или отправьте аудиофайл напрямую"
            )
        except Exception as e:
            logger.error(f"Критическая ошибка обработки YouTube: {e}", exc_info=True)
            await self.telegram.edit_message_text(
                chat_id,
                message_id,
                "❌ Произошла непредвиденная ошибка при обработке видео\n\n"
                f"🔧 Если проблема повторяется, обратитесь к администратору"
            )

    async def _handle_youtube_blocked_error(self, chat_id: int, message_id: int, video_id: str,
                                            blocked_error: Exception):
        """Обработка ошибки блокировки YouTube"""
        error_msg = str(blocked_error).lower()
        if "sign in to confirm" in error_msg or "not a bot" in error_msg:
            await self.telegram.edit_message_text(
                chat_id,
                message_id,
                f"🤖 YouTube требует подтверждения\n\n"
                f"🎬 Видео: {video_id}\n"
                f"❌ YouTube: \"Sign in to confirm you're not a bot\"\n\n"
                f"🔧 **Возможные решения:**\n"
                f"• Обновить cookies в системе\n"
                f"• Попробовать через 30-60 минут\n"
                f"• Использовать VPN\n"
                f"• Отправить аудиофайл напрямую\n\n"
                f"💡 Проблема на стороне YouTube, не в боте"
            )
        else:
            await self.telegram.edit_message_text(
                chat_id,
                message_id,
                f"🚫 YouTube заблокировал загрузку\n\n"
                f"🎬 Видео: {video_id}\n"
                f"❌ Причина: {str(blocked_error)}\n\n"
                f"💡 **Что попробовать:**\n"
                f"• Подождать несколько минут и попробовать снова\n"
                f"• Использовать VPN\n"
                f"• Отправить аудиофайл напрямую\n"
                f"• Попробовать другое видео"
            )

    async def _handle_download_error(self, chat_id: int, message_id: int, video_id: str, download_error: Exception):
        """Обработка ошибки загрузки"""
        await self.telegram.edit_message_text(
            chat_id,
            message_id,
            f"🔥 Не удалось загрузить аудио\n\n"
            f"🎬 Видео: {video_id}\n"
            f"❌ Ошибка: {str(download_error)}\n\n"
            f"💡 Возможные причины:\n"
            f"• Видео приватное или удалено\n"
            f"• Блокировка по авторским правам\n"
            f"• Временные проблемы с YouTube\n\n"
            f"Попробуйте другую ссылку"
        )

    async def _handle_subtitles_result(self, chat_id: int, user: dict, message_id: int,
                                       text: str, metadata: dict, url: str):
        """Обработка результата с субтитрами (БЕСПЛАТНО!)"""

        video_id = metadata.get('video_id', 'unknown')
        words_count = metadata.get('words', len(text.split()))

        # Проверяем качество субтитров
        if len(text.strip()) < 50:
            await self.telegram.edit_message_text(
                chat_id, message_id,
                f"⚠️ Субтитры слишком короткие ({len(text)} символов)\n\n"
                f"🎬 Видео: {video_id}\n"
                f"🔄 Попробую загрузить аудио..."
            )

            # Переключаемся на загрузку аудио
            try:
                result, source, metadata = await self.smart_video_service.get_text_smart(
                    url, prefer_subtitles=False
                )
                if source == 'audio_file':
                    await self._handle_audio_transcription_result(
                        chat_id, user, message_id, result, metadata, url
                    )
            except Exception as e:
                await self.telegram.edit_message_text(
                    chat_id, message_id,
                    f"❌ Субтитры слишком короткие, аудио недоступно:\n{str(e)}"
                )
            return

        # Создаем "виртуальную" транскрипцию для субтитров
        try:
            # Сохраняем как аудиофайл (виртуальный)
            audio_file_id = await self.db.create_audio_file(
                user['id'],
                f"YouTube_{video_id}_subtitles.txt",
                len(text.encode('utf-8')),
                'text/plain',
                duration_seconds=metadata.get('duration', 0),
                metadata={
                    'source': 'youtube_subtitles',
                    'original_url': url,
                    'video_id': video_id,
                    'method': metadata.get('method', 'subtitles'),
                    'ip_used': metadata.get('ip_used'),
                    'title': metadata.get('title')
                }
            )

            # Сохраняем транскрипцию
            transcription_id = await self.db.create_transcription(
                audio_file_id,
                text,
                'auto',  # Язык определим позже если нужно
                confidence=1.0  # Субтитры считаем точными
            )

            # Показываем результат
            success_text = f"""✅ Субтитры получены БЕСПЛАТНО!

🎬 YouTube: {video_id}
📄 Источник: Готовые субтитры
📊 {words_count} слов • {len(text)} символов
💰 Стоимость: 0 мин (бесплатно!)"""

            if metadata.get('title'):
                success_text += f"\n🎭 {metadata['title'][:50]}..."

            if metadata.get('ip_used'):
                success_text += f"\n🌐 IP: {metadata['ip_used']}"

            success_text += f"\n\n🎯 Теперь можете обработать текст в любых форматах:"

            # Создаем клавиатуру для обработки
            from ui.keyboards import create_post_transcription_keyboard

            keyboard = create_post_transcription_keyboard(
                transcription_id,
                user.get('balance_minutes', 0)  # Баланс не изменился
            )

            await self.telegram.edit_message_text(
                chat_id, message_id, success_text, reply_markup=keyboard
            )

            logger.info(f"✅ YouTube субтитры обработаны бесплатно: {transcription_id}")

        except Exception as e:
            logger.error(f"Ошибка сохранения субтитров: {e}", exc_info=True)
            await self.telegram.edit_message_text(
                chat_id, message_id,
                f"❌ Ошибка сохранения субтитров: {str(e)}"
            )

    async def _handle_audio_transcription_result(self, chat_id: int, user: dict, message_id: int,
                                                 audio_path: str, metadata: dict, url: str):
        """Обработка аудио для транскрипции (ПЛАТНО) - интеграция с существующей системой"""

        video_id = metadata.get('video_id', 'unknown')

        # ИСПРАВЛЕНИЕ: Получаем размер файла ДО загрузки в R2
        try:
            # Если audio_path - это URL (файл уже в R2)
            if audio_path.startswith('http'):
                # Получаем размер из метаданных или делаем HEAD запрос
                file_size = metadata.get('file_size')
                if not file_size:
                    import requests
                    try:
                        response = requests.head(audio_path, timeout=10)
                        file_size = int(response.headers.get('content-length', 0))
                    except Exception as e:
                        logger.warning(f"Не удалось получить размер файла из R2: {e}")
                        # Примерная оценка: 1MB на минуту для MP3 128kbps
                        estimated_duration = metadata.get('duration', 300)  # 5 минут по умолчанию
                        file_size = estimated_duration * 1024 * 128 // 8  # 128kbps в байты
            else:
                # Локальный файл
                file_size = os.path.getsize(audio_path)

            file_size_mb = file_size / (1024 * 1024)

        except Exception as e:
            logger.error(f"Ошибка получения размера файла {audio_path}: {e}")
            # Fallback: используем данные из метаданных или оценку
            duration_seconds = metadata.get('duration', 300)
            file_size = duration_seconds * 16000  # Примерно 16KB на секунду для MP3
            file_size_mb = file_size / (1024 * 1024)

        # Примерная оценка длительности
        duration_seconds = metadata.get('duration')
        if not duration_seconds:
            # MP3 192kbps ≈ 1.44 MB/минуту
            duration_seconds = max(60, int(file_size_mb / 1.44 * 60))

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
            # Очищаем файл если он локальный
            if not audio_path.startswith('http'):
                self.smart_video_service.cleanup_temp_files(audio_path)
            return

        # Обновляем статус
        status_text = f"🔥 Аудио загружено из YouTube!\n\n"
        status_text += f"🎬 Видео: {video_id}\n"
        status_text += f"📁 {file_size_mb:.1f} МБ\n"
        status_text += f"⏱️ ~{duration_seconds // 60}:{duration_seconds % 60:02d}\n"
        status_text += f"💰 Примерная стоимость: {estimated_cost_seconds / 60:.1f} мин\n"

        if metadata.get('title'):
            status_text += f"🎭 {metadata['title'][:50]}...\n"

        if metadata.get('ip_used'):
            status_text += f"🌐 IP: {metadata['ip_used']}\n"

        status_text += f"\n🔄 Передаю в систему транскрипции..."

        await self.telegram.edit_message_text(
            chat_id, message_id, status_text
        )

        try:
            # Создаем file_info с правильными данными
            file_info = {
                'file_id': f'youtube_{video_id}',
                'file_unique_id': f'yt_{video_id}',
                'file_size': file_size,
                'duration': duration_seconds,
                'file_name': f'YouTube_{video_id}.mp3',
                'media_type': 'youtube_audio',
                'original_extension': 'mp3',
                'source': 'youtube_audio',
                'original_url': url,
                'video_id': video_id,
                'title': metadata.get('title'),
                'method': metadata.get('method'),
                'ip_used': metadata.get('ip_used')
            }

            # Определяем способ обработки
            if audio_path.startswith('http'):
                # Файл уже в R2 - передаем URL
                file_info['r2_url'] = audio_path
                file_info['processing_method'] = 'r2_download'

                # Отправляем в обработку
                from services.transcription import process_transcription_task
                process_transcription_task.delay(chat_id, user['telegram_id'], file_info)

            elif file_size_mb <= 15:
                # Небольшой локальный файл - через Redis
                import base64
                with open(audio_path, 'rb') as f:
                    file_content = f.read()
                file_content_b64 = base64.b64encode(file_content).decode('utf-8')
                file_info['file_content_b64'] = file_content_b64
                file_info['processing_method'] = 'redis'

                # Удаляем исходный файл
                self.smart_video_service.cleanup_temp_files(audio_path)

                # Отправляем в обработку
                from services.transcription import process_transcription_task
                process_transcription_task.delay(chat_id, user['telegram_id'], file_info)

            else:
                # Большой локальный файл - через файловую систему
                from services.transcription import process_large_file_task
                import uuid
                import shutil

                # Перемещаем в общую директорию
                shared_dir = "/tmp/shared_large_files"
                os.makedirs(shared_dir, exist_ok=True)
                unique_filename = f"youtube_{uuid.uuid4().hex}.mp3"
                shared_file_path = os.path.join(shared_dir, unique_filename)
                shutil.move(audio_path, shared_file_path)

                file_info['shared_file_path'] = shared_file_path
                file_info['is_large_file'] = True
                file_info['processing_method'] = 'filesystem'

                # Отправляем в обработку
                process_large_file_task.delay(chat_id, user['telegram_id'], file_info)

            # Обновляем статус - передано в обработку
            final_status = f"✅ YouTube аудио передано в обработку!\n\n"
            final_status += f"🎬 Видео: {video_id}\n"
            final_status += f"📁 {file_size_mb:.1f} МБ\n"
            final_status += f"⏱️ ~{duration_seconds // 60}:{duration_seconds % 60:02d}\n"
            final_status += f"🤖 Транскрипция началась...\n"

            if metadata.get('title'):
                final_status += f"🎭 {metadata['title'][:50]}...\n"

            final_status += f"\n⏳ Ожидайте результат через ~1-2 минуты"

            await self.telegram.edit_message_text(
                chat_id, message_id, final_status
            )

            logger.info(f"✅ YouTube аудио передано в систему транскрипции: {video_id}")

        except Exception as e:
            logger.error(f"Ошибка интеграции с системой транскрипции: {e}", exc_info=True)
            await self.telegram.edit_message_text(
                chat_id, message_id,
                f"❌ Ошибка передачи в систему транскрипции: {str(e)}"
            )
            # Удаляем файл при ошибке (если локальный)
            if not audio_path.startswith('http'):
                self.smart_video_service.cleanup_temp_files(audio_path)

    async def cleanup_old_r2_files():
        """Очистка файлов в R2 старше 24 часов"""
        try:
            # Подключаемся к R2
            import boto3
            from datetime import datetime, timedelta

            # Ваши настройки R2
            r2_client = boto3.client(
                's3',
                endpoint_url='https://your-account.r2.cloudflarestorage.com',
                aws_access_key_id='your-access-key',
                aws_secret_access_key='your-secret-key'
            )

            bucket_name = 'fijy-bot-storage'
            prefix = 'youtube_audio/'

            # Получаем список файлов
            response = r2_client.list_objects_v2(
                Bucket=bucket_name,
                Prefix=prefix
            )

            if 'Contents' not in response:
                return

            # Текущее время минус 24 часа
            cutoff_time = datetime.now() - timedelta(hours=24)

            files_to_delete = []
            for obj in response['Contents']:
                # Сравниваем время последнего изменения
                if obj['LastModified'].replace(tzinfo=None) < cutoff_time:
                    files_to_delete.append({'Key': obj['Key']})

            # Удаляем старые файлы
            if files_to_delete:
                r2_client.delete_objects(
                    Bucket=bucket_name,
                    Delete={'Objects': files_to_delete}
                )
                logger.info(f"🧹 Удалено {len(files_to_delete)} старых файлов из R2")

        except Exception as e:
            logger.error(f"Ошибка очистки R2: {e}")

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