FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости и добавляем репозиторий Tor Project
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    apt-transport-https \
    gpg \
    wget \
    lsb-release \
    && echo "deb [signed-by=/usr/share/keyrings/tor-archive-keyring.gpg] https://deb.torproject.org/torproject.org $(lsb_release -cs) main" > /etc/apt/sources.list.d/tor.list \
    && wget -qO- https://deb.torproject.org/torproject.org/A3C4F0F979CAA22CDBA8F512EE8CBC9E886DDD89.asc | gpg --dearmor | tee /usr/share/keyrings/tor-archive-keyring.gpg >/dev/null \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
    tor \
    ffmpeg \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Альтернативный вариант без добавления репозитория Tor Project (если хотите упростить)
# RUN apt-get update && \
#     apt-get install -y --no-install-recommends \
#     tor \
#     ffmpeg \
#     && apt-get clean && \
#     rm -rf /var/lib/apt/lists/*

# Копируем файлы проекта
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Создаем пользователя для безопасности
RUN useradd -m -u 1001 appuser && chown -R appuser:appuser /app
USER appuser

# Открываем порт
EXPOSE 8000

# Команда запуска
CMD ["python", "app.py"]