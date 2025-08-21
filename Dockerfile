# Dockerfile - Финальная версия с установкой последней версии Tor
FROM python:3.11-bullseye

# Явно переключаемся на root для выполнения системных команд
USER root

# Устанавливаем системные зависимости и добавляем репозиторий Tor Project
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    apt-transport-https \
    gpg \
    && echo "deb [signed-by=/usr/share/keyrings/tor-archive-keyring.gpg] https://deb.torproject.org/torproject.org $(lsb_release -cs) main" > /etc/apt/sources.list.d/tor.list \
    && wget -qO- https://deb.torproject.org/torproject.org/A3C4F0F979CAA22CDBA8F512EE8CBC9E886DDD89.asc | gpg --dearmor | tee /usr/share/keyrings/tor-archive-keyring.gpg >/dev/null \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
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
