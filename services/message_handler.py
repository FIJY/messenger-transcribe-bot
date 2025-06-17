# services/message_handler.py - с новой архитектурой
import os
import logging
import requests
from config.constants import FREE_DAILY_LIMIT, MAX_AUDIO_DURATION_FREE, MAX_AUDIO_DURATION_PREMIUM
from .media_handler import MediaHandler

logger = logging.getLogger(__name__)


class MessageHandler:
    def __init__(self, db, payment):
        self.db = db
        self.media_handler = MediaHandler()  # Используем новый MediaHandler
        self.payment = payment
        self.page_access_token = os.getenv('PAGE_ACCESS_TOKEN')
        self.graph_url = "https://graph.facebook.com/v17.0/me"

    def handle_webhook(self, data):
        """Обработка входящих webhook событий"""
        try:
            for entry in data.get('entry', []):
                for messaging_event in entry.get('messaging', []):
                    sender_id = messaging_event['sender']['id']

                    # Обработка текстовых сообщений
                    if 'message' in messaging_event and 'text' in messaging_event['message']:
                        self.handle_text_message(sender_id, messaging_event['message']['text'])

                    # Обработка аудио и видео
                    elif 'message' in messaging_event and 'attachments' in messaging_event['message']:
                        for attachment in messaging_event['message']['attachments']:
                            if attachment['type'] in ['audio', 'video']:
                                media_url = attachment['payload'].get('url')
                                if media_url:
                                    self.handle_media_message(sender_id, media_url, attachment['type'])

                    # Обработка postback (кнопок)
                    elif 'postback' in messaging_event:
                        self.handle_postback(sender_id, messaging_event['postback']['payload'])

        except Exception as e:
            logger.error(f"Error handling webhook: {str(e)}")

    def handle_text_message(self, sender_id, text):
        """Обработка текстовых команд"""
        text_lower = text.lower().strip()

        # Команда помощи
        if text_lower in ['/help', 'help', 'помощь', 'ជំនួយ']:
            self.send_help_message(sender_id)

        # Команда статуса
        elif text_lower in ['/status', 'status', 'статус', 'ស្ថានភាព']:
            self.send_status_message(sender_id)

        # Команда подписки
        elif text_lower in ['/subscribe', 'subscribe', 'подписка', 'ជាវ']:
            self.send_subscription_message(sender_id)

        # Команда сброса лимитов (для тестирования)
        elif text_lower in ['/reset', 'reset', 'сброс']:
            from datetime import datetime, timedelta
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

            # Удаляем записи транскрипций за сегодня
            self.db.transcriptions.delete_many({
                "user_id": sender_id,
                "created_at": {"$gte": today_start}
            })

            self.send_text_message(sender_id, "✅ Лимиты сброшены! Можете тестировать.")

        # Команда старт
        elif text_lower in ['/start', 'start', 'привет', 'hi', 'hello', 'សួស្តី']:
            self.send_welcome_message(sender_id)

        else:
            # Если команда не найдена
            self.send_text_message(sender_id,
                                   "Отправьте мне голосовое сообщение или видео, и я переведу их в текст! 🎤📹\n"
                                   "Send me a voice message or video and I'll transcribe it! 🎤📹\n"
                                   "សូមផ្ញើសារជាសំឡេង ឬវីដេអូមកខ្ញុំ ហើយខ្ញុំនឹងបកប្រែវាជាអត្ថបទ! 🎤📹")

    def handle_media_message(self, sender_id, media_url, media_type):
        """Обработка аудио/видео сообщений"""
        # Проверка лимитов пользователя
        user = self.db.get_or_create_user(sender_id)

        if not self.check_user_limits(sender_id, user):
            return

        # Отправляем сообщение о начале обработки
        emoji = "🎧" if media_type == "audio" else "🎥"
        self.send_text_message(sender_id,
                               f"{emoji} Обрабатываю ваше {media_type}... / Processing... / កំពុងដំណើរការ...")

        # Обрабатываем медиа БЕЗ перевода сначала
        result = self.media_handler.process_media_url(
            media_url,
            media_type,
            user['subscription_type'],
            include_translation=False  # НЕ включаем перевод автоматически
        )

        if result['success']:
            # Показываем только транскрипцию
            message_text = f"📝 {result['language']}: {result['text']}"
            self.send_text_message(sender_id, message_text)

            # Записываем транскрипцию в БД
            transcription_id = self.db.save_transcription(
                user_id=sender_id,
                media_type=media_type,
                media_url=media_url,
                transcription=result['text'],
                translation=None,  # Пока без перевода
                language=result['language'],
                duration_seconds=result.get('duration_seconds', 0)
            )

            # Увеличиваем счетчик использования
            self.db.increment_user_usage(sender_id)

            # Если язык НЕ английский, предлагаем перевод
            if result['language_code'] != 'en':
                self.send_translation_offer(sender_id, media_url, transcription_id)

            # Отправляем информацию о лимитах
            self.send_usage_info(sender_id, user)
        else:
            self.send_text_message(sender_id,
                                   f"❌ Ошибка: {result['error']}\n"
                                   f"❌ Error: {result['error']}\n"
                                   f"❌ កំហុស: {result['error']}")

    def check_user_limits(self, sender_id, user):
        """Проверка лимитов пользователя"""
        if user['subscription_type'] == 'free':
            daily_usage = self.db.get_daily_usage(sender_id)
            if daily_usage >= FREE_DAILY_LIMIT:
                self.send_limit_reached_message(sender_id)
                return False
        return True

    def send_usage_info(self, sender_id, user):
        """Отправка информации об использовании"""
        if user['subscription_type'] == 'free':
            daily_usage = self.db.get_daily_usage(sender_id)
            remaining = FREE_DAILY_LIMIT - daily_usage

            self.send_text_message(sender_id,
                                   f"✅ Осталось бесплатных транскрипций сегодня: {remaining}\n"
                                   f"Получите безлимитный доступ - /subscribe")

    def handle_postback(self, sender_id, payload):
        """Обработка нажатий на кнопки"""
        if payload == 'GET_STARTED':
            self.send_welcome_message(sender_id)
        elif payload == 'SUBSCRIBE':
            self.send_subscription_message(sender_id)
        elif payload == 'HELP':
            self.send_help_message(sender_id)

    def send_text_message(self, recipient_id, text):
        """Отправка текстового сообщения"""
        try:
            response = requests.post(
                f"{self.graph_url}/messages",
                params={"access_token": self.page_access_token},
                json={
                    "recipient": {"id": recipient_id},
                    "message": {"text": text}
                }
            )

            if response.status_code != 200:
                logger.error(f"Failed to send message: {response.text}")

        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")

    def send_welcome_message(self, sender_id):
        """Отправка приветственного сообщения"""
        message = {
            "text": (
                "👋 Добро пожаловать в Audio Transcribe Bot!\n\n"
                "🎤 Я могу превратить ваши голосовые сообщения и видео в текст на любом языке.\n\n"
                "📝 Просто отправьте мне аудио или видео!\n\n"
                "🆓 Бесплатно: 10 транскрипций в день (до 5 минут)\n"
                "⭐ Премиум: Безлимитный доступ (до 60 минут)\n\n"
                "Команды:\n"
                "/help - Помощь\n"
                "/status - Ваш статус\n"
                "/subscribe - Подписка"
            )
        }

        try:
            response = requests.post(
                f"{self.graph_url}/messages",
                params={"access_token": self.page_access_token},
                json={
                    "recipient": {"id": sender_id},
                    "message": message
                }
            )

            if response.status_code != 200:
                logger.error(f"Failed to send welcome message: {response.text}")

        except Exception as e:
            logger.error(f"Error sending welcome message: {str(e)}")

    def send_help_message(self, sender_id):
        """Отправка справочного сообщения"""
        help_text = (
            "📖 Как использовать бота:\n\n"
            "1️⃣ Отправьте голосовое сообщение или видео\n"
            "2️⃣ Бот автоматически распознает язык\n"
            "3️⃣ Получите текст и перевод на английский\n\n"
            "💡 Советы для лучшего качества:\n"
            "• Говорите четко и не слишком быстро\n"
            "• Избегайте шумных мест\n"
            "• Держите микрофон близко\n\n"
            "🌍 Поддерживаемые языки:\n"
            "Русский, English, ភាសាខ្មែរ, 中文, Español, Français и 90+ других\n\n"
            "⏱ Лимиты:\n"
            "• Бесплатно: до 5 минут\n"
            "• Premium: до 60 минут\n\n"
            "/status - проверить ваш статус\n"
            "/subscribe - получить Premium"
        )

        self.send_text_message(sender_id, help_text)

    def send_status_message(self, sender_id):
        """Отправка статуса пользователя"""
        user = self.db.get_or_create_user(sender_id)
        daily_usage = self.db.get_daily_usage(sender_id)

        if user['subscription_type'] == 'free':
            remaining = FREE_DAILY_LIMIT - daily_usage
            limit_info = f"Транскрипций сегодня: {daily_usage}\nОсталось сегодня: {remaining}/{FREE_DAILY_LIMIT}"
            max_duration = MAX_AUDIO_DURATION_FREE // 60
        else:
            limit_info = "Безлимитные транскрипции"
            max_duration = MAX_AUDIO_DURATION_PREMIUM // 60

        status_text = (
            f"📊 Ваш статус\n\n"
            f"Тип аккаунта: {user['subscription_type'].title()}\n"
            f"{limit_info}\n"
            f"Всего транскрипций: {user.get('total_transcriptions', 0)}\n"
            f"Макс. длительность: {max_duration} минут"
        )

        self.send_text_message(sender_id, status_text)

    def send_subscription_message(self, sender_id):
        """Отправка информации о подписке"""
        # Временная заглушка для подписки
        subscription_text = (
            "⭐ Premium Подписка\n\n"
            "✅ Безлимитные транскрипции\n"
            "✅ Файлы до 60 минут\n"
            "✅ Приоритетная обработка\n"
            "✅ История транскрипций\n\n"
            "💰 Цена: $4.99/месяц\n\n"
            "🔜 Платежная система скоро будет доступна!"
        )

        self.send_text_message(sender_id, subscription_text)

    def send_limit_reached_message(self, sender_id):
        """Сообщение о достижении лимита"""
        message = {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "button",
                    "text": (
                        "🚫 Вы достигли дневного лимита бесплатных транскрипций.\n\n"
                        "Получите безлимитный доступ с Premium подпиской!"
                    ),
                    "buttons": [
                        {
                            "type": "postback",
                            "title": "⭐ Получить Premium",
                            "payload": "SUBSCRIBE"
                        }
                    ]
                }
            }
        }

        try:
            response = requests.post(
                f"{self.graph_url}/messages",
                params={"access_token": self.page_access_token},
                json={
                    "recipient": {"id": sender_id},
                    "message": message
                }
            )

            if response.status_code != 200:
                logger.error(f"Failed to send message: {response.text}")
                # Fallback на простое сообщение
                self.send_text_message(sender_id,
                                       "🚫 Вы достигли дневного лимита.\nПолучите Premium - /subscribe")

        except Exception as e:
            logger.error(f"Error sending limit message: {str(e)}")