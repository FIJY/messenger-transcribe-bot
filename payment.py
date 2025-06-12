import os
import hashlib
import hmac
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, redirect, jsonify
import requests

payment_bp = Blueprint('payment', __name__)

class PaymentService:
    def __init__(self):
        self.payment_method = os.getenv('PAYMENT_METHOD', 'paypal')  # paypal, 2checkout, crypto
        
        if self.payment_method == 'paypal':
            self.client_id = os.getenv('PAYPAL_CLIENT_ID')
            self.client_secret = os.getenv('PAYPAL_CLIENT_SECRET')
            self.webhook_id = os.getenv('PAYPAL_WEBHOOK_ID')
            self.base_url = 'https://api-m.sandbox.paypal.com' if os.getenv('ENVIRONMENT') == 'development' else 'https://api-m.paypal.com'
        elif self.payment_method == '2checkout':
            self.merchant_code = os.getenv('2CO_MERCHANT_CODE')
            self.secret_key = os.getenv('2CO_SECRET_KEY')
        elif self.payment_method == 'crypto':
            # Для криптоплатежей можно использовать CoinPayments или аналоги
            self.merchant_id = os.getenv('COINPAYMENTS_MERCHANT_ID')
            self.ipn_secret = os.getenv('COINPAYMENTS_IPN_SECRET')
    
    def create_subscription_link(self, user_id, plan='monthly'):
        """Создать ссылку для оплаты подписки"""
        if self.payment_method == 'paypal':
            return self._create_paypal_subscription(user_id, plan)
        elif self.payment_method == '2checkout':
            return self._create_2checkout_link(user_id, plan)
        elif self.payment_method == 'crypto':
            return self._create_crypto_payment(user_id, plan)
        else:
            # Fallback на простую страницу оплаты
            return f"{os.getenv('BASE_URL')}/payment?user_id={user_id}&plan={plan}"
    
    def _create_paypal_subscription(self, user_id, plan):
        """Создание подписки через PayPal"""
        # Получаем access token
        token = self._get_paypal_token()
        
        # Создаем продукт
        product_id = self._create_paypal_product(token)
        
        # Создаем план подписки
        plan_id = self._create_paypal_plan(token, product_id, plan)
        
        # Создаем подписку
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        subscription_data = {
            "plan_id": plan_id,
            "custom_id": user_id,
            "application_context": {
                "return_url": f"{os.getenv('BASE_URL')}/payment/success",
                "cancel_url": f"{os.getenv('BASE_URL')}/payment/cancel"
            }
        }
        
        response = requests.post(
            f"{self.base_url}/v1/billing/subscriptions",
            json=subscription_data,
            headers=headers
        )
        
        if response.status_code == 201:
            subscription = response.json()
            # Возвращаем ссылку для оплаты
            for link in subscription['links']:
                if link['rel'] == 'approve':
                    return link['href']
        
        return None
    
    def _create_2checkout_link(self, user_id, plan):
        """Создание ссылки оплаты через 2Checkout"""
        price = '4.99' if plan == 'monthly' else '49.99'
        
        params = {
            'merchant': self.merchant_code,
            'prod': 'Audio Transcribe Bot Premium',
            'price': price,
            'qty': '1',
            'type': 'digital',
            'tangible': 'N',
            'src': 'messenger_bot',
            'return_url': f"{os.getenv('BASE_URL')}/payment/2co_return",
            'x_receipt_link_url': f"{os.getenv('BASE_URL')}/payment/2co_ipn",
            'custom': user_id
        }
        
        # Создаем подпись
        signature_string = f"{self.merchant_code}{params['prod']}{params['price']}"
        params['signature'] = hashlib.md5(
            f"{signature_string}{self.secret_key}".encode()
        ).hexdigest()
        
        # Формируем URL
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        return f"https://www.2checkout.com/checkout/purchase?{query_string}"
    
    def _create_crypto_payment(self, user_id, plan):
        """Создание криптоплатежа через CoinPayments"""
        amount = 4.99 if plan == 'monthly' else 49.99
        
        # Простая ссылка на страницу оплаты
        # В реальности здесь нужно создать транзакцию через API
        return f"{os.getenv('BASE_URL')}/payment/crypto?user_id={user_id}&amount={amount}&plan={plan}"
    
    def _get_paypal_token(self):
        """Получение access token PayPal"""
        auth = (self.client_id, self.client_secret)
        headers = {'Accept': 'application/json'}
        data = {'grant_type': 'client_credentials'}
        
        response = requests.post(
            f"{self.base_url}/v1/oauth2/token",
            auth=auth,
            headers=headers,
            data=data
        )
        
        return response.json()['access_token']
    
    def _create_paypal_product(self, token):
        """Создание продукта в PayPal"""
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        product_data = {
            "name": "Audio Transcribe Bot Premium",
            "description": "Unlimited audio transcriptions",
            "type": "SERVICE",
            "category": "SOFTWARE"
        }
        
        response = requests.post(
            f"{self.base_url}/v1/catalogs/products",
            json=product_data,
            headers=headers
        )
        
        if response.status_code == 201:
            return response.json()['id']
        
        # Если продукт уже существует, ищем его
        response = requests.get(
            f"{self.base_url}/v1/catalogs/products",
            headers=headers
        )
        
        for product in response.json()['products']:
            if product['name'] == product_data['name']:
                return product['id']
        
        return None
    
    def _create_paypal_plan(self, token, product_id, plan_type):
        """Создание плана подписки в PayPal"""
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        if plan_type == 'monthly':
            billing_cycles = [{
                "frequency": {
                    "interval_unit": "MONTH",
                    "interval_count": 1
                },
                "tenure_type": "REGULAR",
                "sequence": 1,
                "total_cycles": 0,
                "pricing_scheme": {
                    "fixed_price": {
                        "value": "4.99",
                        "currency_code": "USD"
                    }
                }
            }]
        else:  # yearly
            billing_cycles = [{
                "frequency": {
                    "interval_unit": "YEAR",
                    "interval_count": 1
                },
                "tenure_type": "REGULAR",
                "sequence": 1,
                "total_cycles": 0,
                "pricing_scheme": {
                    "fixed_price": {
                        "value": "49.99",
                        "currency_code": "USD"
                    }
                }
            }]
        
        plan_data = {
            "product_id": product_id,
            "name": f"Premium {plan_type.capitalize()}",
            "billing_cycles": billing_cycles,
            "payment_preferences": {
                "auto_bill_outstanding": True,
                "setup_fee_failure_action": "CONTINUE",
                "payment_failure_threshold": 3
            }
        }
        
        response = requests.post(
            f"{self.base_url}/v1/billing/plans",
            json=plan_data,
            headers=headers
        )
        
        if response.status_code == 201:
            return response.json()['id']
        
        return None
    
    def verify_paypal_webhook(self, headers, body):
        """Верификация webhook от PayPal"""
        # PayPal отправляет специальные заголовки для верификации
        transmission_id = headers.get('Paypal-Transmission-Id')
        timestamp = headers.get('Paypal-Transmission-Time')
        webhook_id = self.webhook_id
        crc = str(body).encode('utf-8')
        
        # Создаем строку для верификации
        expected_sig = f"{transmission_id}|{timestamp}|{webhook_id}|{crc}"
        
        # Проверяем подпись
        actual_sig = headers.get('Paypal-Transmission-Sig')
        
        # В продакшене нужно проверить подпись через PayPal API
        # Здесь упрощенная проверка
        return True
    
    def process_paypal_webhook(self, data):
        """Обработка webhook от PayPal"""
        event_type = data.get('event_type')
        resource = data.get('resource', {})
        
        if event_type == 'BILLING.SUBSCRIPTION.CREATED':
            # Новая подписка создана
            user_id = resource.get('custom_id')
            subscription_id = resource.get('id')
            return {
                'action': 'subscription_created',
                'user_id': user_id,
                'subscription_id': subscription_id
            }
        
        elif event_type == 'BILLING.SUBSCRIPTION.ACTIVATED':
            # Подписка активирована (оплачена)
            user_id = resource.get('custom_id')
            subscription_id = resource.get('id')
            return {
                'action': 'subscription_activated',
                'user_id': user_id,
                'subscription_id': subscription_id,
                'end_date': datetime.utcnow() + timedelta(days=30)
            }
        
        elif event_type == 'BILLING.SUBSCRIPTION.CANCELLED':
            # Подписка отменена
            user_id = resource.get('custom_id')
            return {
                'action': 'subscription_cancelled',
                'user_id': user_id
            }
        
        elif event_type == 'PAYMENT.SALE.COMPLETED':
            # Платеж прошел успешно
            custom = resource.get('custom')
            if custom:
                return {
                    'action': 'payment_completed',
                    'user_id': custom
                }
        
        return None
    
    def process_2checkout_ipn(self, data):
        """Обработка IPN от 2Checkout"""
        # Проверяем MD5 хеш
        secret = self.secret_key
        vendor_id = self.merchant_code
        order_number = data.get('order_number')
        total = data.get('total')
        
        # 2Checkout использует особый алгоритм для подписи
        string_to_hash = f"{secret}{vendor_id}{order_number}{total}"
        expected_hash = hashlib.md5(string_to_hash.encode()).hexdigest().upper()
        
        if expected_hash != data.get('key'):
            logging.error("Invalid 2Checkout IPN signature")
            return None
        
        # Обрабатываем успешный платеж
        if data.get('credit_card_processed') == 'Y':
            user_id = data.get('custom')
            return {
                'action': 'payment_completed',
                'user_id': user_id,
                'amount': total
            }
        
        return None

