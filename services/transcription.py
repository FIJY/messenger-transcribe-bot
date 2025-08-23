# services/transcription.py - ИСПРАВЛЕННАЯ версия с правильной очисткой файлов
import logging
import asyncio
import os
import sys
import gc
import base64
import tempfile
from typing import Dict, Any

# Добавляем текущую директорию в путь Python
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from openai import AsyncOpenAI
from celery import Celery
from config import settings

# Импорты для IDE (предварительные объявления)
try:
    from services.database import DatabaseService
    from services.audio_processor import AudioProcessor
    from services.telegram_client import TelegramClient
    from ui.localization import LocalizationService
    from ui.keyboards import create_post_transcription_keyboard
except ImportError:
    # Эти импорты выполняются внутри функций при необходимости
    DatabaseService = None
    AudioProcessor = None
    TelegramClient = None
    LocalizationService = None
    create_post_transcription_keyboard = None

logger = logging.getLogger(__name__)


class TranscriptionService:
    """Сервис для транскрипции аудио через OpenAI Whisper"""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("OpenAI API key is required")
        self.client = AsyncOpenAI(
            api_key=api_key,
            timeout=180.0,  # 3 минуты для стабильности
            max_retries=2
        )
        logger.info("🎤 TranscriptionService инициализирован")

    async def transcribe_audio(self, file_path: str) -> Dict[str, Any]:
        """Транскрибирует аудио файл с оптимизацией памяти"""
        try:
            file_size = os.path.getsize(file_path)
            max_size = 25 * 1024 * 1024  # 25MB лимит OpenAI
            if file_size > max_size:
                return {
                    'success': False,
                    'error': f'Файл слишком большой: {file_size / 1024 / 1024:.1f}MB. Максимум: 25MB для OpenAI Whisper',
                    'text': '',
                    'language': 'unknown',
                    'duration': None
                }

            logger.info(f"🎤 Начинаю транскрипцию: {file_path} ({file_size / 1024 / 1024:.1f}MB)")

            with open(file_path, "rb") as audio_file:
                transcript = await self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    temperature=0
                )

            result = {
                'success': True,
                'text': transcript.text.strip(),
                'language': getattr(transcript, 'language', 'unknown'),
                'duration': getattr(transcript, 'duration', None)
            }

            logger.info(f"✅ Транскрипция завершена: {len(result['text'])} символов")
            gc.collect()
            return result

        except Exception as e:
            logger.error(f"❌ Ошибка транскрипции: {e}", exc_info=True)
            gc.collect()
            return {
                'success': False,
                'error': str(e),
                'text': '',
                'language': 'unknown',
                'duration': None
            }

    async def close(self):
        """Закрываем соединения для освобождения памяти"""
        if hasattr(self, 'client'):
            await self.client.close()


# Настройки Celery для гибридного подхода
celery_app = Celery(
    'transcription_tasks',
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=['services.transcription']
)

# Настройки оптимизированные под Redis Starter (256MB)
celery_app.conf.update(
    # Базовые настройки
    task_track_started=True,
    worker_hijack_root_logger=False,
    worker_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
    worker_task_log_format='[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s',

    # Лимиты для экономии памяти
    task_soft_time_limit=1800,  # 30 минут мягкий лимит
    task_time_limit=3600,  # 60 минут жесткий лимит

    # Настройки очереди
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,

    # Сериализация с сжатием для экономии Redis
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    task_compression='gzip',  # Сжатие для Redis Starter
    result_compression='gzip',

    # Быстрое истечение результатов
    result_expires=3600,  # 1 час
    task_ignore_result=False,

    # Настройки подключения к Redis
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=5,

    # Оптимизация транспорта для Redis Starter
    broker_transport_options={
        'max_connections': 20,  # Под лимит 250 connections
        'retry_on_timeout': True,
        'socket_timeout': 20,
    }
)


