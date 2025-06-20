# services/message_handler.py - ФИНАЛЬНАЯ ВЕРСИЯ С ФУНКЦИЕЙ ПЕРЕВОДА
import logging
import requests
import os
import tempfile
from typing import Dict, Any, Optional, List

# Импорты ваших сервисов
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
        self.audio_processor = AudioProcessor()
        self.page_access_token = os.getenv('PAGE_ACCESS_TOKEN')
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

            if 'quick_reply' in message:
                payload = message['quick_reply'].get('payload')
                if payload:
                    self._handle_quick_reply(sender_id, payload, user)
                    return

            if not self._check_usage_limits(user) and 'attachments' in message:
                self._send_limit_exceeded_message(sender_id)
                return

            if 'attachments' in message:
                self._handle_attachments(sender_id, message['attachments'], user)
                return

            if 'text' in message:
                # Передаем весь объект user для доступа к его данным
                self._handle_text_message(sender_id, message['text'], user)
                return

        self._send_text_message(sender_id, "Отправьте аудио или видео файл для транскрипции.")

    # ... (методы _handle_quick_reply, _handle_attachments, и другие до _handle_text_message остаются без изменений)

    def _handle_text_message(self, sender_id: str, text: str, user: Dict[str, Any]):
        """Обрабатывает текстовые сообщения, включая команды."""
        text_lower = text.lower().strip()

        # 🔧 НОВОЕ: Проверяем, является ли сообщение запросом на перевод
        if self._is_translation_request(text_lower):
            self._handle_translation_request(sender_id, text)
            return

        if any(keyword in text_lower for keyword in ['help', 'помощь', 'справка', '/start']):
            self._send_help_message(sender_id)
            return

        if any(keyword in text_lower for keyword in ['stats', 'статистика', 'лимит']):
            self._send_stats_message(sender_id, user)
            return

        response = "🎙️ Отправьте мне аудио или видео файл для транскрипции!"
        self._send_text_message(sender_id, response)

    # 🔧 --- НОВЫЕ МЕТОДЫ ДЛЯ ПЕРЕВОДА --- 🔧

    def _is_translation_request(self, text: str) -> bool:
        """Проверяет, является ли текст запросом на перевод."""
        translation_keywords = ['translate', 'переведи', 'перевести', 'translation', 'перевод']
        return any(keyword in text for keyword in translation_keywords)

    def _extract_target_language(self, text: str) -> Optional[str]:
        """Извлекает целевой язык из текста запроса и возвращает его код."""
        text_lower = text.lower()
        # Карта языков: что может написать пользователь -> код языка
        language_mappings = {
            'english': 'en', 'английский': 'en', 'английский язык': 'en', 'на английский': 'en',
            'russian': 'ru', 'русский': 'ru', 'русский язык': 'ru', 'на русский': 'ru',
            'khmer': 'km', 'кхмерский': 'km', 'на кхмерский': 'km',
            'thai': 'th', 'тайский': 'th', 'на тайский': 'th',
            'vietnamese': 'vi', 'вьетнамский': 'vi', 'на вьетнамский': 'vi',
        }
        for keyword, code in language_mappings.items():
            if keyword in text_lower:
                return code
        return None

    def _handle_translation_request(self, sender_id: str, text: str):
        """Обрабатывает запрос на перевод последней транскрипции."""
        logger.info(f"Пользователь {sender_id} запросил перевод: {text}")

        last_transcription_doc = self.database.get_last_transcription(sender_id)
        if not last_transcription_doc or not last_transcription_doc.get('transcription'):
            self._send_text_message(sender_id, "❌ Нечего переводить. Сначала отправьте аудиофайл для транскрипции.")
            return

        original_text = last_transcription_doc['transcription']
        source_lang = last_transcription_doc['detected_language']
        target_lang = self._extract_target_language(text)

        if not target_lang:
            self._send_text_message(sender_id,
                                    "❌ Не могу понять, на какой язык перевести. Попробуйте, например: 'переведи на английский'.")
            return

        if target_lang == source_lang:
            self._send_text_message(sender_id, "🤔 Текст уже на этом языке!")
            return

        self._send_text_message(sender_id, f"✅ Принято! Перевожу на {target_lang.upper()}...")

        translation_result = self.translation_service.translate_text(original_text, target_lang, source_lang)

        if translation_result.get('success'):
            translated_text = translation_result['translated_text']
            response = f"🔄 **Перевод:**\n\n{translated_text}"
            self._send_text_message(sender_id, response)
        else:
            error = translation_result.get('error', 'неизвестная ошибка')
            self._send_text_message(sender_id, f"❌ Не удалось выполнить перевод. Ошибка: {error}")

    # ... (здесь должны быть все остальные ваши методы из message_handler.py)
    # Я скопирую их из нашей последней версии, чтобы файл был полным.

    def _handle_quick_reply(self, sender_id: str, payload: str, user: Dict[str, Any]):
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
            result = self.media_handler.process_media(file_to_retry, user)
            if result.get('success'):
                new_response = self._format_transcription_response(result)
                self._send_text_message(sender_id, new_response)
            else:
                self._send_text_message(sender_id, f"❌ При повторной обработке произошла ошибка: {result.get('error')}")
            self.audio_processor.cleanup_temp_file(file_to_retry)
            self.database.store_retry_info(sender_id, {'file_path': None})
            return
        if payload == 'LANG_CORRECT':
            retry_info = self.database.get_retry_info(sender_id)
            if retry_info and retry_info.get('file_path'):
                self.audio_processor.cleanup_temp_file(retry_info['file_path'])
                self.database.store_retry_info(sender_id, {'file_path': None})
            self._send_text_message(sender_id, "👍 Отлично! Спасибо за подтверждение.")
            return

    def _handle_attachments(self, sender_id: str, attachments: List[Dict], user: Dict[str, Any]):
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
        try:
            file_url = attachment.get('payload', {}).get('url')
            if not file_url: return None
            headers = {'Authorization': f'Bearer {self.page_access_token}'}
            response = requests.get(file_url, headers=headers, stream=True, timeout=60)
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as temp_file:
                temp_file_path = temp_file.name
                for chunk in response.iter_content(chunk_size=8192):
                    temp_file.write(chunk)
            return temp_file_path
        except requests.RequestException as e:
            logger.error(f"Ошибка при скачивании файла: {e}", exc_info=True)
            return None

    def _process_media_file(self, sender_id: str, file_path: str, user: Dict[str, Any]):
        try:
            self._send_processing_message(sender_id)
            is_valid, error_msg = self.media_handler.validate_file(file_path, user.get('is_premium', False))
            if not is_valid:
                self._send_text_message(sender_id, f"❌ {error_msg}")
                self.audio_processor.cleanup_temp_file(file_path)
                return
            result = self.media_handler.process_media(file_path, user)
            processed_audio_path = result.get('processed_audio_path')
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
            if 'file_path' in locals() and file_path: self.audio_processor.cleanup_temp_file(file_path)
            if 'processed_audio_path' in locals() and processed_audio_path: self.audio_processor.cleanup_temp_file(
                processed_audio_path)

    def _send_transcription_with_language_buttons(self, sender_id: str, result: Dict[str, Any]):
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

    def _should_show_language_correction_buttons(self, result: Dict[str, Any]) -> bool:
        quality_analysis = result.get('quality_analysis', {})
        if quality_analysis.get('quality') in ['poor', 'mixed']:
            logger.info(f"Показываем кнопки из-за плохого качества: {quality_analysis.get('quality')}")
            return True
        return False

    def _format_transcription_response(self, result: Dict[str, Any]) -> str:
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
        daily_usage = user.get('daily_usage', 0)
        is_premium = user.get('is_premium', False)
        limit = self.PREMIUM_DAILY_LIMIT if is_premium else self.FREE_DAILY_LIMIT
        return daily_usage < limit

    def _send_welcome_message(self, sender_id: str):
        self._send_text_message(sender_id, "🎉 Добро пожаловать! Отправьте аудио/видео файл для транскрипции.")

    def _send_help_message(self, sender_id: str):
        self._send_text_message(sender_id,
                                "📖 **Справка:**\n• Отправьте аудио/видео для транскрипции.\n• После транскрипции напишите 'переведи на ...' для перевода.\n• 'stats' - ваша статистика.")

    def _send_stats_message(self, sender_id: str, user: Dict[str, Any]):
        daily_usage = user.get('daily_usage', 0)
        limit = self.PREMIUM_DAILY_LIMIT if user.get('is_premium', False) else self.FREE_DAILY_LIMIT
        remaining = max(0, limit - daily_usage)
        self._send_text_message(sender_id,
                                f"📊 **Статистика:**\n• Использовано сегодня: {daily_usage}/{limit}\n• Осталось: {remaining}")

    def _send_limit_exceeded_message(self, sender_id: str):
        self._send_text_message(sender_id, "❌ Превышен дневной лимит. Лимиты сбрасываются в 00:00 UTC.")

    def _send_processing_message(self, sender_id: str):
        self._send_text_message(sender_id, "🎯 Обрабатываю ваш файл...")

    def _send_text_message(self, recipient_id: str, message_text: str):
        return self._send_api_request(recipient_id, {'text': message_text})

    def _send_message_with_quick_replies(self, recipient_id: str, text: str, quick_replies: List[Dict]):
        message_data = {'text': text, 'quick_replies': quick_replies}
        return self._send_api_request(recipient_id, message_data)

    def _send_api_request(self, recipient_id: str, message_data: Dict) -> bool:
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
            if e.response: logger.error(f"Ответ API: {e.response.text}")
            return False