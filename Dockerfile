# Dockerfile

# Используем официальный образ Python
FROM python:3.11.4-slim

# Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# Устанавливаем переменные окружения
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Устанавливаем системные зависимости, необходимые для сборки некоторых пакетов
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Создаем виртуальное окружение
RUN python -m venv .venv
ENV PATH="/app/.venv/bin:$PATH"

# Копируем файл с зависимостями
COPY requirements.txt .

# Устанавливаем зависимости в виртуальное окружение
# Правильный способ вызова pip из venv
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта в рабочую директорию
COPY . .

# Команда для запуска приложения (может быть переопределена в render.yaml)
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--worker-class", "uvicorn.workers.UvicornWorker", "app:app"]