@celery_app.task(name="process_transcription_task", bind=True)
def process_transcription_task(self, chat_id: int, user_id: int, enhanced_file_info: dict):
    """🚨 ИСПРАВЛЕННАЯ задача для всех файлов с правильной очисткой"""
    try:
        file_size_mb = enhanced_file_info.get('file_size', 0) / (1024 * 1024)
        processing_method = enhanced_file_info.get('processing_method', 'unknown')

        logger.info(f"🚨 ИСПРАВЛЕННАЯ обработка файла: {file_size_mb:.1f}MB, метод: {processing_method}")

        self.update_state(state='PROGRESS', meta={
            'progress': 0,
            'status': f'Обработка файла {file_size_mb:.1f}MB ({processing_method})...'
        })

        result = asyncio.run(
            _async_process_file_fixed(self, chat_id, user_id, enhanced_file_info)
        )

        gc.collect()
        return result

    except Exception as e:
        logger.critical(f"Критическая ошибка в обработке файла: {e}", exc_info=True)

        try:
            asyncio.run(_notify_user_error(chat_id, str(e)))
        except Exception as notify_error:
            logger.error(f"Не удалось уведомить пользователя: {notify_error}")

        gc.collect()
        return {"status": "error", "error": str(e)}


async def _async_process_file_fixed(task_instance, chat_id: int, user_id: int, enhanced_file_info: dict):
    """
    🚨 ИСПРАВЛЕННАЯ обработка всех файлов с улучшенной диагностикой и правильной очисткой
    """

    from services.database import DatabaseService
    from services.audio_processor import AudioProcessor
    from services.telegram_client import TelegramClient
    from ui.localization import LocalizationService
    from ui.keyboards import create_post_transcription_keyboard

    db_service = None
    telegram_client = None
    transcription_service = None
    audio_processor = AudioProcessor()
    localization_service = LocalizationService()

    temp_file_path = None
    processed_audio_path = None
    should_cleanup_file = False  # 🚨 ФЛАГ для контроля очистки

    try:
        task_instance.update_state(state='PROGRESS', meta={'progress': 5, 'status': 'Подготовка файла...'})

        processing_method = enhanced_file_info.get('processing_method', 'unknown')
        logger.info(f"🚨 Обработка через метод: {processing_method}")

        # 🔍 УЛУЧШЕННАЯ ДИАГНОСТИКА - проверяем все возможные ключи
        logger.info(f"🔍 Ищем файл в enhanced_file_info:")
        for key, value in enhanced_file_info.items():
            if 'path' in key.lower() or 'file' in key.lower() or 'content' in key.lower():
                if key == 'file_content_b64':
                    logger.info(f"  🔍 {key}: <base64 data, {len(value) if value else 0} символов>")
                else:
                    logger.info(f"  🔍 {key}: {value}")
                    if isinstance(value, str) and os.path.exists(value):
                        logger.info(f"    ✅ Файл существует!")
                    elif isinstance(value, str) and value.startswith('/'):
                        logger.warning(f"    ❌ Файл НЕ существует: {value}")

        # 🔹 Вариант 1: файл передан как base64 (Redis-режим)
        if 'file_content_b64' in enhanced_file_info:
            logger.info("📦 Декодируем файл из base64")
            file_content = base64.b64decode(enhanced_file_info['file_content_b64'])
            logger.info(f"Декодировано {len(file_content)} байт из base64")
            del enhanced_file_info['file_content_b64']
            gc.collect()

            file_extension = enhanced_file_info.get('original_extension', 'oga') or 'oga'
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}", dir='/tmp',
                                             prefix='small_file_') as tmp:
                tmp.write(file_content)
                temp_file_path = tmp.name
            del file_content
            gc.collect()
            should_cleanup_file = True  # 🚨 Нужно удалить временный файл

        # 🔹 Вариант 2: есть локальный путь к файлу (local_file_path)
        elif 'local_file_path' in enhanced_file_info:
            potential_path = enhanced_file_info['local_file_path']
            logger.info(f"📂 Проверяем local_file_path: {potential_path}")

            if os.path.exists(potential_path):
                temp_file_path = potential_path
                logger.info(f"✅ Используем локальный файл: {temp_file_path}")

                # 🚨 КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: Определяем нужна ли очистка
                if 'youtube_audio' in potential_path or enhanced_file_info.get('source') == 'youtube_audio':
                    should_cleanup_file = True  # YouTube файлы удаляем после обработки
                    logger.info("🗑️ YouTube файл - будет удален после обработки")
                else:
                    should_cleanup_file = False  # Обычные файлы не удаляем
                    logger.info("📁 Обычный файл - не будет удален")

            else:
                # Файл не существует - возможно удален после скачивания
                logger.error(f"❌ local_file_path не существует: {potential_path}")

                # Пытаемся найти файл в других местах
                possible_paths = [
                    potential_path,
                    potential_path.replace('/tmp/youtube_audio/', '/tmp/'),
                    f"/tmp/{os.path.basename(potential_path)}",
                    f"/tmp/youtube_audio/{enhanced_file_info.get('video_id', 'unknown')}.mp3"
                ]

                logger.info("🔍 Ищем файл в альтернативных местах:")
                for path in possible_paths:
                    logger.info(f"  Проверяем: {path}")
                    if os.path.exists(path):
                        temp_file_path = path
                        logger.info(f"  ✅ НАЙДЕН: {path}")
                        should_cleanup_file = True  # Найденный файл удаляем
                        break
                else:
                    # Файл совсем не найден
                    logger.error("❌ Файл не найден ни в одном из мест!")

                    # Показываем что есть в /tmp
                    logger.info("🔍 Содержимое /tmp:")
                    try:
                        for item in os.listdir('/tmp'):
                            if 'youtube' in item.lower() or enhanced_file_info.get('video_id', '') in item:
                                logger.info(f"  📄 {item}")
                    except Exception as e:
                        logger.error(f"Ошибка чтения /tmp: {e}")

        # 🔹 Вариант 3: проверяем другие возможные ключи для файла
        elif 'file_path' in enhanced_file_info and os.path.exists(enhanced_file_info['file_path']):
            temp_file_path = enhanced_file_info['file_path']
            logger.info(f"📂 Используем файл по пути file_path: {temp_file_path}")
            should_cleanup_file = False  # Обычные файлы не удаляем

        # 🔹 Вариант 4: проверяем shared_file_path
        elif 'shared_file_path' in enhanced_file_info:
            shared_path = enhanced_file_info['shared_file_path']
            if os.path.exists(shared_path):
                temp_file_path = shared_path
                logger.info(f"📂 Используем файл по пути shared_file_path: {temp_file_path}")
                should_cleanup_file = False
            else:
                # Это URL, пробуем скачать
                logger.info(f"🌐 shared_file_path является URL: {shared_path}")
                temp_file_path = await _download_file_from_url(shared_path)
                should_cleanup_file = True  # Скачанный файл удаляем

        else:
            # КРИТИЧЕСКАЯ СИТУАЦИЯ: файл точно должен быть, но не найден
            logger.critical("🚨 КРИТИЧЕСКАЯ СИТУАЦИЯ: файл не найден!")

            # Последняя попытка - найти любой файл с video_id
            video_id = enhanced_file_info.get('video_id')
            if video_id:
                logger.info(f"🔍 Последняя попытка: ищем файлы с video_id '{video_id}'")

                search_dirs = ['/tmp', '/tmp/youtube_audio']
                for search_dir in search_dirs:
                    if not os.path.exists(search_dir):
                        continue

                    for filename in os.listdir(search_dir):
                        if video_id in filename and filename.endswith(('.mp3', '.mp4', '.webm')):
                            found_path = os.path.join(search_dir, filename)
                            if os.path.exists(found_path):
                                temp_file_path = found_path
                                logger.info(f"🎯 НАЙДЕН файл: {found_path}")
                                should_cleanup_file = True
                                break

                    if temp_file_path:
                        break

            # Если всё еще не найден
            if not temp_file_path:
                # Показываем полную диагностику
                logger.error("❌ ФАЙЛ НЕ НАЙДЕН. Полная диагностика:")
                logger.error(f"  - Ожидаемый путь: {enhanced_file_info.get('local_file_path', 'НЕТ')}")
                logger.error(f"  - Video ID: {enhanced_file_info.get('video_id', 'НЕТ')}")
                logger.error(f"  - Размер файла: {enhanced_file_info.get('file_size', 0)} байт")

                raise ValueError(
                    f"ФАЙЛ НЕ НАЙДЕН! "
                    f"Ожидался: {enhanced_file_info.get('local_file_path', 'НЕИЗВЕСТНО')}. "
                    f"Возможно файл был удален после скачивания. "
                    f"Video ID: {enhanced_file_info.get('video_id', 'НЕИЗВЕСТНО')}"
                )

        # Финальная проверка что файл действительно существует
        if not temp_file_path or not os.path.exists(temp_file_path):
            raise ValueError(f"Файл не существует: {temp_file_path}")

        # Проверяем размер файла
        actual_size = os.path.getsize(temp_file_path)
        expected_size = enhanced_file_info.get('file_size', 0)

        logger.info(f"✅ Файл найден: {temp_file_path}")
        logger.info(f"📊 Размер файла: {actual_size} байт (ожидалось: {expected_size})")
        logger.info(f"🗑️ Будет удален после обработки: {should_cleanup_file}")

        if abs(actual_size - expected_size) > 1024:  # Разница больше 1KB
            logger.warning(f"⚠️ Размер файла не соответствует ожидаемому!")

        # 🔹 Далее идёт общая логика обработки
        await _common_transcription_processing_fixed(
            task_instance, chat_id, user_id, temp_file_path, enhanced_file_info,
            db_service, telegram_client, transcription_service, audio_processor,
            localization_service, should_cleanup_file
        )

        return {"status": "success", "processing_method": processing_method, "file_cleaned": should_cleanup_file}

    except Exception as e:
        logger.error(f"Ошибка в обработке файла: {e}", exc_info=True)

        # Отправляем детальную ошибку пользователю
        try:
            from services.telegram_client import TelegramClient
            temp_client = TelegramClient(settings.TELEGRAM_TOKEN)

            error_msg = "❌ Ошибка обработки файла:\n"
            if "не найден" in str(e) or "не существует" in str(e):
                error_msg += "• Файл был удален после скачивания\n• Попробуйте отправить ссылку еще раз"
            else:
                error_msg += f"• {str(e)[:200]}"

            await temp_client.send_message(chat_id, error_msg)
            await temp_client.close()
        except Exception as notify_error:
            logger.error(f"Не удалось уведомить пользователя: {notify_error}")

        return {"status": "error", "error": str(e)}

    finally:
        # 🚨 ИСПРАВЛЕННАЯ очистка ресурсов с правильным управлением файлами
        await _cleanup_resources_fixed(
            temp_file_path, processed_audio_path, should_cleanup_file,
            db_service, telegram_client, transcription_service
        )


