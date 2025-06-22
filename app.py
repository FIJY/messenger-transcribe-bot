# app.py
import os
import logging
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

# Импорты сервисов
from services.message_handler import MessageHandler
from services.database import Database
from services.translation_service import TranslationService  # 🔧 НОВЫЙ ИМПОРТ

app = Flask(__name__)

# --- Инициализация ---
try:
    logger.info("Инициализация сервисов для веб-процесса...")
    database = Database()
    translation_service = TranslationService()  # 🔧 СОЗДАЕМ СЕРВИС ПЕРЕВОДА

    # 🔧 ПЕРЕДАЕМ ОБА СЕРВИСА В MessageHandler
    message_handler = MessageHandler(database=database, translation_service=translation_service)

    logger.info("✅ Веб-сервисы успешно инициализированы.")
except Exception as e:
    logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА ИНИЦИАЛИЗАЦИИ: {e}", exc_info=True)
    message_handler = None


# --- Конец инициализации ---

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({'status': 'Bot web service is running'})


@app.route('/webhook', methods=['GET'])
def webhook_verify():
    verify_token = os.getenv('VERIFY_TOKEN')
    if request.args.get('hub.verify_token') == verify_token:
        return request.args.get('hub.challenge', '')
    return 'Verification failed', 403


@app.route('/webhook', methods=['POST'])
def webhook_handler():
    try:
        data = request.get_json()
        if data and data.get('object') == 'page':
            if message_handler:
                message_handler.handle_message(data)
            else:
                logger.error("MessageHandler не был инициализирован из-за ошибки при запуске.")
        return 'OK', 200
    except Exception as e:
        logger.error(f"Критическая ошибка в webhook_handler: {e}", exc_info=True)
        return 'OK', 200


