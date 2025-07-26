# Используем официальный образ Python
FROM python:3.11-slim

# Устанавливаем переменные окружения для отключения буферизации и указания пути
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PATH="/app/.venv/bin:$PATH"

# Устанавливаем системные зависимости, включая ffmpeg и build-essential для некоторых пакетов
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg build-essential && \
    rm -rf /var/lib/apt/lists/*

# Создаем рабочую директорию и пользователя без root-прав
WORKDIR /app
RUN adduser --system --group appuser
COPY . .
RUN chown -R appuser:appuser /app

# Переключаемся на пользователя без прав root
USER appuser

# Создаем виртуальное окружение и устанавливаем зависимости
RUN python -m venv /app/.venv
COPY requirements.txt .
RUN . /app/.venv/bin/activate && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем и делаем исполняемым наш скрипт-точку входа
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Указываем, что все команды должны запускаться через этот скрипт
ENTRYPOINT ["./entrypoint.sh"]