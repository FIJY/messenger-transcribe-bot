FROM python:3.11-bullseye

USER root

RUN apt-get update && apt-get install -y \
    tor \
    netcat-openbsd \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/* \

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --shell /bin/bash appuser
COPY --chown=appuser:appuser . .
USER appuser

ENV PYTHONPATH /app
EXPOSE 10000

CMD ["sh", "-c", "/usr/bin/tor & sleep 15 && exec python main.py"]
