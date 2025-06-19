# services/message_handler.py - Полная и финальная версия
import logging
import requests
import os
import tempfile
from typing import Dict, Any, Optional, List
from .media_handler import MediaHandler
from .database import Database
from .translation_service import TranslationService
from .audio_processor import AudioProcessor

logger = logging.getLogger(__name__)


class MessageHandler:
    def __init__(self, media_handler: MediaHandler, database: Database, translation_service: TranslationService):
        self.media_handler = media_handler
        self.database = database
        self.translation_service = translation_service
        self.audio_processor = AudioProcessor()  # Создаем экземпляр для утилит
        self.page_access_token = os.getenv('PAGE_ACCESS_TOKEN')
        # Лимиты для тестирования, как вы и указали
        self.FREE_DAILY_LIMIT = int(os.getenv('FREE_DAILY_LIMIT', '9999'))
        self.PREMIUM_DAILY_LIMIT = int(os.getenv('PREMIUM_DAILY_LIMIT', '9999'))

    def handle_message(self, webhook_event: Dict[str, Any]):
        """Главный обработчик входящих событий от Messenger."""
        sender_id = webhook_event.get('sender', {}).get('id')
        if not sender_id:
            logger.error("Отсутствует sender_id в событии")
            return

        user = self.database.get_user(sender_id)
        if not user:
            user = self.database.create_user(sender_id)
            self._send_welcome_message(sender_id)
            return

        if 'message' in webhook_event:
            message = webhook_event['message']

            # 1. Сначала проверяем нажатие на быструю кнопку
            if 'quick_reply' in message:
                payload = message['quick_reply'].get('payload')
                if payload:
                    self._handle_quick_reply(sender_id, payload, user)
                    return

            # 2. Проверяем лимиты перед обработкой файлов
            if not self._check_usage_limits(user) and 'attachments' in message:
                self._send_limit_exceeded_message(sender_id)
                return

            # 3. Обрабатываем вложения (аудио/видео)
            if 'attachments' in message:
                self._handle_attachments(sender_id, message['attachments'], user)
                return

            # 4. Обрабатываем текстовые сообщения
            if 'text' in message:
                self._handle_text_message(sender_id, message['text'])
                return

        # Если ничего из вышеперечисленного не подошло
        self._send_text_message(sender_id, "Отправьте аудио или видео файл для транскрипции.")

    def _handle_quick_reply(self, sender_id: str, payload: str, user: Dict[str, Any]):
        """Обрабатывает нажатия на быстрые ответы, включая бесшовный ретрай."""
        logger.info(f"User {sender_id} clicked quick reply: {payload}")

        if payload.startswith('RETRY_LANG_'):
            retry_info = self.database.get_retry_info(sender_id)
            if not retry_info or not retry_info.get('file_path'):
                self._send_text_message(sender_id,
                                        "❌ Не удалось найти файл для повторной обработки. Пожалуйста, отправьте его снова.")
                return

            file_to_retry = retry_info['file_path']
            if not os.path.exists(file_to_retry):
                self._send_text_message(sender_id, f"❌ Исходный файл уже удален. Пожалуйста, отправьте его снова.")
                return

            lang_code = payload.replace('RETRY_LANG_', '').lower()
            lang_names = {'km': 'Кхмерский', 'th': 'Тайский', 'vi': 'Вьетнамский', 'en': 'Английский'}
            lang_name = lang_names.get(lang_code, lang_code.upper())

            self._send_text_message(sender_id, f"✅ Понял! Повторно обрабатываю файл с языком: **{lang_name}**...")

            user['preferred_language'] = lang_code

            # Повторно обрабатываем ТОТ ЖЕ САМЫЙ файл
            result = self.media_handler.process_media(file_to_retry, user)

            if result.get('success'):
                new_response = self._format_transcription_response(result)
                self._send_text_message(sender_id, new_response)
            else:
                self._send_text_message(sender_id, f"❌ При повторной обработке произошла ошибка: {result.get('error')}")

            # Очистка после ретрая
            self.audio_processor.cleanup_temp_file(file_to_retry)
            self.database.store_retry_info(sender_id, {'file_path': None})  # Очищаем инфо
            return

        if payload == 'LANG_CORRECT':
            retry_info = self.database.get_retry_info(sender_id)
            if retry_info and retry_info.get('file_path'):
                self.audio_processor.cleanup_temp_file(retry_info['file_path'])
                self.database.store_retry_info(sender_id, {'file_path': None})
            self._send_text_message(sender_id, "👍 Отлично! Спасибо за подтверждение.")
            return

    def _handle_attachments(self, sender_id: str, attachments: List[Dict], user: Dict[str, Any]):
        """Обрабатывает вложения (аудио/видео файлы)."""
        if user.get('preferred_language'):
            self.database.set_user_language_preference(sender_id, None)
            user = self.database.get_user(sender_id)

        for attachment in attachments:
            if attachment.get('type') in ['audio', 'video']:
                original_file_path = self._download_file(attachment)
                if not original_file_path:
                    self._send_text_message(sender_id, "❌ Не удалось скачать файл.")
                    return

                self._process_media_file(sender_id, original_file_path, user)
                return
        self._send_text_message(sender_id, "Пожалуйста, отправьте поддерживаемый аудио или видео файл.")

    def _download_file(self, attachment: Dict) -> Optional[str]:
        """Скачивает файл и возвращает путь к нему."""
        try:
            file_url = attachment.get('payload', {}).get('url')
            if not file_url: return None

            headers = {'Authorization': f'Bearer {self.page_access_token}'}
            response = requests.get(file_url, headers=headers, stream=True, timeout=60)
            response.raise_for_status()

            # Сохраняем во временный файл
            with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as temp_file:
                temp_file_path = temp_file.name
                for chunk in response.iter_content(chunk_size=8192):
                    temp_file.write(chunk)
            return temp_file_path
        except requests.RequestException as e:
            logger.error(f"Ошибка при скачивании файла: {e}", exc_info=True)
            return None

    def _process_media_file(self, sender_id: str, file_path: str, user: Dict[str, Any]):
        """Обрабатывает локальный медиа файл."""
        try:
            self._send_processing_message(sender_id)

            is_valid, error_msg = self.media_handler.validate_file(file_path, user.get('is_premium', False))
            if not is_valid:
                self._send_text_message(sender_id, f"❌ {error_msg}")
                self.audio_processor.cleanup_temp_file(file_path)
                return

            result = self.media_handler.process_media(file_path, user)
            processed_audio_path = result.get('processed_audio_path')

            # Важно: не удаляем оригинальный файл, если он же является обработанным
            if file_path != processed_audio_path:
                self.audio_processor.cleanup_temp_file(file_path)

            if not result.get('success'):
                self._send_text_message(sender_id, f"❌ {result.get('error', 'Неизвестная ошибка')}")
                self.audio_processor.cleanup_temp_file(processed_audio_path)
                return

            self.database.save_transcription(user_id=sender_id, **result)
            self.database.increment_usage(user_id=sender_id)

            self._send_transcription_with_language_buttons(sender_id, result)
        except Exception as e:
            logger.error(f"Критическая ошибка при обработке файла: {e}", exc_info=True)
            self._send_text_message(sender_id, "❌ Произошла внутренняя ошибка.")
            if 'file_path' in locals() and file_path:
                self.audio_processor.cleanup_temp_file(file_path)
            if 'processed_audio_path' in locals() and processed_audio_path:
                self.audio_processor.cleanup_temp_file(processed_audio_path)

    def _send_transcription_with_language_buttons(self, sender_id: str, result: Dict[str, Any]):
        """Отправляет транскрипцию и, если нужно, кнопки для исправления языка."""
        response_text = self._format_transcription_response(result)
        processed_audio_path = result.get('processed_audio_path')

        if self._should_show_language_correction_buttons(result) and processed_audio_path:
            self.database.store_retry_info(sender_id, {'file_path': processed_audio_path})

            question = "\n\n🤔 Язык определен правильно? Если нет, выберите верный:"
            quick_replies = [
                {"content_type": "text", "title": "✅ Правильно", "payload": "LANG_CORRECT"},
                {"content_type": "text", "title": "🇰🇭 Кхмерский", "payload": "RETRY_LANG_KM"},
                {"content_type": "text", "title": "🇹🇭 Тайский", "payload": "RETRY_LANG_TH"},
                {"content_type": "text", "title": "🇻🇳 Вьетнамский", "payload": "RETRY_LANG_VI"},
            ]
            self._send_text_message(sender_id, response_text)
            self._send_message_with_quick_replies(sender_id, question, quick_replies)
        else:
            self._send_text_message(sender_id, response_text)
            if processed_audio_path:
                self.audio_processor.cleanup_temp_file(processed_audio_path)

    def _handle_text_message(self, sender_id: str, text: str):
        """Обрабатывает обычные текстовые сообщения."""
        text_lower = text.lower().strip()
        if any(keyword in text_lower for keyword in
               ['help', 'помощь', 'справка', '/start', 'start', 'привет', 'hello']):
            self._send_help_message(sender_id)
            return
        if any(keyword in text_lower for keyword in ['stats', 'статистика', 'лимит']):
            user = self.database.get_user(sender_id)  # Нужен актуальный user
            self._send_stats_message(sender_id, user)
            return

        response = "🎙️ Отправьте мне аудио или видео файл для транскрипции!"
        self._send_text_message(sender_id, response)

    def _should_show_language_correction_buttons(self, result: Dict[str, Any]) -> bool:
        """Определяет, нужно ли показывать кнопки исправления языка."""
        quality_analysis = result.get('quality_analysis', {})
        if quality_analysis.get('quality') in ['poor', 'mixed']:
            logger.info(f"Показываем кнопки из-за плохого качества: {quality_analysis.get('quality')}")
            return True
        return False

    def _format_transcription_response(self, result: Dict[str, Any]) -> str:
        """Форматирует ответ с результатами транскрипции."""
        detected_lang = result.get('detected_language', 'unknown')
        transcription = result.get('transcription', '')
        language_info = result.get('language_info', {})
        quality_analysis = result.get('quality_analysis', {})

        language_icons = {'km': '🇰🇭', 'th': '🇹🇭', 'vi': '🇻🇳', 'en': '🇺🇸', 'ru': '🇷🇺'}
        icon = language_icons.get(detected_lang, '🌐')
        lang_name = language_info.get('name', detected_lang.upper())

        response = f"🎯 **Язык:** {icon} {lang_name}\n\n"
        response += f"📝 **Транскрипция:**\n{transcription}"

        if quality_analysis.get('message') and 'успешно' not in quality_analysis.get('message', ''):
            response += f"\n\n{quality_analysis['message']}"
        return response

    def _check_usage_limits(self, user: Dict[str, Any]) -> bool:
        """Проверяет лимиты использования."""
        daily_usage = user.get('daily_usage', 0)
        is_premium = user.get('is_premium', False)
        limit = self.PREMIUM_DAILY_LIMIT if is_premium else self.FREE_DAILY_LIMIT
        return daily_usage < limit

    def _send_welcome_message(self, sender_id: str):
        """Отправляет приветственное сообщение."""
        message = "🎉 Добро пожаловать в Transcribe Bot! Просто отправьте мне аудио или видео файл."
        self._send_text_message(sender_id, message)

    def _send_help_message(self, sender_id: str):
        """Отправляет сообщение помощи."""
        message = "📖 **Справка:**\n• Отправьте аудио/видео для транскрипции.\n• 'stats' - статистика использования."
        self._send_text_message(sender_id, message)

    def _send_stats_message(self, sender_id: str, user: Dict[str, Any]):
        """Отправляет статистику пользователя."""
        daily_usage = user.get('daily_usage', 0)
        total_transcriptions = user.get('total_transcriptions', 0)
        is_premium = user.get('is_premium', False)
        limit = self.PREMIUM_DAILY_LIMIT if is_premium else self.FREE_DAILY_LIMIT
        remaining = max(0, limit - daily_usage)
        status = "💎 Premium" if is_premium else "🆓 Free"
        message = f"📊 **Статистика:**\n• Статус: {status}\n• Сегодня: {daily_usage}/{limit}\n• Осталось: {remaining}"
        self._send_text_message(sender_id, message)

    def _send_limit_exceeded_message(self, sender_id: str):
        """Отправляет сообщение о превышении лимита."""
        self._send_text_message(sender_id, "❌ Превышен дневной лимит. Лимиты сбрасываются в 00:00 UTC.")

    def _send_processing_message(self, sender_id: str):
        """Отправляет сообщение о начале обработки."""
        self._send_text_message(sender_id, "🎯 Обрабатываю ваш файл...")

    def _send_text_message(self, recipient_id: str, message_text: str):
        """Отправляет простое текстовое сообщение."""
        return self._send_api_request(recipient_id, {'text': message_text})

    def _send_message_with_quick_replies(self, recipient_id: str, text: str, quick_replies: List[Dict]):
        """Отправляет сообщение с быстрыми ответами."""
        message_data = {'text': text, 'quick_replies': quick_replies}
        return self._send_api_request(recipient_id, message_data)

    def _send_api_request(self, recipient_id: str, message_data: Dict) -> bool:
        """Централизованный метод для отправки запросов к Messenger API."""
        try:
            payload = {
                'recipient': {'id': recipient_id},
                'messaging_type': 'RESPONSE',
                'message': message_data,
                'access_token': self.page_access_token
            }
            response = requests.post(
                "https://graph.facebook.com/v18.0/me/messages",
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"Сообщение успешно отправлено пользователю {recipient_id}")
            return True
        except requests.RequestException as e:
            logger.error(f"Ошибка при отправке сообщения API: {e}", exc_info=True)
            if e.response:
                logger.error(f"Ответ API: {e.response.text}")
            return False