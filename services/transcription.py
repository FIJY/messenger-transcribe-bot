# services/transcription.py - ПОЛНАЯ версия с новой моделью ценообразования
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
    # Эти импорты выполнятся внутри функций при необходимости
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
    """Задача для маленьких файлов через Redis (≤15MB)"""
    try:
        file_size_mb = enhanced_file_info.get('file_size', 0) / (1024 * 1024)
        logger.info(f"Обработка маленького файла: {file_size_mb:.1f}MB через Redis")

        self.update_state(state='PROGRESS', meta={
            'progress': 0,
            'status': f'Обработка файла {file_size_mb:.1f}MB через Redis...'
        })

        result = asyncio.run(
            _async_process_small_file(self, chat_id, user_id, enhanced_file_info)
        )

        gc.collect()
        return result

    except Exception as e:
        logger.critical(f"Критическая ошибка в обработке маленького файла: {e}", exc_info=True)

        try:
            asyncio.run(_notify_user_error(chat_id, str(e)))
        except Exception as notify_error:
            logger.error(f"Не удалось уведомить пользователя: {notify_error}")

        gc.collect()
        return {"status": "error", "error": str(e)}


@celery_app.task(name="process_large_file_task", bind=True)
def process_large_file_task(self, chat_id: int, user_id: int, enhanced_file_info: dict):
    """НОВАЯ задача для больших файлов через R2 (>15MB)"""
    try:
        file_size_mb = enhanced_file_info.get('file_size', 0) / (1024 * 1024)
        logger.info(f"Обработка большого файла: {file_size_mb:.1f}MB через R2")

        self.update_state(state='PROGRESS', meta={
            'progress': 0,
            'status': f'Скачивание файла {file_size_mb:.1f}MB из R2...'
        })

        result = asyncio.run(
            _async_process_large_file(self, chat_id, user_id, enhanced_file_info)
        )

        gc.collect()
        return result

    except Exception as e:
        logger.critical(f"Критическая ошибка в обработке большого файла: {e}", exc_info=True)

        # Очистка не нужна для R2 - файлы остаются в облаке
        # Только уведомляем пользователя
        try:
            asyncio.run(_notify_user_error(chat_id, str(e)))
        except Exception as notify_error:
            logger.error(f"Не удалось уведомить пользователя: {notify_error}")

        gc.collect()
        return {"status": "error", "error": str(e)}


