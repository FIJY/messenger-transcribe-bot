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
        """Обработка YouTube видео (умно: сначала субтитры, потом аудио)"""

        status_message = await self.telegram.send_message(
            chat_id,
            "🎬 Обрабатываю YouTube видео...\n🔄 Проверяю доступность субтитров"
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

            # Умное получение текста (сначала субтитры, потом аудио)
            result, source, metadata = await self.smart_video_service.get_text_smart(url)

            if source == 'subtitles':
                # ✅ Субтитры найдены - БЕСПЛАТНО!
                await self._handle_subtitles_result(
                    chat_id, user, status_message['message_id'],
                    result, metadata, url
                )

            elif source == 'audio_file':
                # 📥 Нужна транскрипция аудио - платно
                await self._handle_audio_transcription_result(
                    chat_id, user, status_message['message_id'],
                    result, metadata, url
                )

        except SubtitleNotFoundError:
            # Субтитры не найдены, пробуем загрузить аудио
            await self.telegram.edit_message_text(
                chat_id,
                status_message['message_id'],
                f"📄 Субтитры не найдены\n🔄 Загружаю аудиодорожку..."
            )

            try:
                # Пытаемся загрузить аудио
                result, source, metadata = await self.smart_video_service.get_text_smart(
                    url, prefer_subtitles=False
                )

                if source == 'audio_file':
                    await self._handle_audio_transcription_result(
                        chat_id, user, status_message['message_id'],
                        result, metadata, url
                    )

            except YouTubeBlockedError as blocked_error:
                error_msg = str(blocked_error).lower()
                if "sign in to confirm" in error_msg or "not a bot" in error_msg:
                    await self.telegram.edit_message_text(
                        chat_id,
                        status_message['message_id'],
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
                        status_message['message_id'],
                        f"🚫 YouTube заблокировал загрузку\n\n"
                        f"🎬 Видео: {video_id}\n"
                        f"❌ Причина: {str(blocked_error)}\n\n"
                        f"💡 **Что попробовать:**\n"
                        f"• Подождать несколько минут и попробовать снова\n"
                        f"• Использовать VPN\n"
                        f"• Отправить аудиофайл напрямую\n"
                        f"• Попробовать другое видео"
                    )

            except DownloadError as download_error:
                await self.telegram.edit_message_text(
                    chat_id,
                    status_message['message_id'],
                    f"📥 Не удалось загрузить аудио\n\n"
                    f"🎬 Видео: {video_id}\n"
                    f"❌ Ошибка: {str(download_error)}\n\n"
                    f"💡 Возможные причины:\n"
                    f"• Видео приватное или удалено\n"
                    f"• Блокировка по авторским правам\n"
                    f"• Временные проблемы с YouTube\n\n"
                    f"Попробуйте другую ссылку"
                )

            except SmartVideoError as video_error:
                await self.telegram.edit_message_text(
                    chat_id,
                    status_message['message_id'],
                    f"❌ Ошибка обработки видео:\n{str(video_error)}\n\n"
                    f"💡 Попробуйте другую ссылку или отправьте аудиофайл напрямую"
                )

        except YouTubeBlockedError as blocked_error:
            # Блокировка уже на стадии получения субтитров
            error_msg = str(blocked_error).lower()
            if "sign in to confirm" in error_msg or "not a bot" in error_msg:
                await self.telegram.edit_message_text(
                    chat_id,
                    status_message['message_id'],
                    f"🤖 YouTube требует подтверждения\n\n"
                    f"🎬 Видео: {video_id}\n"
                    f"❌ \"Sign in to confirm you're not a bot\"\n\n"
                    f"🔧 **Технические проблемы:**\n"
                    f"• YouTube активировал anti-bot защиту\n"
                    f"• Нужны обновленные cookies\n"
                    f"• Возможно, IP временно заблокирован\n\n"
                    f"💡 **Рекомендации:**\n"
                    f"• Попробуйте через час\n"
                    f"• Используйте VPN\n"
                    f"• Отправьте аудиофайл напрямую"
                )
            else:
                await self.telegram.edit_message_text(
                    chat_id,
                    status_message['message_id'],
                    f"🚫 YouTube заблокировал доступ к видео\n\n"
                    f"🎬 Видео: {video_id}\n"
                    f"❌ {str(blocked_error)}\n\n"
                    f"💡 **Рекомендации:**\n"
                    f"• Попробуйте через 10-15 минут\n"
                    f"• Используйте VPN\n"
                    f"• Отправьте аудиофайл напрямую"
                )

        except DownloadError as download_error:
            await self.telegram.edit_message_text(
                chat_id,
                status_message['message_id'],
                f"📥 Проблема с загрузкой\n\n"
                f"🎬 Видео: {video_id}\n"
                f"❌ {str(download_error)}\n\n"
                f"💡 Попробуйте другую ссылку"
            )

        except SmartVideoError as e:
            await self.telegram.edit_message_text(
                chat_id,
                status_message['message_id'],
                f"❌ Ошибка обработки видео:\n{str(e)}\n\n"
                f"💡 Попробуйте другую ссылку или отправьте аудиофайл напрямую"
            )
        except Exception as e:
            logger.error(f"Критическая ошибка обработки YouTube: {e}", exc_info=True)
            await self.telegram.edit_message_text(
                chat_id,
                status_message['message_id'],
                "❌ Произошла непредвиденная ошибка при обработке видео\n\n"
                f"🔧 Если проблема повторяется, обратитесь к администратору"
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
                duration_seconds=0,  # Неизвестно для субтитров
                metadata={
                    'source': 'youtube_subtitles',
                    'original_url': url,
                    'video_id': video_id,
                    'method': 'subtitles'
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
💰 Стоимость: 0 мин (бесплатно!)

🎯 Теперь можете обработать текст в любых форматах:"""

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

        # Получаем размер файла
        try:
            file_size = os.path.getsize(audio_path)
            file_size_mb = file_size / (1024 * 1024)
        except OSError as e:
            logger.error(f"Не удалось получить размер файла {audio_path}: {e}")
            await self.telegram.edit_message_text(
                chat_id, message_id,
                f"❌ Ошибка доступа к загруженному файлу\n\n"
                f"🎬 Видео: {video_id}\n"
                f"Попробуйте еще раз"
            )
            return

        # Примерная оценка длительности (MP3 192kbps ≈ 1.44 MB/минуту)
        estimated_duration_seconds = max(60, int(file_size_mb / 1.44 * 60))  # Минимум 1 минута
        estimated_cost_seconds = max(3, estimated_duration_seconds)  # Минимум 3 секунды

        # Проверяем баланс (переводим в секунды)
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
            # Удаляем временный файл
            self.smart_video_service.cleanup_temp_files(audio_path)
            return

        # Обновляем статус
        await self.telegram.edit_message_text(
            chat_id, message_id,
            f"📥 Аудио загружено из YouTube!\n\n"
            f"🎬 Видео: {video_id}\n"
            f"📁 {file_size_mb:.1f} МБ\n"
            f"💰 Примерная стоимость: {estimated_cost_seconds / 60:.1f} мин\n\n"
            f"🔄 Передаю в систему транскрипции..."
        )

        try:
            # ИНТЕГРАЦИЯ с существующей системой медиа-обработки
            # Создаем file_info в формате, который понимает ваша система
            file_info = {
                'file_id': f'youtube_{video_id}',
                'file_unique_id': f'yt_{video_id}',
                'file_size': file_size,
                'duration': estimated_duration_seconds,
                'file_name': f'YouTube_{video_id}.mp3',
                'media_type': 'youtube_audio',
                'original_extension': 'mp3',
                'source': 'youtube_audio',
                'original_url': url,
                'video_id': video_id,
                'local_file_path': audio_path  # Путь к уже загруженному файлу
            }

            # Используем существующую логику обработки через Redis/filesystem
            from services.transcription import process_transcription_task
            import base64

            if file_size_mb <= 15:  # Ваш лимит для Redis
                # Маленький файл - через Redis
                with open(audio_path, 'rb') as f:
                    file_content = f.read()
                file_content_b64 = base64.b64encode(file_content).decode('utf-8')
                file_info['file_content_b64'] = file_content_b64

                # Удаляем исходный файл
                self.smart_video_service.cleanup_temp_files(audio_path)

                # Отправляем в обработку
                process_transcription_task.delay(chat_id, user['telegram_id'], file_info)

            else:
                # Большой файл - через файловую систему
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
            await self.telegram.edit_message_text(
                chat_id, message_id,
                f"✅ YouTube аудио передано в обработку!\n\n"
                f"🎬 Видео: {video_id}\n"
                f"📁 {file_size_mb:.1f} МБ\n"
                f"🤖 Транскрипция началась...\n\n"
                f"⏳ Ожидайте результат через ~1-2 минуты"
            )

            logger.info(f"✅ YouTube аудио передано в систему транскрипции: {video_id}")

        except Exception as e:
            logger.error(f"Ошибка интеграции с системой транскрипции: {e}", exc_info=True)
            await self.telegram.edit_message_text(
                chat_id, message_id,
                f"❌ Ошибка передачи в систему транскрипции: {str(e)}"
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