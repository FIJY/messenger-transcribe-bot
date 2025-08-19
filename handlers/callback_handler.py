# handlers/callback_handler.py - ПОЛНАЯ ИСПРАВЛЕННАЯ версия с FormatProcessor
import logging
from typing import Dict, Any, Optional, Set
import asyncio
import os
import aiofiles

from services.telegram_client import TelegramClient
from services.database import DatabaseService
from ui.localization import LocalizationService
from services.ai_processing import AIProcessingService
from services.format_processor import FormatProcessorService, FormatProcessorError, UnknownFormatError, \
    ProcessingTimeoutError
from handlers.start_handler import StartHandler
from services.export_service import ExportService
from ui.keyboards import (
    create_post_transcription_keyboard,
    create_categories_keyboard,
    create_category_formats_keyboard,
    create_export_keyboard,
    create_subscription_keyboard,
    create_processing_result_keyboard,
    create_post_transcription_keyboard_with_selections,
    create_categories_keyboard_with_selections,
    create_category_formats_keyboard_with_selections
)
from config import PROCESSING_CATEGORIES, QUICK_FORMATS, SUBSCRIPTION_PLANS

logger = logging.getLogger(__name__)


class CallbackHandler:
    """Обработчик callback-запросов с сохранением меню и отслеживанием выбранных опций"""

    def __init__(self,
                 telegram: TelegramClient,
                 db: DatabaseService,
                 localization: LocalizationService,
                 ai_service: Optional[AIProcessingService],
                 start_handler: StartHandler):
        self.telegram = telegram
        self.db = db
        self.localization = localization
        self.ai_service = ai_service
        self.start_handler = start_handler
        self.export_service = ExportService()

        # НОВЫЙ СЕРВИС для обработки форматов
        self.format_processor = FormatProcessorService(ai_service) if ai_service else None

        # Словарь для отслеживания выбранных опций по пользователям
        # Структура: {user_id: {transcription_id: set(selected_formats)}}
        self.user_selections: Dict[int, Dict[str, Set[str]]] = {}

    def _get_user_selections(self, user_id: int, transcription_id: str) -> Set[str]:
        """Получает выбранные форматы для пользователя и транскрипции"""
        if user_id not in self.user_selections:
            self.user_selections[user_id] = {}
        if transcription_id not in self.user_selections[user_id]:
            self.user_selections[user_id][transcription_id] = set()
        return self.user_selections[user_id][transcription_id]

    def _add_user_selection(self, user_id: int, transcription_id: str, format_key: str):
        """Добавляет выбранный формат"""
        selections = self._get_user_selections(user_id, transcription_id)
        selections.add(format_key)

    async def handle(self, callback_query: Dict[str, Any]):
        """Главный маршрутизатор callback-запросов с улучшенной валидацией"""
        try:
            # Валидация структуры callback_query
            if not isinstance(callback_query, dict):
                logger.error("Invalid callback_query format: not a dict")
                return

            data = callback_query.get('data')
            message = callback_query.get('message')

            if not data or not message:
                logger.error("Missing required fields in callback_query")
                return

            chat_id = message.get('chat', {}).get('id')
            message_id = message.get('message_id')

            if not chat_id:
                logger.error("Missing chat_id in callback_query")
                return

            user_id = callback_query.get('from', {}).get('id')
            if not user_id:
                logger.error("Missing user_id in callback_query")
                return

            logger.info(f"📨 Получен callback: {data} от пользователя {user_id}")

            # Получаем пользователя
            user = await self.db.get_or_create_user(
                user_id,
                callback_query.get('from', {}).get('first_name'),
                callback_query.get('from', {}).get('language_code', 'ru')
            )

            lang = user.get('language', 'ru')

            # Отвечаем на callback
            await self._answer_callback_query(callback_query.get('id'))

            # Парсим и валидируем команду
            parts = data.split(':')
            if not parts:
                logger.error(f"Invalid callback data format: {data}")
                return

            command = parts[0]

            # Маршрутизация команд
            await self._route_command(command, parts, chat_id, message_id, user, lang)

        except Exception as e:
            logger.error(f"Критическая ошибка в callback_handler: {e}", exc_info=True)

            # Попытка уведомить пользователя об ошибке
            try:
                chat_id = callback_query.get('message', {}).get('chat', {}).get('id')
                if chat_id:
                    await self.telegram.send_message(
                        chat_id,
                        "❌ Произошла ошибка. Попробуйте еще раз или обратитесь в поддержку."
                    )
            except Exception as notify_error:
                logger.error(f"Не удалось уведомить пользователя об ошибке: {notify_error}")

    async def _answer_callback_query(self, callback_query_id: Optional[str]):
        """Безопасный ответ на callback_query"""
        if not callback_query_id:
            return

        try:
            await self.telegram.client.post(
                f"{self.telegram.base_url}/answerCallbackQuery",
                json={"callback_query_id": callback_query_id}
            )
        except Exception as e:
            logger.warning(f"Не удалось ответить на callback_query: {e}")

    async def _route_command(self, command: str, parts: list, chat_id: int,
                             message_id: Optional[int], user: dict, lang: str):
        """Маршрутизация команд с сохранением меню"""

        try:
            logger.info(f"🔄 Обрабатываю команду: {command} с параметрами: {parts}")

            if command == 'show_text':
                if len(parts) < 2:
                    raise ValueError("Missing transcription_id for show_text")
                await self._handle_show_text(parts[1], chat_id, user)

            elif command == 'categories':
                if len(parts) < 2:
                    raise ValueError("Missing transcription_id for categories")
                await self._handle_categories(parts[1], chat_id, message_id, user)

            elif command == 'category':
                if len(parts) < 3:
                    raise ValueError("Missing parameters for category")
                await self._handle_category_formats(parts[1], parts[2], chat_id, message_id, user)

            elif command == 'process':
                if len(parts) < 3:
                    raise ValueError("Missing parameters for process")
                await self._handle_process_format(parts[1], parts[2], chat_id, message_id, user)

            elif command == 'export':
                if len(parts) < 2:
                    raise ValueError("Missing transcription_id for export")
                await self._handle_export_menu(parts[1], chat_id, message_id, user)

            elif command == 'export_format':
                if len(parts) < 3:
                    raise ValueError("Missing parameters for export_format")
                await self._handle_export_format(parts[1], parts[2], chat_id, user)

            elif command == 'export_all':
                if len(parts) < 2:
                    raise ValueError("Missing transcription_id for export_all")
                await self._handle_export_all(parts[1], chat_id, user)

            elif command == 'back_to_main':
                if len(parts) < 2:
                    raise ValueError("Missing transcription_id for back_to_main")
                await self._handle_back_to_main(parts[1], chat_id, message_id, user)

            elif command == 'insufficient_balance':
                if len(parts) < 2:
                    raise ValueError("Missing required_minutes for insufficient_balance")
                await self._handle_insufficient_balance(int(parts[1]), chat_id, user)

            elif command == 'subscription':
                action = parts[1] if len(parts) > 1 else 'main'
                await self._handle_subscription(action, chat_id, message_id, user)

            elif command == 'buy_plan':
                if len(parts) < 2:
                    raise ValueError("Missing plan_key for buy_plan")
                await self._handle_buy_plan(parts[1], chat_id, user)

            elif command == 'install_deps':
                if len(parts) < 2:
                    raise ValueError("Missing format for install_deps")
                await self._handle_install_deps(parts[1], chat_id)

            elif command in ['start', 'settings', 'balance', 'help']:
                await self._handle_old_commands(command, parts, chat_id, message_id, user)

            elif command == 'processing_info':
                await self._handle_processing_info(chat_id, user)

            elif command == 'clear_selections':
                if len(parts) < 2:
                    raise ValueError("Missing transcription_id for clear_selections")
                await self._handle_clear_selections(parts[1], chat_id, message_id, user)

            elif command == 'promo':
                await self._handle_promo_callbacks(parts, chat_id, message_id, user)

            elif command == 'format_info':
                if len(parts) < 2:
                    raise ValueError("Missing format_key for format_info")
                await self._handle_format_info(parts[1], chat_id, user)

            else:
                logger.warning(f"Неизвестная команда: {command}")
                await self.telegram.send_message(
                    chat_id,
                    "❌ Неизвестная команда. Попробуйте выбрать из предложенных вариантов."
                )

        except ValueError as e:
            logger.error(f"Ошибка валидации команды {command}: {e}")
            await self.telegram.send_message(
                chat_id,
                "❌ Некорректные параметры команды. Попробуйте еще раз."
            )
        except Exception as e:
            logger.error(f"Ошибка обработки команды {command}: {e}", exc_info=True)
            await self.telegram.send_message(
                chat_id,
                "❌ Произошла ошибка при обработке команды."
            )

    async def _handle_show_text(self, transcription_id: str, chat_id: int, user: dict):
        """Показать полный текст транскрипции БЕЗ удаления меню"""
        try:
            transcription = await self.db.get_transcription(transcription_id)
            if not transcription:
                await self.telegram.send_message(chat_id, "❌ Транскрипция не найдена")
                return

            # Получаем информацию о файле
            audio_file = await self.db.get_audio_file(transcription['audio_file_id'])
            file_info = {
                'file_size': audio_file.get('file_size_mb', 0) * 1024 * 1024,
                'duration': audio_file.get('duration_seconds', 0)
            }

            # КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: отправляем текст ОТДЕЛЬНЫМ сообщением
            await self._send_full_transcription_text_separately(
                chat_id, transcription_id, transcription['text'],
                transcription['language'], file_info
            )
        except Exception as e:
            logger.error(f"Ошибка показа текста {transcription_id}: {e}")
            await self.telegram.send_message(chat_id, "❌ Ошибка получения текста")

    async def _send_full_transcription_text_separately(self, chat_id: int, transcription_id: str,
                                                       text: str, language: str, file_info: dict):
        """Отправка полного текста ОТДЕЛЬНЫМ сообщением"""
        clean_text = text.replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')

        # Информация о файле
        file_size_mb = file_info.get('file_size', 0) / (1024 * 1024)
        duration_seconds = file_info.get('duration', 0)

        # Статистика
        if language in ['zh', 'ja', 'ko']:
            stats = f"{len(text)} символов"
        else:
            stats = f"{len(text.split())} слов"

        header = f"""📝 Полный текст транскрипции

📁 {file_size_mb:.1f}MB • 🌍 {language.upper()} • 📊 {stats}

───────────────────────────"""

        # Отправляем заголовок
        await self.telegram.send_message(chat_id, header)

        # Разбиваем текст если нужно
        max_length = 3800

        if len(clean_text) > max_length:
            chunks = [clean_text[i:i + max_length] for i in range(0, len(clean_text), max_length)]

            for i, chunk in enumerate(chunks):
                await self.telegram.send_message(chat_id, chunk)
                if i < len(chunks) - 1:
                    await asyncio.sleep(0.3)
        else:
            await self.telegram.send_message(chat_id, clean_text)

        # Отправляем подтверждение БЕЗ кнопок - исходное меню остается
        await self.telegram.send_message(
            chat_id,
            "👆 Полный текст выше. Исходное меню остается активным."
        )

    async def _handle_categories(self, transcription_id: str, chat_id: int, message_id: Optional[int], user: dict):
        """Показать категории форматов - ОТДЕЛЬНЫМ сообщением для сохранения исходного меню."""
        try:
            user_balance = user.get('balance_minutes', 0)
            selected_formats = self._get_user_selections(user.get('telegram_id'), transcription_id)
            keyboard = create_categories_keyboard_with_selections(transcription_id, user_balance, selected_formats)

            format_names = []
            if selected_formats:
                for fmt in selected_formats:
                    if fmt in QUICK_FORMATS:
                        format_names.append(QUICK_FORMATS[fmt]['name'])
                    else:
                        for category in PROCESSING_CATEGORIES.values():
                            if fmt in category.get('formats', {}):
                                format_names.append(category['formats'][fmt]['name'])
                                break

            selected_text = f"\n\n✅ Уже выбрано: {', '.join(format_names[:3])}{'...' if len(format_names) > 3 else ''}" if format_names else ""

            text = f"""📂 Выберите категорию:

💼 РАБОТА - протоколы, отчеты, задачи
📱 КОНТЕНТ - посты, описания, нарезки  
🎓 УЧЕБА - конспекты, вопросы, термины
🌍 ПЕРЕВОДЫ - на все популярные языки
👨‍👩‍👧‍👦 ДЛЯ СЕМЬИ - анализ безопасности

✨ Вся обработка БЕСПЛАТНА!{selected_text}"""

            # КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: ВСЕГДА отправляем ОТДЕЛЬНЫМ сообщением
            await self.telegram.send_message(chat_id, text, reply_markup=keyboard)
            logger.info(f"✅ Меню категорий отправлено отдельным сообщением для chat_id {chat_id}")

        except Exception as e:
            logger.error(f"❌ Ошибка в _handle_categories: {e}", exc_info=True)
            await self.telegram.send_message(chat_id, "❌ Не удалось загрузить меню категорий.")

    async def _handle_category_formats(self, transcription_id: str, category_key: str,
                                       chat_id: int, message_id: Optional[int], user: dict):
        """Показать форматы в категории - ОТДЕЛЬНЫМ сообщением."""
        try:
            user_balance = user.get('balance_minutes', 0)
            selected_formats = self._get_user_selections(user.get('telegram_id'), transcription_id)
            keyboard = create_category_formats_keyboard_with_selections(
                transcription_id, category_key, user_balance, selected_formats
            )

            category_info = PROCESSING_CATEGORIES.get(category_key, {})
            if not category_info:
                await self.telegram.send_message(chat_id, "❌ Неизвестная категория")
                return

            category_name = category_info.get('name', 'КАТЕГОРИЯ')
            category_emoji = category_info.get('emoji', '📂')

            selected_in_category = []
            for fmt in selected_formats:
                if fmt in category_info.get('formats', {}):
                    selected_in_category.append(category_info['formats'][fmt]['name'])

            selected_text = f"\n\n✅ Выбрано в категории: {', '.join(selected_in_category)}" if selected_in_category else ""

            text = f"""{category_emoji} {category_name}

Выберите нужный формат:

✨ Вся обработка БЕСПЛАТНА!{selected_text}"""

            # КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: ВСЕГДА отправляем ОТДЕЛЬНЫМ сообщением
            await self.telegram.send_message(chat_id, text, reply_markup=keyboard)
            logger.info(f"✅ Меню категории {category_key} отправлено отдельным сообщением для chat_id {chat_id}")

        except Exception as e:
            logger.error(f"❌ Ошибка в _handle_category_formats: {e}", exc_info=True)
            await self.telegram.send_message(chat_id, "❌ Произошла ошибка при загрузке форматов.")

    async def _handle_process_format(self, transcription_id: str, format_key: str,
                                     chat_id: int, message_id: Optional[int], user: dict):
        """ОБНОВЛЕННАЯ версия с использованием FormatProcessorService"""

        # Проверяем доступность сервисов
        if not self.format_processor:
            await self.telegram.send_message(chat_id, "❌ AI сервис временно недоступен")
            return

        user_id = user.get('telegram_id')
        self._add_user_selection(user_id, transcription_id, format_key)

        # Получаем информацию о формате через новый сервис
        format_info = self.format_processor.get_format_info(format_key)
        if not format_info:
            await self.telegram.send_message(chat_id, "❌ Неизвестный формат обработки")
            return

        # Получаем транскрипцию
        try:
            transcription = await self.db.get_transcription(transcription_id)
            if not transcription:
                await self.telegram.send_message(chat_id, "❌ Транскрипция не найдена")
                return
        except Exception as e:
            logger.error(f"Ошибка получения транскрипции {transcription_id}: {e}")
            await self.telegram.send_message(chat_id, "❌ Ошибка доступа к транскрипции")
            return

        text = transcription.get('text', '').strip()
        if not text:
            await self.telegram.send_message(chat_id, "❌ Текст транскрипции пуст")
            return

        # Показываем сообщение о начале обработки
        format_name = format_info.get('name', format_key)
        processing_message = await self.telegram.send_message(
            chat_id,
            f"🤖 Создаю «{format_name}»... Это может занять до минуты.\n✨ Обработка бесплатна!"
        )

        # Обрабатываем через новый сервис
        result_text = None
        error_message = None

        try:
            # Используем новый FormatProcessorService с таймаутом
            result_text = await asyncio.wait_for(
                self.format_processor.process_format(text, format_key),
                timeout=120.0
            )
        except UnknownFormatError:
            error_message = f"❌ Неизвестный формат: {format_key}"
            logger.error(f"Неизвестный формат: {format_key}")
        except ProcessingTimeoutError:
            error_message = f"⏰ Превышено время обработки для формата «{format_name}»"
            logger.error(f"Таймаут AI обработки для формата {format_key}")
        except FormatProcessorError as e:
            error_message = f"❌ Ошибка обработки: {str(e)}"
            logger.error(f"Ошибка FormatProcessor для {format_key}: {e}")
        except asyncio.TimeoutError:
            error_message = f"⏰ Превышено время обработки для формата «{format_name}»"
            logger.error(f"Общий таймаут для формата {format_key}")
        except Exception as e:
            error_message = f"❌ Неожиданная ошибка при обработке"
            logger.error(f"Неожиданная ошибка AI обработки {format_key}: {e}", exc_info=True)

        # Подготавливаем финальное сообщение с меню
        user_balance = user.get('balance_minutes', 0)
        selected_formats = self._get_user_selections(user_id, transcription_id)

        final_keyboard = create_post_transcription_keyboard_with_selections(
            transcription_id, user_balance, selected_formats
        )

        if result_text and result_text.strip():
            # Успешная обработка
            final_message = f"""✅ Результат «{format_name}»:

{result_text.strip()}

---
🎯 Что делаем дальше?
💰 Ваш баланс: {user_balance:.1f} мин"""

            # Редактируем сообщение "Создаю..." на результат с кнопками
            await self.telegram.edit_message_text(
                chat_id,
                processing_message['message_id'],
                final_message,
                reply_markup=final_keyboard
            )
        else:
            # Ошибка обработки
            error_text = error_message or "❌ Ошибка при обработке. Попробуйте другой формат или повторите позже."

            final_message = f"""{error_text}

---
🎯 Попробуйте другой формат:
💰 Ваш баланс: {user_balance:.1f} мин"""

            await self.telegram.edit_message_text(
                chat_id,
                processing_message['message_id'],
                final_message,
                reply_markup=final_keyboard
            )

    async def _update_menu_with_selection(self, chat_id: int, message_id: int,
                                          transcription_id: str, user: dict):
        """Обновляет меню, показывая выбранные опции"""
        try:
            user_balance = user.get('balance_minutes', 0)
            selected_formats = self._get_user_selections(user.get('telegram_id'), transcription_id)

            keyboard = create_post_transcription_keyboard_with_selections(
                transcription_id, user_balance, selected_formats
            )

            selected_text = ""
            if selected_formats:
                format_names = []
                for fmt in selected_formats:
                    if fmt in QUICK_FORMATS:
                        format_names.append(QUICK_FORMATS[fmt]['name'])

                selected_text = f"\n\n✅ Обработано: {', '.join(format_names)}"

            text = f"""🎯 Что делаем дальше?

✨ ВСЯ ОБРАБОТКА БЕСПЛАТНА!
Выберите нужный формат:{selected_text}"""

            await self.telegram.edit_message_text(chat_id, message_id, text, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Ошибка обновления меню: {e}")

    async def _handle_back_to_main(self, transcription_id: str, chat_id: int, message_id: Optional[int], user: dict):
        """Возврат к главному меню - закрываем текущее подменю."""
        try:
            # Просто отправляем подтверждение о закрытии подменю
            await self.telegram.send_message(
                chat_id,
                "✅ Подменю закрыто. Используйте кнопки в исходном меню выше ☝️"
            )

            logger.info(f"✅ Подменю закрыто для chat_id {chat_id}")

        except Exception as e:
            logger.error(f"❌ Ошибка в _handle_back_to_main: {e}", exc_info=True)
            await self.telegram.send_message(chat_id, "❌ Произошла ошибка.")

    async def _handle_export_menu(self, transcription_id: str, chat_id: int, message_id: Optional[int], user: dict):
        """Показать меню экспорта БЕЗ удаления основного меню"""
        try:
            # Получаем информацию о доступных форматах
            available_formats = self.export_service.get_available_formats()

            # Создаем клавиатуру с учетом доступности форматов
            keyboard_rows = []

            # Первый ряд - всегда доступные форматы
            row1 = []
            if available_formats['txt']:
                row1.append({"text": "📄 .txt", "callback_data": f"export_format:{transcription_id}:txt"})
            if available_formats['srt']:
                row1.append({"text": "📜 .srt", "callback_data": f"export_format:{transcription_id}:srt"})
            keyboard_rows.append(row1)

            # Второй ряд - форматы требующие зависимостей
            row2 = []
            if available_formats['docx']:
                row2.append({"text": "📋 .docx", "callback_data": f"export_format:{transcription_id}:docx"})
            else:
                row2.append({"text": "📋 .docx ❌", "callback_data": f"install_deps:docx"})

            if available_formats['pdf']:
                row2.append({"text": "📑 PDF", "callback_data": f"export_format:{transcription_id}:pdf"})
            else:
                row2.append({"text": "📑 PDF ❌", "callback_data": f"install_deps:pdf"})
            keyboard_rows.append(row2)

            # Кнопка "Все форматы"
            keyboard_rows.append([
                {"text": "📦 Скачать все доступные", "callback_data": f"export_all:{transcription_id}"}
            ])

            # Кнопка назад
            keyboard_rows.append([
                {"text": "🔙 Назад", "callback_data": f"back_to_main:{transcription_id}"}
            ])

            keyboard = {"inline_keyboard": keyboard_rows}

            # Формируем текст с описанием форматов
            format_descriptions = []
            for fmt, available in available_formats.items():
                status = "✅" if available else "❌"
                desc = self.export_service.get_format_description(fmt)
                format_descriptions.append(f"{status} **{fmt.upper()}** - {desc}")

            text = f"""💾 Выберите формат экспорта:

{chr(10).join(format_descriptions)}

✨ Экспорт бесплатен!"""

            # ОТПРАВЛЯЕМ ОТДЕЛЬНЫМ сообщением, НЕ редактируем исходное
            await self.telegram.send_message(chat_id, text, reply_markup=keyboard)
            logger.info(f"✅ Меню экспорта отправлено отдельным сообщением для chat_id {chat_id}")

        except Exception as e:
            logger.error(f"❌ Ошибка в _handle_export_menu: {e}", exc_info=True)
            await self.telegram.send_message(chat_id, "❌ Произошла ошибка при загрузке меню экспорта")

    async def _handle_export_format(self, transcription_id: str, format_type: str, chat_id: int, user: dict):
        """Экспорт в конкретном формате - БЕЗ удаления меню"""
        try:
            # Получаем данные транскрипции
            transcription = await self.db.get_transcription(transcription_id)
            if not transcription:
                await self.telegram.send_message(chat_id, "❌ Транскрипция не найдена")
                return

            # Получаем данные аудио файла для метаданных
            audio_file = await self.db.get_audio_file(transcription['audio_file_id'])

            # Подготавливаем данные для экспорта
            export_data = {
                'text': transcription['text'],
                'language': transcription['language'],
                'created_at': transcription.get('created_at'),
                'duration_seconds': audio_file.get('duration_seconds', 0) if audio_file else 0,
                'file_size_mb': audio_file.get('file_size_mb', 0) if audio_file else 0
            }

            # Проверяем доступность формата
            available_formats = self.export_service.get_available_formats()
            if not available_formats.get(format_type, False):
                format_name = {'docx': 'Word', 'pdf': 'PDF'}.get(format_type, format_type.upper())
                await self.telegram.send_message(
                    chat_id,
                    f"❌ Формат {format_name} недоступен.\n"
                    f"Установите зависимости: pip install python-docx reportlab"
                )
                return

            await self.telegram.send_message(chat_id, f"📄 Создаю файл .{format_type}...")

            # Создаем файл
            file_path = await self.export_service.export_transcription(export_data, format_type)

            if file_path and os.path.exists(file_path):
                # Отправляем файл пользователю
                await self._send_file_to_user(chat_id, file_path, format_type)

                # Подтверждение БЕЗ дополнительных кнопок
                await self.telegram.send_message(
                    chat_id,
                    f"✅ Файл .{format_type} готов!\n\n💡 Исходное меню остается активным."
                )
            else:
                await self.telegram.send_message(
                    chat_id,
                    f"❌ Ошибка создания файла .{format_type}. Попробуйте другой формат."
                )

        except Exception as e:
            logger.error(f"Ошибка экспорта в формат {format_type}: {e}", exc_info=True)
            await self.telegram.send_message(chat_id, "❌ Произошла ошибка при создании файла")

    async def _handle_export_all(self, transcription_id: str, chat_id: int, user: dict):
        """Экспорт всех форматов - РАБОЧАЯ версия"""
        try:
            # Получаем данные транскрипции
            transcription = await self.db.get_transcription(transcription_id)
            if not transcription:
                await self.telegram.send_message(chat_id, "❌ Транскрипция не найдена")
                return

            # Получаем данные аудио файла
            audio_file = await self.db.get_audio_file(transcription['audio_file_id'])

            # Подготавливаем данные для экспорта
            export_data = {
                'text': transcription['text'],
                'language': transcription['language'],
                'created_at': transcription.get('created_at'),
                'duration_seconds': audio_file.get('duration_seconds', 0) if audio_file else 0,
                'file_size_mb': audio_file.get('file_size_mb', 0) if audio_file else 0
            }

            await self.telegram.send_message(chat_id, "📦 Создаю все форматы...")

            # Показываем какие форматы доступны
            available_formats = self.export_service.get_available_formats()
            available_list = []
            for fmt, available in available_formats.items():
                if available:
                    available_list.append(f"✅ .{fmt}")
                else:
                    available_list.append(f"❌ .{fmt} (нужны зависимости)")

            await self.telegram.send_message(
                chat_id,
                f"📋 Доступные форматы:\n" + "\n".join(available_list)
            )

            # Создаем архив со всеми форматами
            archive_path = await self.export_service.export_all_formats(export_data)

            if archive_path and os.path.exists(archive_path):
                # Отправляем архив
                await self._send_file_to_user(chat_id, archive_path, 'zip')

                await self.telegram.send_message(
                    chat_id,
                    "✅ Все доступные форматы упакованы в архив!"
                )
            else:
                await self.telegram.send_message(
                    chat_id,
                    "❌ Ошибка создания архива. Попробуйте экспортировать форматы по отдельности."
                )

        except Exception as e:
            logger.error(f"Ошибка экспорта всех форматов: {e}", exc_info=True)
            await self.telegram.send_message(chat_id, "❌ Произошла ошибка при создании файлов")

    async def _send_file_to_user(self, chat_id: int, file_path: str, format_type: str):
        """Отправка файла пользователю через Telegram"""
        try:
            # Определяем MIME тип
            mime_types = {
                'txt': 'text/plain',
                'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'pdf': 'application/pdf',
                'srt': 'text/plain',
                'zip': 'application/zip'
            }

            mime_type = mime_types.get(format_type, 'application/octet-stream')
            filename = os.path.basename(file_path)

            # Читаем файл
            async with aiofiles.open(file_path, 'rb') as f:
                file_data = await f.read()

            # Отправляем через Telegram API
            files = {
                'document': (filename, file_data, mime_type)
            }

            data = {
                'chat_id': chat_id,
                'caption': f"📄 Экспорт транскрипции (.{format_type})"
            }

            # Отправляем файл
            response = await self.telegram.client.post(
                f"{self.telegram.base_url}/sendDocument",
                data=data,
                files=files
            )

            if response.status_code == 200:
                logger.info(f"✅ Файл {filename} успешно отправлен пользователю {chat_id}")

                # Удаляем временный файл
                try:
                    os.remove(file_path)
                    logger.debug(f"Временный файл удален: {file_path}")
                except Exception as cleanup_error:
                    logger.warning(f"Не удалось удалить временный файл: {cleanup_error}")
            else:
                logger.error(f"Ошибка отправки файла: {response.status_code} - {response.text}")
                raise Exception(f"Telegram API error: {response.status_code}")

        except Exception as e:
            logger.error(f"Ошибка отправки файла {file_path}: {e}")
            await self.telegram.send_message(
                chat_id,
                "❌ Файл создан, но не удалось его отправить. Попробуйте еще раз."
            )

    async def _handle_insufficient_balance(self, required_minutes: int, chat_id: int, user: dict):
        """Обработка недостатка баланса для ТРАНСКРИПЦИИ"""
        current_balance = user.get('balance_minutes', 0)

        message = f"""⚠️ Недостаточно баланса для ТРАНСКРИПЦИИ

💰 Нужно: {required_minutes} мин
💳 У вас: {current_balance:.1f} мин
📉 Не хватает: {required_minutes - current_balance:.1f} мин

✨ Зато ОБРАБОТКА текста всегда бесплатна!
💎 Купите минуты только для транскрипции:"""

        keyboard = create_subscription_keyboard(user.get('plan', 'trial'), current_balance)
        await self.telegram.send_message(chat_id, message, reply_markup=keyboard)

    async def _handle_subscription(self, action: str, chat_id: int, message_id: Optional[int], user: dict):
        """Обработка подписок - с сохранением меню"""
        try:
            if action == 'main':
                current_plan = user.get('plan', 'trial')
                current_balance = user.get('balance_minutes', 0)

                keyboard = create_subscription_keyboard(current_plan, current_balance)

                plan_info = SUBSCRIPTION_PLANS.get(current_plan, SUBSCRIPTION_PLANS['trial'])

                text = f"""💎 Управление подпиской

🔹 Текущий план: {plan_info['name']}
💰 Баланс транскрипции: {current_balance:.1f} мин

✨ Обработка текста всегда бесплатна!

Выберите тариф для транскрипции:"""

                # ОТПРАВЛЯЕМ ОТДЕЛЬНЫМ сообщением
                await self.telegram.send_message(chat_id, text, reply_markup=keyboard)
                logger.info(f"✅ Меню подписки отправлено отдельным сообщением для chat_id {chat_id}")

        except Exception as e:
            logger.error(f"❌ Ошибка в _handle_subscription: {e}", exc_info=True)
            await self.telegram.send_message(chat_id, "❌ Произошла ошибка при загрузке меню подписки")

    async def _handle_buy_plan(self, plan_key: str, chat_id: int, user: dict):
        """Покупка плана"""
        plan_info = SUBSCRIPTION_PLANS.get(plan_key)
        if not plan_info:
            await self.telegram.send_message(chat_id, "❌ Неизвестный тариф")
            return

        # Заглушка для оплаты
        message = f"""💳 Оплата тарифа «{plan_info['name']}»

💰 Стоимость: {plan_info['price_rub']}₽
⏱️ Получите: {plan_info['minutes']} минут транскрипции

✨ Плюс безлимитная обработка текста!

🚧 Система оплаты находится в разработке.
Обратитесь к @your_support для активации тарифа."""

        await self.telegram.send_message(chat_id, message)

    async def _handle_install_deps(self, format_type: str, chat_id: int):
        """Информация об установке зависимостей для форматов"""
        install_commands = {
            'docx': 'pip install python-docx',
            'pdf': 'pip install reportlab'
        }

        format_names = {
            'docx': 'Word документов',
            'pdf': 'PDF файлов'
        }

        command = install_commands.get(format_type, '')
        format_name = format_names.get(format_type, format_type)

        message = f"""💡 Для экспорта {format_name} нужны дополнительные библиотеки

🔧 **Команда для установки:**
```
{command}
```

📚 **Что это даст:**
• Красивое форматирование
• Метаданные файла
• Профессиональный вид

После установки перезапустите бота и формат станет доступен!"""

        await self.telegram.send_message(chat_id, message)

    async def _handle_processing_info(self, chat_id: int, user: dict):
        """Информация о бесплатной обработке - ОТДЕЛЬНЫМ сообщением"""
        message = """💡 Подсказка по ценам:

💰 ТРАНСКРИПЦИЯ (речь → текст) = платно
✨ ОБРАБОТКА ТЕКСТА = всегда бесплатна!

🎯 Создавайте сколько угодно:
• 📋 Протоколы совещаний
• 📱 Instagram посты  
• 🎓 Конспекты лекций
• 🌍 Переводы на любые языки
• 📊 Отчеты и аналитику
• И многое другое!

Платите только за превращение речи в текст! 🎤→📝"""

        await self.telegram.send_message(chat_id, message)

    async def _handle_clear_selections(self, transcription_id: str, chat_id: int,
                                       message_id: Optional[int], user: dict):
        """Очистка всех выбранных опций"""
        try:
            user_id = user.get('telegram_id')

            # Очищаем выбранные форматы
            if user_id in self.user_selections:
                if transcription_id in self.user_selections[user_id]:
                    self.user_selections[user_id][transcription_id].clear()

            # Обновляем главное меню без выбранных опций
            user_balance = user.get('balance_minutes', 0)
            keyboard = create_post_transcription_keyboard_with_selections(
                transcription_id, user_balance, set()
            )

            text = """🎯 Что делаем дальше?

✨ ВСЯ ОБРАБОТКА БЕСПЛАТНА!
Выберите нужный формат:

🗑️ Выбранные опции очищены."""

            if message_id is not None:
                try:
                    await self.telegram.edit_message_text(chat_id, message_id, text, reply_markup=keyboard)
                    logger.info(f"✅ Выбранные опции очищены для chat_id {chat_id}")
                    return
                except Exception as edit_error:
                    logger.warning(f"Не удалось отредактировать сообщение: {edit_error}")

            await self.telegram.send_message(chat_id, text, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"❌ Ошибка в _handle_clear_selections: {e}", exc_info=True)
            await self.telegram.send_message(chat_id, "❌ Произошла ошибка при очистке выбранных опций")

    async def _handle_old_commands(self, command: str, parts: list, chat_id: int, message_id: Optional[int],
                                   user: dict):
        """Обработка старых команд для совместимости"""
        try:
            if command == 'start':
                await self.start_handler._handle_start_command(chat_id, user)
            elif command == 'settings':
                await self.start_handler._handle_settings_command(chat_id, user)
            elif command == 'balance':
                await self.start_handler._handle_balance_command(chat_id, user)
            elif command == 'help':
                await self.start_handler._handle_help_command(chat_id, user)
        except Exception as e:
            logger.error(f"❌ Ошибка в обработке старой команды {command}: {e}", exc_info=True)
            await self.telegram.send_message(chat_id, "❌ Произошла ошибка при обработке команды")

    async def _handle_promo_callbacks(self, parts: list, chat_id: int, message_id: Optional[int], user: dict):
        """Обработка callback'ов промокодов"""
        try:
            action = parts[1] if len(parts) > 1 else 'help'

            if action == 'help':
                help_text = """🎫 **Промокоды**

📝 **Как использовать:**
• Отправьте код прямо в чат
• Или используйте `/promo КОД`

💡 **Доступные коды:**
• `ADMIN500` - 500 минут PRO
• `WELCOME100` - 100 минут Starter  
• `TEST50` - 50 минут Trial

🎯 Просто отправьте промокод в чат!"""

                keyboard = {
                    "inline_keyboard": [
                        [{"text": "💰 Мой баланс", "callback_data": "balance:main"}],
                        [{"text": "🔙 Назад", "callback_data": "start"}]
                    ]
                }

                if message_id:
                    try:
                        await self.telegram.edit_message_text(chat_id, message_id, help_text, reply_markup=keyboard)
                        return
                    except Exception:
                        pass

                await self.telegram.send_message(chat_id, help_text, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Ошибка в обработке промокодов: {e}", exc_info=True)
            await self.telegram.send_message(chat_id, "❌ Произошла ошибка при обработке промокода")

    async def _handle_format_info(self, format_key: str, chat_id: int, user: dict):
        """Показать информацию о конкретном формате"""
        if not self.format_processor:
            await self.telegram.send_message(chat_id, "❌ Сервис обработки недоступен")
            return

        format_info = self.format_processor.get_format_info(format_key)
        if not format_info:
            await self.telegram.send_message(chat_id, f"❌ Неизвестный формат: {format_key}")
            return

        message = f"""📋 Информация о формате:

**{format_info['name']}**
{format_info['description']}

🔑 Ключ: `{format_info['key']}`
✨ Обработка бесплатна!"""

        await self.telegram.send_message(chat_id, message)

    # ДОПОЛНИТЕЛЬНЫЕ МЕТОДЫ для работы с новым FormatProcessor

    def get_available_formats_info(self) -> Dict[str, str]:
        """Получить информацию о всех доступных форматах"""
        if not self.format_processor:
            return {}
        return self.format_processor.get_available_formats()

    def is_format_supported(self, format_key: str) -> bool:
        """Проверить, поддерживается ли формат"""
        if not self.format_processor:
            return False
        return self.format_processor.is_format_supported(format_key)