async def _async_process_small_file(task_instance, chat_id: int, user_id: int, enhanced_file_info: dict):
    """Обработка маленьких файлов через Redis (base64) или локально, если base64 отсутствует"""

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

    try:
        task_instance.update_state(state='PROGRESS', meta={'progress': 5, 'status': 'Подготовка файла...'})

        # 🔹 Вариант 1: файл передан как base64 (Redis-режим)
        if 'file_content_b64' in enhanced_file_info:
            file_content = base64.b64decode(enhanced_file_info['file_content_b64'])
            logger.info(f"Декодировано {len(file_content)} байт из base64")
            del enhanced_file_info['file_content_b64']
            gc.collect()

            file_extension = enhanced_file_info.get('original_extension', 'oga') or 'oga'
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}", dir='/tmp', prefix='small_file_') as tmp:
                tmp.write(file_content)
                temp_file_path = tmp.name
            del file_content
            gc.collect()

        # 🔹 Вариант 2: base64 нет, но есть локальный путь
        elif 'local_file_path' in enhanced_file_info and os.path.exists(enhanced_file_info['local_file_path']):
            temp_file_path = enhanced_file_info['local_file_path']
            logger.warning(f"⚠️ base64 отсутствует, использую локальный файл: {temp_file_path}")

        else:
            raise ValueError("Файл не найден: отсутствует base64 и local_file_path")

        # 🔹 Дальше идёт общая логика
        await _common_transcription_processing(
            task_instance, chat_id, user_id, temp_file_path, enhanced_file_info,
            db_service, telegram_client, transcription_service, audio_processor, localization_service
        )

        return {"status": "success", "processing_method": "redis", "file_type": "small"}

    except Exception as e:
        logger.error(f"Ошибка в обработке маленького файла: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}

    finally:
        await _cleanup_resources(temp_file_path, processed_audio_path,
                                 db_service, telegram_client, transcription_service)


async def _async_process_large_file(task, chat_id: int, user_id: int, enhanced_file_info: dict):
    """Асинхронная обработка большого файла из R2"""
    import tempfile
    import requests

    # Получаем R2 URL вместо локального пути
    r2_url = enhanced_file_info.get('shared_file_path')  # Теперь это R2 URL
    if not r2_url:
        raise ValueError("R2 URL не найден в enhanced_file_info")

    # Создаем временный файл для скачивания
    temp_file = None
    try:
        # Обновляем прогресс
        task.update_state(state='PROGRESS', meta={
            'progress': 10,
            'status': 'Скачивание файла из облачного хранилища...'
        })

        # Скачиваем файл из R2
        logger.info(f"📥 Скачивание из R2: {r2_url}")

        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_f:
            temp_file = tmp_f.name

            response = requests.get(r2_url, timeout=300, stream=True)
            response.raise_for_status()

            # Скачиваем с отображением прогресса
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    tmp_f.write(chunk)
                    downloaded += len(chunk)

                    # Обновляем прогресс скачивания (10-30%)
                    if total_size > 0:
                        progress = 10 + int((downloaded / total_size) * 20)
                        task.update_state(state='PROGRESS', meta={
                            'progress': progress,
                            'status': f'Скачивание: {progress-10}%'
                        })

        logger.info(f"✅ Файл скачан во временную папку: {temp_file}")

        # Обновляем прогресс
        task.update_state(state='PROGRESS', meta={
            'progress': 35,
            'status': 'Начинаем транскрипцию...'
        })

        # Инициализируем сервисы
        localization = LocalizationService()
        transcription_service = TranscriptionService()

        # Валидация файла
        validated_info = transcription_service.validate_file(temp_file)
        if not validated_info['valid']:
            raise ValueError(f"Файл не прошел валидацию: {validated_info['error']}")

        # Обновляем enhanced_file_info для локального файла
        local_file_info = enhanced_file_info.copy()
        local_file_info['file_path'] = temp_file
        local_file_info['shared_file_path'] = temp_file  # Для совместимости

        # Транскрипция
        task.update_state(state='PROGRESS', meta={
            'progress': 40,
            'status': 'Выполняется транскрипция...'
        })

        transcription_result = await transcription_service.transcribe_audio_async(
            temp_file,
            local_file_info,
            progress_callback=lambda p: task.update_state(
                state='PROGRESS',
                meta={'progress': 40 + int(p * 0.5), 'status': f'Транскрипция: {int(p)}%'}
            )
        )

        if not transcription_result.get('success'):
            raise ValueError(f"Ошибка транскрипции: {transcription_result.get('error')}")

        # Сохранение результатов в БД
        task.update_state(state='PROGRESS', meta={
            'progress': 90,
            'status': 'Сохранение результатов...'
        })

        # ... остальная логика сохранения в БД ...

        task.update_state(state='PROGRESS', meta={
            'progress': 100,
            'status': 'Завершено!'
        })

        return {
            'status': 'success',
            'processing_method': 'r2_cloud',
            'file_type': 'large',
            'transcription_id': str(transcription_result.get('transcription_id')),
            'text_length': len(transcription_result.get('text', '')),
            'r2_url': r2_url
        }

    except requests.RequestException as e:
        logger.error(f"❌ Ошибка скачивания из R2: {e}")
        raise ValueError(f"Не удалось скачать файл из облачного хранилища: {e}")

    except Exception as e:
        logger.error(f"❌ Ошибка обработки большого файла: {e}")
        raise

    finally:
        # Очищаем временный файл
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
                logger.info(f"🧹 Временный файл удален: {temp_file}")
            except Exception as cleanup_error:
                logger.warning(f"⚠️ Не удалось удалить временный файл: {cleanup_error}")

async def _common_transcription_processing(task_instance, chat_id: int, user_id: int, file_path: str,
                                           enhanced_file_info: dict, db_service, telegram_client,
                                           transcription_service, audio_processor, localization_service):
    """Общая логика транскрипции для маленьких и больших файлов с новой моделью ценообразования"""

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
            logger.info(f"📝 Содержимое: '{text}'")

        # Сохранение в БД
        task_instance.update_state(state='PROGRESS', meta={'progress': 80, 'status': 'Сохранение...'})

        db_file = await db_service.create_audio_file(
            user_id=user_id,
            telegram_file_id=enhanced_file_info['file_id'],
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

    # В services/transcription.py добавить:
    if file_info.get('processing_method') == 'local_file':
        # Читаем файл напрямую без скачивания
        local_file_path = file_info.get('local_file_path')
        if os.path.exists(local_file_path):
            # Обрабатываем файл напрямую
            process_audio_file(local_file_path)
        else:
            raise FileNotFoundError(f"Локальный файл не найден: {local_file_path}")

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
🌍 Язык: {language.upper()} • {stats_line}

💰 Списано за транскрипцию: {transcription_cost} мин
💳 Остаток баланса: {user_balance} мин
✨ Дальнейшая обработка БЕСПЛАТНА!"""

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

📝 Текст:
{clean_text}"""

        await telegram_client.send_message(chat_id, full_message)

    # ГЛАВНАЯ ФИШКА: отправляем клавиатуру с популярными форматами + акцент на бесплатность
    keyboard = create_post_transcription_keyboard(transcription_id, user_balance)

    menu_message = """🎯 Что делаем дальше?

✨ ВСЯ ОБРАБОТКА БЕСПЛАТНА!
Выберите нужный формат:"""

    await telegram_client.send_message(chat_id, menu_message, reply_markup=keyboard)


async def _send_full_transcription_text(telegram_client, chat_id: int, transcription_id: str,
                                        text: str, language: str, file_info: dict):
    """Отправка полного текста транскрипции при нажатии кнопки 'Показать полный текст'"""

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
    await telegram_client.send_message(chat_id, header)

    # Разбиваем текст если нужно
    max_length = 3800  # Оставляем место для форматирования

    if len(clean_text) > max_length:
        chunks = [clean_text[i:i + max_length] for i in range(0, len(clean_text), max_length)]

        for i, chunk in enumerate(chunks):
            await telegram_client.send_message(chat_id, chunk)
            if i < len(chunks) - 1:
                await asyncio.sleep(0.3)
    else:
        await telegram_client.send_message(chat_id, clean_text)

    # Кнопка возврата
    back_keyboard = {
        "inline_keyboard": [[
            {"text": "🔙 К выбору форматов", "callback_data": f"back_to_main:{transcription_id}"}
        ]]
    }

    await telegram_client.send_message(
        chat_id,
        "👆 Полный текст выше",
        reply_markup=back_keyboard
    )


async def _cleanup_resources(temp_file_path, processed_audio_path, db_service, telegram_client, transcription_service):
    """Очистка ресурсов"""
    try:
        # Очистка файлов
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        if processed_audio_path and processed_audio_path != temp_file_path and os.path.exists(processed_audio_path):
            os.remove(processed_audio_path)

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
            "❌ Произошла ошибка при обработке файла. Пожалуйте, попробуйте еще раз."
        )
        await temp_client.close()
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя об ошибке: {e}")


async def _notify_processing_is_free(chat_id: int, telegram_client):
    """Уведомление о том, что обработка бесплатна"""
    message = """💡 Подсказка:

💰 ТРАНСКРИПЦИЯ = платно (по минутам)
✨ ОБРАБОТКА ТЕКСТА = всегда бесплатна!

🎯 Создавайте сколько угодно:
• Протоколы совещаний
• Instagram посты  
• Конспекты лекций
• Переводы на любые языки
• И многое другое!

Плата только за превращение речи в текст! 🎤→📝"""

    await telegram_client.send_message(chat_id, message)