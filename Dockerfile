FROM python:3.11-bullseye

# Обновляем пакеты и устанавливаем системные зависимости
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    tor \
    ffmpeg \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app
EXPOSE 10000

# Конфигурируем Tor
RUN echo "SocksPort 9050" >> /etc/tor/torrc && \
    echo "ControlPort 9051" >> /etc/tor/torrc

# Запускаем Tor и приложение
CMD ["sh", "-c", "tor --RunAsDaemon 1 --SocksPort 9050 && sleep 10 && python main.py"]