async def _download_file_from_url(url: str) -> str:
    """Скачивает файл по URL и возвращает путь к временному файлу"""
    import aiohttp
    import tempfile

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()

                # Создаём временный файл
                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
                    async for chunk in response.content.iter_chunked(8192):
                        tmp_file.write(chunk)

                    logger.info(f"🔥 Файл скачан по URL: {tmp_file.name}")
                    return tmp_file.name

    except Exception as e:
        logger.error(f"❌ Ошибка скачивания файла по URL {url}: {e}")
        raise


async def _common_transcription_processing_fixed(task_instance, chat_id: int, user_id: int, file_path: str,
                                                 enhanced_file_info: dict, db_service, telegram_client,
                                                 transcription_service, audio_processor, localization_service,
                                                 should_cleanup_file: bool):
    """🚨 ИСПРАВЛЕННАЯ общая логика транскрипции с правильным управлением файлами"""

    processed_audio_path = None

    try:
        # Инициализация сервисов
        task_instance.update_state(state='PROGRESS', meta={'progress': 15, 'status': 'Подключение к сервисам...'})

        db_service = DatabaseService()
        await db_service.initialize()

        telegram_client = TelegramClient(settings.TELEGRAM_TOKEN)
        transcription_service = TranscriptionService(settings.OPENAI_API_KEY)

        # Получаем пользователя
        user = await db_service.get_user_by_telegram_id(user_id)
        if not user:
            raise ValueError("Пользователь не найден")

        lang = user.get('language', 'ru')

        # Валидация файла
        task_instance.update_state(state='PROGRESS', meta={'progress': 25, 'status': 'Проверяю файл...'})

        is_valid, validation_message = await audio_processor.validate_audio_file(
            file_path, max_size_mb=2048  # 2GB лимит
        )
        if not is_valid:
            raise ValueError(f"Файл не прошел валидацию: {validation_message}")

        # Обработка файла
        task_instance.update_state(state='PROGRESS', meta={'progress': 35, 'status': 'Конвертация файла...'})

        processed_audio_path = await audio_processor.process_file(file_path)
        if not processed_audio_path:
            raise ValueError("Ошибка обработки файла")

        # Транскрипция
        task_instance.update_state(state='PROGRESS', meta={'progress': 60, 'status': 'Транскрипция...'})

        transcription_result = await transcription_service.transcribe_audio(processed_audio_path)
        if not transcription_result.get('success'):
            raise Exception(f"Ошибка транскрипции: {transcription_result.get('error')}")

        # ИСПРАВЛЕННАЯ ВАЛИДАЦИЯ ТРАНСКРИПЦИИ
        text = transcription_result['text'].strip()
        language = transcription_result['language']

        # Функция для определения является ли символ китайским/японским/корейским
        def is_cjk_character(char):
            """Проверяет является ли символ китайским, японским или корейским"""
            return '\u4e00' <= char <= '\u9fff' or '\u3400' <= char <= '\u4dbf' or '\u20000' <= char <= '\u2a6df'

        # Считаем количество CJK символов в тексте
        cjk_count = sum(1 for char in text if is_cjk_character(char))
        total_chars = len(text)
        non_space_chars = len(text.replace(' ', ''))

        # Умная валидация в зависимости от языка и содержимого
        if total_chars == 0:
            raise ValueError("Транскрипция пустая")

        # Для текстов с китайскими/японскими/корейскими символами
        if cjk_count > 0:
            # Если больше половины символов - CJK, то даже 1-2 символа могут быть значимыми
            if cjk_count >= total_chars * 0.5:
                min_chars = 1  # Один иероглиф может быть словом
                logger.info(f"CJK текст обнаружен: {cjk_count} иероглифов из {total_chars}")
            else:
                min_chars = 2  # Смешанный текст
        else:
            # Для латинских языков нужно больше символов
            if language in ['ar', 'he']:
                min_chars = 2  # Арабский/иврит
            else:
                min_chars = 3  # Английский, русский и др.

        if non_space_chars < min_chars:
            raise ValueError(f"Транскрипция слишком короткая: {non_space_chars} символов (минимум {min_chars})")

        # Логирование результата
        logger.info(f"✅ Транскрипция принята: {total_chars} символов ({cjk_count} CJK), язык: {language}")
        if total_chars < 20:
            logger.info(f"🔍 Содержимое: '{text}'")

        # Сохранение в БД
        task_instance.update_state(state='PROGRESS', meta={'progress': 80, 'status': 'Сохранение...'})

        db_file = await db_service.create_audio_file(
            user_id=user_id,
            telegram_file_id=enhanced_file_info.get('file_id', 'unknown'),
            file_type=enhanced_file_info.get('original_extension', 'mp4'),
            duration_seconds=enhanced_file_info.get('duration', 0),
            file_size_mb=enhanced_file_info.get('file_size', 0) / (1024 * 1024)
        )

        db_transcription = await db_service.create_transcription(
            audio_file_id=db_file['id'],
            user_id=user_id,
            text=text,
            language=language,
            confidence=transcription_result.get('confidence')
        )

        # НОВАЯ МОДЕЛЬ: Списываем баланс ТОЛЬКО за транскрипцию
        transcription_cost = max(1, enhanced_file_info.get('duration', 0) // 60)  # Минимум 1 минута
        current_balance = user.get('balance_minutes', 0)
        new_balance = max(0, current_balance - transcription_cost)

        # Обновляем баланс пользователя
        await db_service.update_user(user_id, {'balance_minutes': new_balance})
        logger.info(f"💰 Списано {transcription_cost} мин за ТРАНСКРИПЦИЮ, остаток: {new_balance} мин")

        # Отправка результата с НОВЫМ UX
        task_instance.update_state(state='PROGRESS', meta={'progress': 95, 'status': 'Отправка результата...'})

        await _send_transcription_result_new_ux(
            telegram_client, chat_id, text, language,
            enhanced_file_info, new_balance, db_transcription['id']
        )

        task_instance.update_state(state='SUCCESS', meta={'progress': 100, 'status': 'Готово!'})

    except Exception as e:
        logger.error(f"Ошибка в общей обработке: {e}", exc_info=True)

        if telegram_client:
            await telegram_client.send_message(chat_id, "❌ Произошла ошибка при обработке файла.")

        raise e


async def _send_transcription_result_new_ux(telegram_client, chat_id: int, text: str, language: str,
                                            file_info: dict, user_balance: int, transcription_id: str):
    """
    НОВАЯ отправка результата с четким разделением платежей
    """
    from ui.keyboards import create_post_transcription_keyboard

    clean_text = text.replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')
    file_size_mb = file_info.get('file_size', 0) / (1024 * 1024)
    duration_seconds = file_info.get('duration', 0)

    # Определяем тип языка для правильной статистики
    is_cjk = language in ['zh', 'ja', 'ko']

    if is_cjk:
        stats_line = f"📊 Символов: {len(text)}"
    else:
        word_count = len(text.split())
        stats_line = f"📊 Слов: {word_count}"

    # Форматируем длительность
    if duration_seconds < 60:
        duration_str = f"{duration_seconds}с"
    elif duration_seconds < 3600:
        minutes = duration_seconds // 60
        seconds = duration_seconds % 60
        duration_str = f"{minutes}м {seconds}с" if seconds else f"{minutes}м"
    else:
        hours = duration_seconds // 3600
        minutes = (duration_seconds % 3600) // 60
        duration_str = f"{hours}ч {minutes}м" if minutes else f"{hours}ч"

    # НОВОЕ: Показываем что именно было оплачено
    transcription_cost = max(1, duration_seconds // 60)

    # Основное сообщение с результатом и четким разделением платежей
    result_header = f"""✅ Транскрипция готова!

📁 Размер: {file_size_mb:.1f}MB • ⏱️ {duration_str}
🌐 Язык: {language.upper()} • {stats_line}

💰 Списано за транскрипцию: {transcription_cost} мин
💳 Остаток баланса: {user_balance} мин
✨ Дальнейшая обработка БЕСПЛАТНО!"""

    # Добавляем подсказку для коротких текстов
    if len(text) < 15:
        if is_cjk:
            result_header += f"\n💡 Короткий текст нормален для {language.upper()}"
        else:
            result_header += f"\n💡 Для более длинного результата говорите громче"

    # Проверяем длину текста для отправки
    max_message_length = 3200  # Безопасный лимит для Telegram с учетом заголовка

    if len(clean_text) > max_message_length:
        # Длинный текст - отправляем заголовок отдельно
        await telegram_client.send_message(chat_id, result_header)

        # Разбиваем текст на части
        chunks = [clean_text[i:i + max_message_length] for i in range(0, len(clean_text), max_message_length)]

        for i, chunk in enumerate(chunks):
            chunk_message = f"📄 Часть {i + 1}/{len(chunks)}:\n\n{chunk}"
            await telegram_client.send_message(chat_id, chunk_message)

            # Пауза между частями
            if i < len(chunks) - 1:
                await asyncio.sleep(0.5)
    else:
        # Короткий текст - всё в одном сообщении
        full_message = f"""{result_header}

📁 Текст:
{clean_text}"""

        await telegram_client.send_message(chat_id, full_message)

    # ГЛАВНАЯ ФИШКА: отправляем клавиатуру с популярными форматами + акцент на бесплатность
    keyboard = create_post_transcription_keyboard(transcription_id, user_balance)

    menu_message = """🎯 Что делаем дальше?

✨ ВСЯ ОБРАБОТКА БЕСПЛАТНА!
Выберите нужный формат:"""

    await telegram_client.send_message(chat_id, menu_message, reply_markup=keyboard)


async def _cleanup_resources_fixed(temp_file_path, processed_audio_path, should_cleanup_file,
                                   db_service, telegram_client, transcription_service):
    """🚨 ИСПРАВЛЕННАЯ очистка ресурсов с правильным управлением файлами"""
    try:
        # 🚨 ИСПРАВЛЕНИЕ: Очистка файлов только когда нужно
        if should_cleanup_file and temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            logger.info(f"🧹 Удален файл: {temp_file_path}")
        elif temp_file_path:
            logger.info(f"📁 Файл сохранен (не удален): {temp_file_path}")

        if processed_audio_path and processed_audio_path != temp_file_path and os.path.exists(processed_audio_path):
            os.remove(processed_audio_path)
            logger.info(f"🧹 Удален обработанный файл: {processed_audio_path}")

        # Закрытие соединений
        if db_service:
            await db_service.close()
        if telegram_client:
            await telegram_client.close()
        if transcription_service:
            await transcription_service.close()

    except Exception as cleanup_error:
        logger.warning(f"Ошибка при очистке ресурсов: {cleanup_error}")

    # Принудительная очистка памяти
    gc.collect()


async def _notify_user_error(chat_id: int, error_message: str):
    """Уведомление пользователя об ошибке"""
    try:
        from services.telegram_client import TelegramClient
        temp_client = TelegramClient(settings.TELEGRAM_TOKEN)
        await temp_client.send_message(
            chat_id,
            "❌ Произошла ошибка при обработке файла. Пожалуйста, попробуйте еще раз."
        )
        await temp_client.close()
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя об ошибке: {e}")


# Остальные функции остаются без изменений...
# (get_transcription_status, cancel_transcription_task, test_openai_connection, etc.)

async def get_transcription_status(task_id: str) -> Dict[str, Any]:
    """Получает статус задачи транскрипции"""
    try:
        from celery.result import AsyncResult
        result = AsyncResult(task_id, app=celery_app)

        if result.ready():
            if result.successful():
                return {
                    'status': 'completed',
                    'result': result.get(),
                    'progress': 100
                }
            else:
                return {
                    'status': 'failed',
                    'error': str(result.info),
                    'progress': 0
                }
        else:
            # Задача еще выполняется
            meta = result.info if result.info else {}
            return {
                'status': 'processing',
                'progress': meta.get('progress', 0),
                'current_status': meta.get('status', 'Обработка...'),
                'meta': meta
            }

    except Exception as e:
        logger.error(f"Ошибка получения статуса задачи {task_id}: {e}")
        return {
            'status': 'error',
            'error': f'Ошибка получения статуса: {e}',
            'progress': 0
        }