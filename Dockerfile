# Используем официальный образ Python
FROM python:3.11-slim

# Устанавливаем системные зависимости, включая ffmpeg
# Это решит проблему "Read-only file system"
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Создаем рабочую директорию
WORKDIR /app

# Копируем файл с зависимостями и устанавливаем их
# Также принудительно обновляем yt-dlp до последней версии
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade yt-dlp && \
    pip install --no-cache-dir -r requirements.txt

# Копируем весь остальной код проекта в рабочую директорию
COPY . .

# Render будет использовать startCommand из render.yaml, поэтому CMD здесь не нужен
