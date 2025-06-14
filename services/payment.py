import os
import logging
import hashlib
import hmac
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class PaymentService:
    def __init__(self):
        """Инициализация сервиса платежей"""
        self.stripe_key = os.getenv('STRIPE_SECRET_KEY')
        self.stripe_webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
        self.paypal_client_id = os.getenv('PAYPAL_CLIENT_ID')
        self.paypal_secret = os.getenv('PAYPAL_SECRET')

        logger.info("Payment service initialized")

    def create_subscription_link(self, user_id, plan_type="premium"):
        """Создать ссылку на оплату подписки"""
        # Временная заглушка - в продакшене здесь будет интеграция с платежными системами
        base_url = os.getenv('BASE_URL', 'https://your-payment-site.com')

        payment_link = f"{base_url}/subscribe?user_id={user_id}&plan={plan_type}"

        logger.info(f"Created payment link for user {user_id}: {payment_link}")
        return payment_link

    def verify_webhook_signature(self, payload, signature, webhook_secret):
        """Проверить подпись webhook"""
        try:
            expected_signature = hmac.new(
                webhook_secret.encode('utf-8'),
                payload,
                hashlib.sha256
            ).hexdigest()

            return hmac.compare_digest(signature, expected_signature)

        except Exception as e:
            logger.error(f"Error verifying webhook signature: {e}")
            return False

    def process_payment_success(self, user_id, transaction_id, plan_type="premium"):
        """Обработать успешный платеж"""
        try:
            # Определяем срок действия подписки
            if plan_type == "premium":
                expires_at = datetime.utcnow() + timedelta(days=30)  # 1 месяц
            else:
                expires_at = None

            logger.info(f"Processing successful payment for user {user_id}: {transaction_id}")

            return {
                "success": True,
                "subscription_type": plan_type,
                "expires_at": expires_at,
                "transaction_id": transaction_id
            }

        except Exception as e:
            logger.error(f"Error processing payment success: {e}")
            return {"success": False, "error": str(e)}

    def cancel_subscription(self, user_id):
        """Отменить подписку"""
        try:
            logger.info(f"Cancelling subscription for user {user_id}")

            # В продакшене здесь будет обращение к платежной системе
            # для отмены автоплатежей

            return {"success": True}

        except Exception as e:
            logger.error(f"Error cancelling subscription: {e}")
            return {"success": False, "error": str(e)}

    def get_subscription_status(self, user_id):
        """Получить статус подписки"""
        try:
            # В продакшене здесь будет проверка статуса в платежной системе
            return {
                "active": False,
                "plan": "free",
                "expires_at": None
            }

        except Exception as e:
            logger.error(f"Error getting subscription status: {e}")
            return None

    def generate_invoice(self, user_id, amount, currency="USD"):
        """Создать инвойс для оплаты"""
        try:
            invoice_id = f"inv_{user_id}_{int(datetime.utcnow().timestamp())}"

            invoice_data = {
                "id": invoice_id,
                "user_id": user_id,
                "amount": amount,
                "currency": currency,
                "status": "pending",
                "created_at": datetime.utcnow()
            }

            logger.info(f"Generated invoice for user {user_id}: {invoice_id}")
            return invoice_data

        except Exception as e:
            logger.error(f"Error generating invoice: {e}")
            return None