# Dockerfile - Финальная, надежная версия для Render
FROM python:3.11-bullseye

# Устанавливаем системные зависимости
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    tor \
    ffmpeg \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файл с зависимостями и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Создаем непривилегированного пользователя для безопасности
RUN useradd --create-home --shell /bin/bash appuser

# Копируем код приложения и устанавливаем правильного владельца
COPY --chown=appuser:appuser . .

# Переключаемся на непривилегированного пользователя
USER appuser

# Устанавливаем переменную окружения PYTHONPATH
ENV PYTHONPATH /app

# Открываем порт 10000 для доступа извне
EXPOSE 10000

# Копируем стартовый скрипт и делаем его исполняемым
COPY --chown=appuser:appuser entrypoint.sh .
RUN chmod +x ./entrypoint.sh

# Указываем, что контейнер должен запускаться с помощью нашего скрипта
ENTRYPOINT ["./entrypoint.sh"]
