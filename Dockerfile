FROM python:3.11-slim

# Обновляем пакеты и устанавливаем системные зависимости
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    tor \
    ffmpeg \
    curl \
    build-essential \
    procps \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Проверяем установку Tor
RUN which tor || (echo "ERROR: Tor not found after installation" && exit 1)
RUN tor --version || (echo "ERROR: Tor version check failed" && exit 1)

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файл с зависимостями и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY . .

# Устанавливаем переменную окружения PYTHONPATH
ENV PYTHONPATH=/app

# Создаем конфигурацию Tor
RUN echo "SocksPort 9050" > /etc/tor/torrc && \
    echo "RunAsDaemon 1" >> /etc/tor/torrc && \
    echo "Log notice stdout" >> /etc/tor/torrc && \
    echo "DataDirectory /tmp/tor" >> /etc/tor/torrc

# Создаем директорию для данных Tor
RUN mkdir -p /tmp/tor && chmod 700 /tmp/tor

# Открываем порт 10000 для доступа извне
EXPOSE 10000

# Финальная проверка что все на месте
RUN echo "=== Build verification ===" && \
    which tor && \
    tor --version && \
    python --version && \
    echo "=== Build complete ==="

# Команда по умолчанию (будет переопределена в render.yaml)
CMD ["python", "main.py"]