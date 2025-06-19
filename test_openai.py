# test_openai.py - быстрый тест подключения
import openai
import os
from dotenv import load_dotenv

load_dotenv()


def test_openai_connection():
    try:
        api_key = os.getenv('OPENAI_API_KEY')
        print(f"API Key: {api_key[:10]}...")

        # Простая инициализация
        client = openai.OpenAI(api_key=api_key)
        print("✅ OpenAI клиент создан успешно")

        # Проверяем список моделей
        models = client.models.list()
        whisper_models = [m for m in models.data if 'whisper' in m.id]
        print(f"✅ Найдено Whisper моделей: {len(whisper_models)}")

        return True

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False


if __name__ == "__main__":
    test_openai_connection()