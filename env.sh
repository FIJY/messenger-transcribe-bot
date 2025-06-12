# Facebook Messenger Configuration
PAGE_ACCESS_TOKEN=your_page_access_token_here
VERIFY_TOKEN=your_random_verify_token_here
APP_ID=your_facebook_app_id
APP_SECRET=your_facebook_app_secret

# Database Configuration
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/dbname?retryWrites=true&w=majority
# Или для локальной MongoDB:
# MONGODB_URI=mongodb://localhost:27017/transcribe_bot

# Whisper Configuration
WHISPER_MODEL=base  # tiny, base, small, medium, large

# Application Settings
ENVIRONMENT=development  # development или production
BASE_URL=https://your-app-name.railway.app
PORT=5000

# Payment Configuration
PAYMENT_METHOD=paypal  # paypal, 2checkout, или crypto

# PayPal (если используете)
PAYPAL_CLIENT_ID=your_paypal_client_id
PAYPAL_CLIENT_SECRET=your_paypal_client_secret
PAYPAL_WEBHOOK_ID=your_webhook_id

# 2Checkout (если используете)
2CO_MERCHANT_CODE=your_merchant_code
2CO_SECRET_KEY=your_secret_key

# CoinPayments (если используете криптоплатежи)
COINPAYMENTS_MERCHANT_ID=your_merchant_id
COINPAYMENTS_IPN_SECRET=your_ipn_secret

# Optional: Redis for caching
REDIS_URL=redis://localhost:6379

# Optional: Logging
LOG_LEVEL=INFO