FROM python:3.11-bullseye

USER root

# Добавляем официальный репозиторий Tor Project
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gnupg curl && \
    curl -sSL https://deb.torproject.org/torproject.org/pubkey.asc | gpg --dearmor -o /usr/share/keyrings/tor-archive-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/tor-archive-keyring.gpg] https://deb.torproject.org/torproject.org bullseye main" > /etc/apt/sources.list.d/tor.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    tor deb.torproject.org-keyring ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --shell /bin/bash appuser
COPY --chown=appuser:appuser . .

USER appuser

ENV PYTHONPATH /app
EXPOSE 10000

CMD ["sh", "-c", "/usr/bin/tor & sleep 15 && exec python main.py"]
