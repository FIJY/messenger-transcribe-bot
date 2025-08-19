#!/usr/bin/env python3
# manage.py - Скрипт управления приложением
import asyncio
import sys
import subprocess
from pathlib import Path


def start_web():
    """Запуск веб-сервера"""
    subprocess.run(["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"])


def start_worker():
    """Запуск Celery воркера"""
    subprocess.run([
        "celery", "-A", "services.transcription.celery_app", "worker",
        "--loglevel=info", "--concurrency=2", "--max-tasks-per-child=20"
    ])


def start_flower():
    """Запуск Flower для мониторинга"""
    subprocess.run([
        "celery", "-A", "services.transcription.celery_app", "flower",
        "--port=5555"
    ])


def start_monitoring():
    """Запуск системы мониторинга"""
    from monitoring import run_monitoring
    asyncio.run(run_monitoring())


def check_health():
    """Проверка здоровья системы"""
    from health_check import run_health_checks
    result = asyncio.run(run_health_checks())
    print(f"Overall Status: {result['overall_status']}")
    for service, status in result['services'].items():
        print(f"  {service}: {status['status']}")


def setup_environment():
    """Настройка окружения"""
    print("🔧 Настройка окружения...")

    # Создаем необходимые директории
    Path("logs").mkdir(exist_ok=True)
    Path("temp").mkdir(exist_ok=True)

    # Проверяем .env файл
    if not Path(".env").exists():
        print("❌ Файл .env не найден!")
        print("Создайте .env файл с необходимыми переменными:")
        print("TELEGRAM_TOKEN=your_token")
        print("OPENAI_API_KEY=your_key")
        print("MONGODB_URI=mongodb://localhost:27017/")
        sys.exit(1)

    print("✅ Окружение готово")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python manage.py [command]")
        print("Команды:")
        print("  web      - Запуск веб-сервера")
        print("  worker   - Запуск Celery воркера")
        print("  flower   - Запуск Flower мониторинга")
        print("  monitor  - Запуск системного мониторинга")
        print("  health   - Проверка здоровья системы")
        print("  setup    - Настройка окружения")
        sys.exit(1)

    command = sys.argv[1]

    if command == "setup":
        setup_environment()
    elif command == "web":
        start_web()
    elif command == "worker":
        start_worker()
    elif command == "flower":
        start_flower()
    elif command == "monitor":
        start_monitoring()
    elif command == "health":
        check_health()
    else:
        print(f"Неизвестная команда: {command}")