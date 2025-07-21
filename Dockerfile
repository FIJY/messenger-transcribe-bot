# Используем официальный образ Python
FROM python:3.11-slim

# Устанавливаем системные зависимости, включая ffmpeg
# Это решит проблему "Read-only file system"
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Создаем рабочую директорию
WORKDIR /app

# Копируем файл с зависимостями и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade yt-dlp && \
    pip install --no-cache-dir -r requirements.txt

# Копируем весь остальной код проекта
COPY . .

# Копируем и делаем исполняемым наш скрипт-точку входа
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Указываем, что все команды должны запускаться через этот скрипт
ENTRYPOINT ["./entrypoint.sh"]
