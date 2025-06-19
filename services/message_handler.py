import logging
import requests
import os
from typing import Dict, Any, Optional, List
from .media_handler import MediaHandler
from .database import Database
from .translation_service import TranslationService

logger = logging.getLogger(__name__)


class MessageHandler:
    def __init__(self, media_handler: MediaHandler, database: Database, translation_service: TranslationService):
        self.media_handler = media_handler
        self.database = database
        self.translation_service = translation_service
        self.page_access_token = os.getenv('PAGE_ACCESS_TOKEN')

        # Настройки лимитов
        self.FREE_DAILY_LIMIT = int(os.getenv('FREE_DAILY_LIMIT', '10'))
        self.PREMIUM_DAILY_LIMIT = int(os.getenv('PREMIUM_DAILY_LIMIT', '1000'))

    def handle_message(self, message_data: Dict[str, Any]) -> bool:
        """
        Обрабатывает входящее сообщение от пользователя

        Args:
            message_data: данные сообщения от Facebook

        Returns:
            True если сообщение обработано успешно
        """
        try:
            sender_id = message_data.get('sender', {}).get('id')
            message = message_data.get('message', {})

            if not sender_id:
                logger.error("Отсутствует sender_id в сообщении")
                return False

            logger.info(f"Обрабатываем сообщение от пользователя {sender_id}")

            # Получаем информацию о пользователе
            user = self.database.get_user(sender_id)
            if not user:
                user = self.database.create_user(sender_id)
                self._send_welcome_message(sender_id)
                return True

            # Проверяем лимиты
            if not self._check_usage_limits(user):
                self._send_limit_exceeded_message(sender_id, user)
                return True

            # Обрабатываем текстовые сообщения
            if 'text' in message:
                return self._handle_text_message(sender_id, message['text'], user)

            # Обрабатываем вложения (аудио/видео)
            if 'attachments' in message:
                return self._handle_attachments(sender_id, message['attachments'], user)

            # Неизвестный тип сообщения
            self._send_text_message(sender_id, "Извините, я понимаю только текстовые сообщения, аудио и видео файлы.")
            return True

        except Exception as e:
            logger.error(f"Ошибка при обработке сообщения: {e}")
            self._send_error_message(sender_id if 'sender_id' in locals() else None)
            return False

    def _handle_text_message(self, sender_id: str, text: str, user: Dict[str, Any]) -> bool:
        """
        Обрабатывает текстовые сообщения
        """
        text_lower = text.lower().strip()

        # Команды помощи
        if any(keyword in text_lower for keyword in ['help', 'помощь', 'справка', '/start']):
            self._send_help_message(sender_id)
            return True

        # Команды статистики
        if any(keyword in text_lower for keyword in ['stats', 'статистика', 'лимит']):
            self._send_stats_message(sender_id, user)
            return True

        # Команды перевода
        if self._is_translation_request(text_lower):
            return self._handle_translation_request(sender_id, text, user)

        # Обычное текстовое сообщение
        response = "🎙️ Отправьте мне аудио или видео файл для транскрипции!\n\n"
        response += "📝 Поддерживаемые форматы:\n"
        response += "• Аудио: MP3, WAV, OGG, M4A, AAC, FLAC\n"
        response += "• Видео: MP4, AVI, MOV, MKV, WEBM\n\n"
        response += "⏱️ Максимальная длительность: 5 минут"

        self._send_text_message(sender_id, response)
        return True

    def _handle_attachments(self, sender_id: str, attachments: List[Dict], user: Dict[str, Any]) -> bool:
        """
        Обрабатывает вложения (аудио/видео файлы)
        """
        for attachment in attachments:
            attachment_type = attachment.get('type')

            if attachment_type in ['audio', 'video']:
                return self._process_media_attachment(sender_id, attachment, user)
            elif attachment_type == 'file':
                # Проверяем, является ли файл медиа
                payload = attachment.get('payload', {})
                url = payload.get('url')
                if url and any(ext in url.lower() for ext in ['.mp3', '.wav', '.mp4', '.avi']):
                    return self._process_media_attachment(sender_id, attachment, user)

        self._send_text_message(sender_id, "Пожалуйста, отправьте аудио или видео файл для транскрипции.")
        return True

    def _process_media_attachment(self, sender_id: str, attachment: Dict, user: Dict[str, Any]) -> bool:
        """
        Обрабатывает медиа вложение
        """
        try:
            # Отправляем сообщение о начале обработки
            self._send_processing_message(sender_id)

            # Получаем URL файла
            payload = attachment.get('payload', {})
            file_url = payload.get('url')

            if not file_url:
                self._send_text_message(sender_id, "❌ Не удалось получить файл.")
                return False

            # Скачиваем и обрабатываем файл
            result = self._download_and_process_media(file_url, user.get('is_premium', False))

            if not result['success']:
                self._send_text_message(sender_id, f"❌ {result['error']}")
                return False

            # Сохраняем результат в базу данных
            self.database.save_transcription(
                user_id=sender_id,
                transcription=result['transcription'],
                detected_language=result['detected_language'],
                file_type=attachment.get('type', 'unknown')
            )

            # Увеличиваем счетчик использования
            self.database.increment_usage(sender_id)

            # Отправляем результат пользователю
            response = self._format_transcription_response(result)
            self._send_text_message(sender_id, response)

            # Предлагаем перевод если нужно
            self.send_translation_offer(sender_id, result, user)

            return True

        except Exception as e:
            logger.error(f"Ошибка при обработке медиа вложения: {e}")
            self._send_text_message(sender_id, "❌ Произошла ошибка при обработке файла.")
            return False

    def _download_and_process_media(self, file_url: str, is_premium: bool = False) -> Dict[str, Any]:
        """
        Скачивает и обрабатывает медиа файл
        """
        try:
            import tempfile
            import requests

            # Скачиваем файл
            headers = {'Authorization': f'Bearer {self.page_access_token}'}
            response = requests.get(file_url, headers=headers, timeout=30)
            response.raise_for_status()

            # Сохраняем во временный файл
            with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as temp_file:
                temp_file.write(response.content)
                temp_file_path = temp_file.name

            # Проверяем файл
            is_valid, error_msg = self.media_handler.validate_file(temp_file_path, is_premium)
            if not is_valid:
                os.remove(temp_file_path)
                return {'success': False, 'error': error_msg}

            # Обрабатываем файл
            result = self.media_handler.process_media(temp_file_path)

            return result

        except requests.RequestException as e:
            logger.error(f"Ошибка при скачивании файла: {e}")
            return {'success': False, 'error': 'Не удалось скачать файл'}
        except Exception as e:
            logger.error(f"Ошибка при обработке медиа: {e}")
            return {'success': False, 'error': f'Ошибка обработки: {str(e)}'}

    def _format_transcription_response(self, result: Dict[str, Any]) -> str:
        """
        Форматирует ответ с результатами транскрипции
        """
        detected_lang = result.get('detected_language', 'unknown')
        transcription = result.get('transcription', '')
        language_info = result.get('language_info', {})

        # Иконки для языков
        language_icons = {
            'km': '🇰🇭', 'th': '🇹🇭', 'vi': '🇻🇳', 'zh': '🇨🇳', 'ja': '🇯🇵',
            'ko': '🇰🇷', 'en': '🇺🇸', 'ru': '🇷🇺', 'fr': '🇫🇷', 'es': '🇪🇸',
            'de': '🇩🇪', 'ar': '🇸🇦'
        }

        icon = language_icons.get(detected_lang, '🌐')
        lang_name = language_info.get('name', detected_lang.upper())
        native_name = language_info.get('native', '')

        response = f"🎯 **Язык:** {icon} {lang_name}"
        if native_name and native_name != lang_name:
            response += f" ({native_name})"
        response += "\n\n📝 **Транскрипция:**\n" + transcription

        return response

    def send_translation_offer(self, sender_id: str, result: Dict[str, Any], user: Dict[str, Any]):
        """
        Предлагает перевод если подходящие условия
        """
        detected_lang = result.get('detected_language', 'unknown')
        user_lang = user.get('preferred_language', 'en')

        # Предлагаем перевод для азиатских языков
        if detected_lang in ['km', 'th', 'vi', 'zh', 'ja', 'ko'] and user_lang in ['en', 'ru']:
            suggestions = {
                'en': "💡 Need translation? Type 'translate to english'",
                'ru': "💡 Нужен перевод? Напишите 'перевести на русский'"
            }

            suggestion = suggestions.get(user_lang, suggestions['en'])
            self._send_text_message(sender_id, suggestion)

    def _handle_translation_request(self, sender_id: str, text: str, user: Dict[str, Any]) -> bool:
        """
        Обрабатывает запрос на перевод
        """
        # Получаем последнюю транскрипцию пользователя
        last_transcription = self.database.get_last_transcription(sender_id)

        if not last_transcription:
            self._send_text_message(sender_id, "❌ Нет транскрипции для перевода. Сначала отправьте аудио или видео.")
            return True

        # Определяем целевой язык
        target_lang = self._extract_target_language(text)
        if not target_lang:
            self._send_text_message(sender_id,
                                    "❌ Не удалось определить язык для перевода. Попробуйте: 'translate to english'")
            return True

        # Выполняем перевод
        try:
            translation = self.translation_service.translate_text(
                last_transcription['transcription'],
                last_transcription['detected_language'],
                target_lang
            )

            if translation:
                response = f"🔄 **Перевод на {target_lang.upper()}:**\n{translation}"
                self._send_text_message(sender_id, response)
            else:
                self._send_text_message(sender_id, "❌ Не удалось выполнить перевод.")

        except Exception as e:
            logger.error(f"Ошибка при переводе: {e}")
            self._send_text_message(sender_id, "❌ Произошла ошибка при переводе.")

        return True

    def _is_translation_request(self, text: str) -> bool:
        """
        Проверяет, является ли текст запросом на перевод
        """
        translation_keywords = [
            'translate', 'перевести', 'translation', 'перевод',
            'បកប្រែ', 'แปล', 'dịch', '翻译', '번역'
        ]
        return any(keyword in text for keyword in translation_keywords)

    def _extract_target_language(self, text: str) -> Optional[str]:
        """
        Извлекает целевой язык из текста запроса
        """
        text_lower = text.lower()

        language_mappings = {
            'english': 'en', 'английский': 'en', 'en': 'en',
            'russian': 'ru', 'русский': 'ru', 'ru': 'ru',
            'khmer': 'km', 'cambodian': 'km', 'кхмерский': 'km', 'km': 'km',
            'thai': 'th', 'тайский': 'th', 'th': 'th',
            'vietnamese': 'vi', 'вьетнамский': 'vi', 'vi': 'vi',
            'chinese': 'zh', 'китайский': 'zh', 'zh': 'zh'
        }

        for lang_name, lang_code in language_mappings.items():
            if lang_name in text_lower:
                return lang_code

        return None

    def _check_usage_limits(self, user: Dict[str, Any]) -> bool:
        """
        Проверяет лимиты использования
        """
        daily_usage = user.get('daily_usage', 0)
        is_premium = user.get('is_premium', False)

        limit = self.PREMIUM_DAILY_LIMIT if is_premium else self.FREE_DAILY_LIMIT

        return daily_usage < limit

    def _send_welcome_message(self, sender_id: str):
        """Отправляет приветственное сообщение"""
        message = """🎉 Добро пожаловать в Transcribe Bot!

🎙️ Я помогу вам транскрибировать аудио и видео файлы.

📝 **Что я умею:**
• Распознавание речи из аудио/видео
• Определение языка автоматически
• Поддержка 50+ языков
• Перевод на другие языки

🚀 **Просто отправьте мне аудио или видео файл!**

ℹ️ Лимит: 10 файлов в день (бесплатно)"""

        self._send_text_message(sender_id, message)

    def _send_help_message(self, sender_id: str):
        """Отправляет сообщение помощи"""
        message = """📖 **Справка по использованию:**

🎙️ **Отправьте аудио/видео** для транскрипции
📝 **Форматы:** MP3, WAV, OGG, M4A, AAC, FLAC, MP4, AVI, MOV, MKV, WEBM
⏱️ **Лимит времени:** 5 минут (бесплатно)

🔄 **Перевод:** Напишите "translate to [язык]" после транскрипции

📊 **Команды:**
• "stats" - статистика использования
• "help" - эта справка

💎 **Premium:** неограниченное использование до 60 минут"""

        self._send_text_message(sender_id, message)

    def _send_stats_message(self, sender_id: str, user: Dict[str, Any]):
        """Отправляет статистику пользователя"""
        daily_usage = user.get('daily_usage', 0)
        total_transcriptions = user.get('total_transcriptions', 0)
        is_premium = user.get('is_premium', False)

        limit = self.PREMIUM_DAILY_LIMIT if is_premium else self.FREE_DAILY_LIMIT
        remaining = max(0, limit - daily_usage)

        status = "💎 Premium" if is_premium else "🆓 Free"

        message = f"""📊 **Ваша статистика:**

👤 **Статус:** {status}
📈 **Использовано сегодня:** {daily_usage}/{limit}
🎯 **Осталось:** {remaining}
📝 **Всего транскрипций:** {total_transcriptions}

⏰ **Лимиты сбрасываются каждый день в 00:00 UTC**"""

        self._send_text_message(sender_id, message)

    def _send_limit_exceeded_message(self, sender_id: str, user: Dict[str, Any]):
        """Отправляет сообщение о превышении лимита"""
        is_premium = user.get('is_premium', False)

        if is_premium:
            message = "❌ Превышен дневной лимит Premium (1000 транскрипций)."
        else:
            message = """❌ **Превышен дневной лимит (10 транскрипций)**

💎 **Upgrade to Premium:**
• Неограниченные транскрипции
• Файлы до 60 минут  
• Приоритетная обработка

⏰ **Или подождите до завтра** - лимиты обновляются в 00:00 UTC"""

        self._send_text_message(sender_id, message)

    def _send_processing_message(self, sender_id: str):
        """Отправляет сообщение о начале обработки"""
        messages = [
            "🎯 Обрабатываю ваш файл...",
            "🎯 Processing your file...",
            "🎯 កំពុងដំណើរការ..."
        ]

        message = " / ".join(messages)
        self._send_text_message(sender_id, message)

    def _send_error_message(self, sender_id: Optional[str]):
        """Отправляет сообщение об ошибке"""
        if sender_id:
            message = "❌ Произошла ошибка. Попробуйте позже или обратитесь в поддержку."
            self._send_text_message(sender_id, message)

    def _send_text_message(self, recipient_id: str, message: str) -> bool:
        """
        Отправляет текстовое сообщение пользователю
        """
        try:
            url = f"https://graph.facebook.com/v17.0/me/messages"

            payload = {
                'recipient': {'id': recipient_id},
                'message': {'text': message},
                'access_token': self.page_access_token
            }

            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()

            logger.info(f"Сообщение отправлено пользователю {recipient_id}")
            return True

        except requests.RequestException as e:
            logger.error(f"Ошибка при отправке сообщения: {e}")
            return False
        except Exception as e:
            logger.error(f"Неожиданная ошибка при отправке сообщения: {e}")
            return False