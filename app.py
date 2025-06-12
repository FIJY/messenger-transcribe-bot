import os
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import logging
from database import Database
from transcribe import TranscribeService
from payment import PaymentService

load_dotenv()

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Инициализация сервисов
db = Database()
transcriber = TranscribeService()
payment = PaymentService()

# Конфигурация
PAGE_ACCESS_TOKEN = os.getenv('PAGE_ACCESS_TOKEN')
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN')
WEBHOOK_URL = "https://graph.facebook.com/v18.0/me/messages"

# Лимиты для freemium
FREE_DAILY_LIMIT = 3
MAX_AUDIO_DURATION = 300  # 5 минут в секундах

@app.route('/webhook', methods=['GET'])
def verify_webhook():
    """Верификация webhook для Facebook"""
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    
    if token == VERIFY_TOKEN:
        logging.info('Webhook verified')
        return challenge
    return 'Invalid token', 403

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    """Обработка входящих сообщений"""
    data = request.json
    
    if data['object'] == 'page':
        for entry in data['entry']:
            for messaging_event in entry['messaging']:
                sender_id = messaging_event['sender']['id']
                
                # Обработка текстовых команд
                if 'message' in messaging_event and 'text' in messaging_event['message']:
                    handle_text_message(sender_id, messaging_event['message']['text'])
                
                # Обработка аудио
                elif 'message' in messaging_event and 'attachments' in messaging_event['message']:
                    for attachment in messaging_event['message']['attachments']:
                        if attachment['type'] == 'audio':
                            handle_audio_message(sender_id, attachment['payload']['url'])
                
                # Обработка postback (кнопки)
                elif 'postback' in messaging_event:
                    handle_postback(sender_id, messaging_event['postback']['payload'])
    
    return 'OK', 200

def handle_text_message(sender_id, text):
    """Обработка текстовых команд"""
    text_lower = text.lower()
    
    if text_lower in ['/start', 'start', 'привет', 'hello', 'សួស្តី']:
        send_welcome_message(sender_id)
    elif text_lower in ['/help', 'help', 'помощь']:
        send_help_message(sender_id)
    elif text_lower in ['/status', 'status', 'статус']:
        send_status_message(sender_id)
    elif text_lower in ['/subscribe', 'subscribe', 'подписка']:
        send_subscription_options(sender_id)
    else:
        send_text_message(sender_id, 
            "Отправьте мне голосовое сообщение, и я переведу его в текст! 🎤\n"
            "Send me a voice message and I'll transcribe it! 🎤\n"
            "ផ្ញើសារជាសំឡេងមកខ្ញុំ ខ្ញុំនឹងបកប្រែជាអក្សរ! 🎤")

def handle_audio_message(sender_id, audio_url):
    """Обработка аудио сообщений"""
    # Проверка лимитов пользователя
    user = db.get_or_create_user(sender_id)
    
    if not check_user_limits(user):
        send_limit_exceeded_message(sender_id)
        return
    
    # Отправка сообщения о начале обработки
    send_text_message(sender_id, "🎧 Обрабатываю ваше аудио... / Processing... / កំពុងដំណើរការ...")
    
    try:
        # Скачивание аудио
        audio_data = download_audio(audio_url)
        
        # Транскрипция
        transcription = transcriber.transcribe(audio_data)
        
        if transcription['success']:
            # Обновление статистики пользователя
            db.increment_user_usage(sender_id)
            
            # Отправка результата
            message = f"📝 **Язык/Language/ភាសា**: {transcription['language']}\n\n"
            message += f"**Текст/Text/អត្ថបទ**:\n{transcription['text']}"
            
            send_text_message(sender_id, message)
            
            # Добавление промо для бесплатных пользователей
            if user['subscription_type'] == 'free':
                remaining = FREE_DAILY_LIMIT - db.get_daily_usage(sender_id)
                send_text_message(sender_id, 
                    f"✅ Осталось бесплатных транскрипций сегодня: {remaining}\n"
                    f"🌟 Получите безлимитный доступ - /subscribe")
        else:
            send_text_message(sender_id, 
                "❌ Не удалось распознать аудио. Попробуйте записать четче или проверьте качество записи.")
            
    except Exception as e:
        logging.error(f"Error processing audio: {e}")
        send_text_message(sender_id, 
            "❌ Произошла ошибка при обработке. Пожалуйста, попробуйте позже.")

def check_user_limits(user):
    """Проверка лимитов пользователя"""
    if user['subscription_type'] == 'premium':
        return True
    
    daily_usage = db.get_daily_usage(user['user_id'])
    return daily_usage < FREE_DAILY_LIMIT

def send_welcome_message(sender_id):
    """Отправка приветственного сообщения"""
    message = {
        "text": (
            "👋 Добро пожаловать в Audio Transcribe Bot!\n\n"
            "🎤 Я могу превратить ваши голосовые сообщения в текст на любом языке.\n\n"
            "📝 Просто отправьте мне аудио сообщение!\n\n"
            "🆓 Бесплатно: 3 транскрипции в день\n"
            "⭐ Премиум: Безлимитный доступ\n\n"
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
    send_message(sender_id, message)

def send_subscription_options(sender_id):
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
                        "url": f"{os.getenv('PAYMENT_URL')}?user_id={sender_id}",
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
    send_message(sender_id, message)

def send_status_message(sender_id):
    """Отправка статуса пользователя"""
    user = db.get_or_create_user(sender_id)
    daily_usage = db.get_daily_usage(sender_id)
    
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
    
    send_text_message(sender_id, message)

def send_text_message(recipient_id, text):
    """Отправка текстового сообщения"""
    message = {"text": text}
    send_message(recipient_id, message)

def send_message(recipient_id, message):
    """Базовая функция отправки сообщений"""
    payload = {
        "recipient": {"id": recipient_id},
        "message": message
    }
    
    headers = {"Content-Type": "application/json"}
    params = {"access_token": PAGE_ACCESS_TOKEN}
    
    response = requests.post(
        WEBHOOK_URL,
        params=params,
        headers=headers,
        json=payload
    )
    
    if response.status_code != 200:
        logging.error(f"Failed to send message: {response.text}")

def download_audio(url):
    """Скачивание аудио файла"""
    response = requests.get(url)
    response.raise_for_status()
    return response.content

def send_limit_exceeded_message(sender_id):
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
    send_message(sender_id, message)

def handle_postback(sender_id, payload):
    """Обработка нажатий на кнопки"""
    if payload == 'SUBSCRIBE':
        send_subscription_options(sender_id)
    elif payload == 'STATUS':
        send_status_message(sender_id)
    elif payload == 'BACK_TO_MENU':
        send_welcome_message(sender_id)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)