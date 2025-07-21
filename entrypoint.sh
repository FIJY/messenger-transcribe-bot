#!/bin/sh
set -e

# Этот скрипт определяет, какой процесс нужно запустить,
# основываясь на переменной окружения PROCESS_TYPE.

# Отключаем буферизацию вывода Python для корректного логирования
export PYTHONUNBUFFERED=1

# Если PROCESS_TYPE="worker", запускаем воркер Celery
if [ "$PROCESS_TYPE" = "worker" ]; then
  echo "Starting Celery worker..."
  exec celery -A celery_worker.celery_app worker --loglevel=info -c 1 --pool=solo

# Если PROCESS_TYPE="beat", запускаем планировщик Celery
elif [ "$PROCESS_TYPE" = "beat" ]; then
  echo "Starting Celery beat..."
  exec celery -A celery_worker.celery_app beat --loglevel=info

# Во всех остальных случаях (включая "web" или если переменная не задана), запускаем веб-сервер
else
  echo "Starting web server..."
  exec hypercorn app:app -b 0.0.0.0:$PORT
fi