# Flask роуты для обработки платежей
@payment_bp.route('/payment/success')
def payment_success():
    """Успешная оплата"""
    return """
    <html>
    <head>
        <title>Payment Successful</title>
        <meta charset="utf-8">
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
            .success { color: #4CAF50; font-size: 24px; }
            .message { margin-top: 20px; font-size: 18px; }
        </style>
    </head>
    <body>
        <div class="success">✅ Payment Successful!</div>
        <div class="message">
            Your premium subscription is now active.<br>
            Return to Messenger to enjoy unlimited transcriptions!
        </div>
        <script>
            setTimeout(function() {
                window.location.href = 'https://m.me/YourBotUsername';
            }, 3000);
        </script>
    </body>
    </html>
    """

@payment_bp.route('/payment/cancel')
def payment_cancel():
    """Отмена оплаты"""
    return """
    <html>
    <head>
        <title>Payment Cancelled</title>
        <meta charset="utf-8">
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
            .cancel { color: #f44336; font-size: 24px; }
            .message { margin-top: 20px; font-size: 18px; }
        </style>
    </head>
    <body>
        <div class="cancel">❌ Payment Cancelled</div>
        <div class="message">
            Your payment was cancelled.<br>
            Return to Messenger to try again or continue with free plan.
        </div>
    </body>
    </html>
    """

@payment_bp.route('/payment/webhook/paypal', methods=['POST'])
def paypal_webhook():
    """Webhook для PayPal"""
    from database import Database
    db = Database()
    payment_service = PaymentService()
    
    # Верифицируем webhook
    if not payment_service.verify_paypal_webhook(request.headers, request.data):
        return 'Unauthorized', 401
    
    # Обрабатываем событие
    result = payment_service.process_paypal_webhook(request.json)
    
    if result:
        if result['action'] == 'subscription_activated':
            db.update_subscription(
                result['user_id'],
                'premium',
                result['end_date']
            )
        elif result['action'] == 'subscription_cancelled':
            db.update_subscription(result['user_id'], 'free')
    
    return 'OK', 200

@payment_bp.route('/payment/ipn/2checkout', methods=['POST'])
def twocheckout_ipn():
    """IPN для 2Checkout"""
    from database import Database
    db = Database()
    payment_service = PaymentService()
    
    result = payment_service.process_2checkout_ipn(request.form)
    
    if result and result['action'] == 'payment_completed':
        # Активируем премиум на месяц
        end_date = datetime.utcnow() + timedelta(days=30)
        db.update_subscription(result['user_id'], 'premium', end_date)
    
    return 'OK', 200