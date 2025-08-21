# Dockerfile - Упрощенная и надежная версия для Render
FROM python:3.11-bullseye

# Явно переключаемся на root для выполнения системных команд
USER root

# Устанавливаем системные зависимости из стандартных репозиториев
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    tor \
    ffmpeg \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файл с зависимостями и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Создаем непривилегированного пользователя для безопасности
RUN useradd --create-home --shell /bin/bash appuser

# Копируем код приложения и устанавливаем правильного владельца
COPY --chown=appuser:appuser . .

# Переключаемся на непривилегированного пользователя для запуска приложения
USER appuser

# Устанавливаем переменную окружения PYTHONPATH
ENV PYTHONPATH /app

# Открываем порт 10000 для доступа извне
EXPOSE 10000

# Команда для запуска. Используем полный путь к tor.
CMD ["sh", "-c", "/usr/bin/tor & sleep 15 && exec python main.py"]
