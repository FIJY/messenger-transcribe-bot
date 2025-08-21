FROM python:3.11-bullseye

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

ENV PYTHONPATH /app
EXPOSE 10000

# Запускаем Tor в фоне и затем приложение
CMD ["sh", "-c", "tor & sleep 5 && python main.py"]