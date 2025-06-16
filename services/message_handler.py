import os
import logging
import requests
from config.constants import FREE_DAILY_LIMIT, MAX_AUDIO_DURATION_FREE, MAX_AUDIO_DURATION_PREMIUM

logger = logging.getLogger(__name__)


class MessageHandler:
    def __init__(self, db, transcriber, payment):
        self.db = db
        self.transcriber = transcriber
        self.payment = payment
        self.page_access_token = os.getenv('PAGE_ACCESS_TOKEN')
        self.webhook_url = "https://graph.facebook.com/v18.0/me/messages"

    def handle_messaging_event(self, messaging_event):
        """Обработка одного события сообщения"""
        sender_id = messaging_event['sender']['id']

        try:
            # Обработка текстовых команд
            if 'message' in messaging_event and 'text' in messaging_event['message']:
                self.handle_text_message(sender_id, messaging_event['message']['text'])

            # Обработка аудио и видео
            elif 'message' in messaging_event and 'attachments' in messaging_event['message']:
                for attachment in messaging_event['message']['attachments']:
                    if attachment['type'] in ['audio', 'video']:
                        self.handle_media_message(sender_id, attachment['payload']['url'], attachment['type'])

            # Обработка postback (кнопки)
            elif 'postback' in messaging_event:
                self.handle_postback(sender_id, messaging_event['postback']['payload'])

        except Exception as e:
            logger.error(f"Error handling messaging event: {e}")
            self.send_text_message(sender_id, "❌ Произошла ошибка. Попробуйте позже.")

    def handle_text_message(self, sender_id, text):
        """Обработка текстовых команд"""
        text_lower = text.lower()

        commands = {
            ('/start', 'start', 'привет', 'hello', 'សួស្តី'): self.send_welcome_message,
            ('/help', 'help', 'помощь'): self.send_help_message,
            ('/status', 'status', 'статус'): self.send_status_message,
            ('/subscribe', 'subscribe', 'подписка'): self.send_subscription_options,
            ('/reset', 'reset', 'сброс'): self.reset_user_limits
        }

        # Поиск команды
        for command_variants, handler in commands.items():
            if text_lower in command_variants:
                handler(sender_id)
                return

        # Если команда не найдена
        self.send_text_message(sender_id,
                               "Отправьте мне голосовое сообщение или видео, и я переведу их в текст! 🎤📹\n"
                               "Send me a voice message or video and I'll transcribe it! 🎤📹\n"
                               "ផ្ញើសារជាសំឡេងឬវីដេអូមកខ្ញុំ ខ្ញុំនឹងបកប្រែជាអក្សរ! 🎤📹")

    def handle_media_message(self, sender_id, media_url, media_type):
        """Обработка аудио/видео сообщений"""
        # Проверка лимитов пользователя
        user = self.db.get_or_create_user(sender_id)

        if not self.check_user_limits(user):
            self.send_limit_exceeded_message(sender_id)
            return

        # Определяем тип файла для сообщения
        media_emoji = "🎥" if media_type == 'video' else "🎧"
        media_name = "видео" if media_type == 'video' else "аудио"

        # 1. Отправка сообщения о начале обработки
        self.send_text_message(sender_id,
                               f"{media_emoji} Обрабатываю ваше {media_name}... / Processing... / កំពុងដំណើរការ...")

        try:
            # Скачивание медиа файла
            media_data = self.download_audio(media_url)

            # Транскрипция с учетом типа подписки
            transcription = self.transcriber.transcribe(
                media_data,
                user_subscription=user['subscription_type'],
                media_type=media_type
            )

            if transcription['success']:
                # Обновление статистики пользователя
                self.db.increment_user_usage(sender_id)

                # 2. Отправка результата транскрипции
                duration_text = ""
                if transcription.get('duration', 0) > 0:
                    minutes = transcription['duration'] // 60
                    seconds = transcription['duration'] % 60
                    duration_text = f" ({minutes}:{seconds:02d})"

                message = f"📝 **Язык/Language/ភាសា**: {transcription['language']}{duration_text}\n\n"
                message += f"**Текст/Text/អត្ថបទ**:\n{transcription['text']}"

                self.send_text_message(sender_id, message)

                # 3. Добавление промо для бесплатных пользователей
                if user['subscription_type'] == 'free':
                    remaining = FREE_DAILY_LIMIT - self.db.get_daily_usage(sender_id)
                    max_duration = MAX_AUDIO_DURATION_FREE // 60  # в минутах
                    self.send_text_message(sender_id,
                                           f"✅ Осталось бесплатных транскрипций сегодня: {remaining}\n"
                                           f"⏱️ Лимит длительности: {max_duration} минут\n"
                                           f"🌟 Premium: 60 минут + безлимитно - /subscribe")
                else:
                    max_duration = MAX_AUDIO_DURATION_PREMIUM // 60
                    self.send_text_message(sender_id,
                                           f"⭐ Premium активен - лимит {max_duration} минут на файл")
            else:
                self.send_text_message(sender_id,
                                       f"❌ {transcription['error']}")

        except Exception as e:
            logger.error(f"Error processing {media_type}: {e}")
            self.send_text_message(sender_id,
                                   f"❌ Произошла ошибка при обработке {media_name}. Пожалуйста, попробуйте позже.")

    def reset_user_limits(self, sender_id):
        """Сброс лимитов для тестирования"""
        from datetime import datetime, timedelta
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        # Удаляем записи транскрипций за сегодня
        self.db.transcriptions.delete_many({
            "user_id": sender_id,
            "created_at": {"$gte": today_start}
        })

        # Обновляем пользователя
        self.db.users.update_one(
            {"user_id": sender_id},
            {"$set": {"total_transcriptions": 0}}
        )

        self.send_text_message(sender_id, "✅ Лимиты сброшены! Можете тестировать.")

    def handle_postback(self, sender_id, payload):
        """Обработка нажатий на кнопки"""
        handlers = {
            'SUBSCRIBE': self.send_subscription_options,
            'STATUS': self.send_status_message,
            'BACK_TO_MENU': self.send_welcome_message
        }

        handler = handlers.get(payload)
        if handler:
            handler(sender_id)
        else:
            logger.warning(f"Unknown postback payload: {payload}")

    def check_user_limits(self, user):
        """Проверка лимитов пользователя"""
        if user['subscription_type'] == 'premium':
            return True

        daily_usage = self.db.get_daily_usage(user['user_id'])
        return daily_usage < FREE_DAILY_LIMIT

    def send_welcome_message(self, sender_id):
        """Отправка приветственного сообщения"""
        message = {
            "text": (
                "👋 Добро пожаловать в Audio Transcribe Bot!\n\n"
                "🎤 Я могу превратить ваши голосовые сообщения и видео в текст на любом языке.\n\n"
                "📝 Просто отправьте мне аудио или видео!\n\n"
                "🆓 Бесплатно: 10 транскрипций в день, до 5 минут\n"
                "⭐ Премиум: Безлимитный доступ, до 60 минут\n\n"
                "Команды:\n"
                "/help - Помощь\n"
                "/status - Ваш статус\n"
                "/subscribe - Подписка"
            ),
            "quick_replies": [
                {
                    "content_type": "text",
                    "title": "📊 Мой статус",
                    "payload": "STATUS"
                },
                {
                    "content_type": "text",
                    "title": "⭐ Подписка",
                    "payload": "SUBSCRIBE"
                }
            ]
        }
        self.send_message(sender_id, message)

    def send_help_message(self, sender_id):
        """Отправка сообщения помощи"""
        message = (
            "🔧 **Как пользоваться ботом:**\n\n"
            "1️⃣ Отправьте голосовое сообщение\n"
            "2️⃣ Получите текст на том же языке\n\n"
            "🌍 **Поддерживаемые языки:**\n"
            "• Кхмерский (ខ្មែរ)\n"
            "• English\n"
            "• Русский\n"
            "• 中文\n"
            "• ไทย\n"
            "• Tiếng Việt\n"
            "• И многие другие!\n\n"
            "📝 **Команды:**\n"
            "/start - Начало работы\n"
            "/help - Эта справка\n"
            "/status - Ваш статус\n"
            "/subscribe - Премиум подписка\n"
            "/reset - Сброс лимитов (тест)"
        )
        self.send_text_message(sender_id, message)

    def send_subscription_options(self, sender_id):
        """Отправка вариантов подписки"""
        message = {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "button",
                    "text": "⭐ Premium подписка - $4.99/месяц\n\n✅ Безлимитные транскрипции\n✅ Приоритетная обработка\n✅ Файлы до 10 минут\n✅ История транскрипций",
                    "buttons": [
                        {
                            "type": "web_url",
                            "url": "https://your-payment-site.com/subscribe",
                            "title": "💳 Оформить подписку"
                        },
                        {
                            "type": "postback",
                            "title": "🔙 Назад",
                            "payload": "BACK_TO_MENU"
                        }
                    ]
                }
            }
        }
        self.send_message(sender_id, message)

    def send_status_message(self, sender_id):
        """Отправка статуса пользователя"""
        user = self.db.get_or_create_user(sender_id)
        daily_usage = self.db.get_daily_usage(sender_id)

        if user['subscription_type'] == 'premium':
            status = "⭐ Premium"
            limit_text = "Безлимитные транскрипции"
        else:
            status = "🆓 Free"
            remaining = FREE_DAILY_LIMIT - daily_usage
            limit_text = f"Осталось сегодня: {remaining}/{FREE_DAILY_LIMIT}"

        total_transcriptions = user.get('total_transcriptions', 0)

        message = (
            f"📊 **Ваш статус**\n\n"
            f"Тип аккаунта: {status}\n"
            f"Транскрипций сегодня: {daily_usage}\n"
            f"{limit_text}\n"
            f"Всего транскрипций: {total_transcriptions}"
        )

        self.send_text_message(sender_id, message)

    def send_limit_exceeded_message(self, sender_id):
        """Сообщение о превышении лимита"""
        message = {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "button",
                    "text": "⚠️ Вы достигли дневного лимита бесплатных транскрипций.\n\nПолучите безлимитный доступ с Premium подпиской!",
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
        self.send_message(sender_id, message)

    def send_text_message(self, recipient_id, text):
        """Отправка текстового сообщения"""
        message = {"text": text}
        self.send_message(recipient_id, message)

    def send_message(self, recipient_id, message):
        """Базовая функция отправки сообщений"""
        payload = {
            "recipient": {"id": recipient_id},
            "message": message
        }

        headers = {"Content-Type": "application/json"}
        params = {"access_token": self.page_access_token}

        response = requests.post(
            self.webhook_url,
            params=params,
            headers=headers,
            json=payload
        )

        if response.status_code != 200:
            logger.error(f"Failed to send message: {response.text}")

    def download_audio(self, url):
        """Скачивание аудио файла"""
        response = requests.get(url)
        response.raise_for_status()
        return response.content