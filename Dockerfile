FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости из стандартных репозиториев
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    tor \
    ffmpeg \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Копируем файлы проекта
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Проверяем, какие файлы скопировались (для отладки)
RUN ls -la /app/

# Создаем пользователя для безопасности
RUN useradd -m -u 1001 appuser && chown -R appuser:appuser /app
USER appuser

# Открываем порт
EXPOSE 8000

# Команда запуска (измените app.py на ваше имя файла)
CMD ["python", "main.py"]