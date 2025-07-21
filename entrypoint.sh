#!/bin/sh
set -e

# Отключаем буферизацию вывода Python для корректного логирования
export PYTHONUNBUFFERED=1

# Читаем переменную окружения PROCESS_TYPE.
# Если она равна "worker", запускаем воркер Celery.
# Во всех остальных случаях (включая "web" или если переменная не задана), запускаем веб-сервер.
if [ "$PROCESS_TYPE" = "worker" ]; then
  echo "Starting Celery worker..."
  exec celery -A celery_worker.celery_app worker --loglevel=info -c 1 --pool=solo
else
  echo "Starting web server..."
  exec hypercorn app:app -b 0.0.0.0:$PORT
fi