@app.route('/privacy')
def privacy_policy():
    """Privacy Policy for Facebook App Review"""
    return '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Privacy Policy - Messenger Transcribe Bot</title>
        <style>
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; 
                max-width: 800px; 
                margin: 40px auto; 
                padding: 20px; 
                line-height: 1.6;
                color: #333;
                background: #f8f9fa;
            }
            .container {
                background: white;
                padding: 40px;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 { 
                color: #1877f2; 
                border-bottom: 3px solid #1877f2;
                padding-bottom: 10px;
            }
            h2 { 
                color: #333; 
                margin-top: 30px; 
                margin-bottom: 15px;
            }
            ul { margin: 15px 0; }
            li { margin: 5px 0; }
            .highlight { 
                background: #e3f2fd; 
                padding: 15px; 
                border-left: 4px solid #1877f2; 
                margin: 20px 0;
            }
            .footer {
                margin-top: 40px;
                padding-top: 20px;
                border-top: 1px solid #eee;
                font-size: 14px;
                color: #666;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Privacy Policy</h1>
            <h2>Messenger Transcribe Bot</h2>

            <div class="highlight">
                <strong>Last Updated:</strong> June 19, 2025<br>
                <strong>Effective Date:</strong> June 19, 2025
            </div>

            <h2>1. Service Description</h2>
            <p>Messenger Transcribe Bot is an automated service for transcribing (converting speech to text) audio and video files. We provide services through Facebook Messenger with support for multiple languages including Khmer, Thai, Vietnamese, and others.</p>

            <h2>2. Information We Collect</h2>
            <ul>
                <li><strong>Media Files:</strong> Audio and video files you send for transcription</li>
                <li><strong>User Identifiers:</strong> Facebook User ID for identification and communication</li>
                <li><strong>Transcription Results:</strong> Generated text and language information</li>
                <li><strong>Usage Statistics:</strong> Number of requests, processing time, service analytics</li>
                <li><strong>Technical Data:</strong> IP address, request time for security purposes</li>
            </ul>

            <h2>3. How We Use Your Information</h2>
            <ul>
                <li>To provide audio and video transcription services</li>
                <li>To improve speech recognition algorithm quality</li>
                <li>To provide technical support</li>
                <li>To ensure security and prevent abuse</li>
                <li>For service usage analytics (in anonymized form)</li>
            </ul>

            <h2>4. Data Storage and Security</h2>
            <ul>
                <li><strong>Audio/Video Files:</strong> Deleted immediately after transcription completion</li>
                <li><strong>Transcriptions:</strong> Stored for up to 30 days for retrieval purposes</li>
                <li><strong>User Data:</strong> Stored as long as you use the service</li>
                <li><strong>Encryption:</strong> All data transmitted over secure channels (HTTPS/TLS)</li>
                <li><strong>Access:</strong> Limited access for authorized personnel only</li>
            </ul>

            <h2>5. Data Sharing with Third Parties</h2>
            <p>We <strong>DO NOT sell, rent, or share</strong> your personal information with third parties, except:</p>
            <ul>
                <li><strong>Service Providers:</strong> OpenAI (transcription processing), MongoDB (storage), Cloudflare (delivery)</li>
                <li><strong>Legal Requirements:</strong> When required by law enforcement or legal process</li>
                <li><strong>Rights Protection:</strong> To protect our rights, safety, or property</li>
            </ul>

            <h2>6. Your Rights</h2>
            <p>You have the right to:</p>
            <ul>
                <li><strong>Access:</strong> Request a copy of your data</li>
                <li><strong>Correction:</strong> Correct inaccurate data</li>
                <li><strong>Deletion:</strong> Request deletion of your data</li>
                <li><strong>Restriction:</strong> Limit processing of your data</li>
                <li><strong>Portability:</strong> Receive data in machine-readable format</li>
                <li><strong>Objection:</strong> Object to data processing</li>
            </ul>

            <h2>7. Children's Privacy</h2>
            <p>Our service is not intended for children under 13. We do not knowingly collect personal information from children under 13.</p>

            <h2>8. International Transfers</h2>
            <p>Your data may be processed in countries other than your country of residence. We ensure adequate level of data protection for any international transfers.</p>

            <h2>9. Changes to This Policy</h2>
            <p>We may update this privacy policy periodically. We will notify you of material changes through our service or by email.</p>

            <h2>10. Contact Information</h2>
            <p>For privacy-related questions, contact us:</p>
            <ul>
                <li><strong>Email:</strong> fijyfijy@gmail.com</li>
                <li><strong>Contact:</strong> Olga Shmykova</li>
            </ul>

            <div class="footer">
                <p><em>This privacy policy is designed to comply with GDPR, CCPA, and other applicable data protection laws.</em></p>
            </div>
        </div>
    </body>
    </html>
    '''


@app.route('/terms')
def terms_of_service():
    """Terms of Service for Facebook App Review"""
    return '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Terms of Service - Messenger Transcribe Bot</title>
        <style>
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; 
                max-width: 800px; 
                margin: 40px auto; 
                padding: 20px; 
                line-height: 1.6;
                color: #333;
                background: #f8f9fa;
            }
            .container {
                background: white;
                padding: 40px;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 { 
                color: #1877f2; 
                border-bottom: 3px solid #1877f2;
                padding-bottom: 10px;
            }
            h2 { 
                color: #333; 
                margin-top: 30px; 
                margin-bottom: 15px;
            }
            ul { margin: 15px 0; }
            li { margin: 5px 0; }
            .highlight { 
                background: #e8f5e8; 
                padding: 15px; 
                border-left: 4px solid #4caf50; 
                margin: 20px 0;
            }
            .warning { 
                background: #fff3cd; 
                padding: 15px; 
                border-left: 4px solid #ffc107; 
                margin: 20px 0;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Terms of Service</h1>
            <h2>Messenger Transcribe Bot</h2>

            <div class="highlight">
                <strong>Last Updated:</strong> June 19, 2025<br>
                <strong>Effective Date:</strong> June 19, 2025
            </div>

            <h2>1. Acceptance of Terms</h2>
            <p>By using Messenger Transcribe Bot ("Service"), you agree to comply with these Terms of Service. If you do not agree with any of these terms, please do not use the Service.</p>

            <h2>2. Service Description</h2>
            <p>Messenger Transcribe Bot provides automated transcription services (speech-to-text conversion) for audio and video files through Facebook Messenger. The service supports multiple languages and uses advanced artificial intelligence technologies.</p>

            <h2>3. Usage Limits and Restrictions</h2>
            <ul>
                <li><strong>Free Plan:</strong> 10 files per day, maximum 5 minutes duration, 50MB file size</li>
                <li><strong>Premium Plan:</strong> Unlimited files, maximum 60 minutes duration, 100MB file size</li>
                <li><strong>Supported Formats:</strong> MP3, WAV, OGG, M4A, AAC, FLAC, MP4, AVI, MOV, MKV, WEBM</li>
            </ul>

            <h2>4. Acceptable Use</h2>
            <p>You agree NOT to:</p>
            <ul>
                <li>Upload illegal, harmful, or copyrighted content without permission</li>
                <li>Attempt to reverse engineer or exploit the service</li>
                <li>Use the service to violate any laws or regulations</li>
                <li>Share login credentials or attempt unauthorized access</li>
                <li>Spam or abuse the service limits</li>
            </ul>

            <h2>5. Service Availability</h2>
            <div class="warning">
                <p><strong>Important:</strong> The service is provided "as is" without guarantees of:</p>
                <ul>
                    <li>100% transcription accuracy</li>
                    <li>Uninterrupted service availability</li>
                    <li>Error-free operation</li>
                </ul>
            </div>

            <h2>6. Liability and Disclaimers</h2>
            <ul>
                <li>We are not responsible for transcription accuracy</li>
                <li>Users are responsible for content they upload</li>
                <li>Service may be temporarily unavailable for maintenance</li>
                <li>We reserve the right to terminate accounts for violations</li>
            </ul>

            <h2>7. Changes to Terms</h2>
            <p>We may modify these terms at any time. Continued use of the service after changes constitutes acceptance of new terms.</p>

            <h2>8. Contact Information</h2>
            <p>For questions about these terms:</p>
            <ul>
                <li><strong>Email:</strong> fijyfijy@gmail.com</li>
                <li><strong>Support:</strong> Olga Shmykova</li>
            </ul>
        </div>
    </body>
    </html>
    '''


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)