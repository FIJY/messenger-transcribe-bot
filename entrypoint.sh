#!/bin/sh

# Этот скрипт определяет, какой процесс нужно запустить,
# основываясь на команде из render.yaml.

# Отключаем буферизацию вывода Python для корректного логирования
export PYTHONUNBUFFERED=1

# Если первый аргумент - "web", запускаем веб-сервер
if [ "$1" = "web" ]; then
  echo "Starting web server..."
  exec hypercorn app:app -b 0.0.0.0:$PORT

# Если первый аргумент - "worker", запускаем воркер Celery
elif [ "$1" = "worker" ]; then
  echo "Starting celery worker..."
  exec celery -A celery_worker.celery_app worker --loglevel=info -c 1 --pool=solo

# Иначе, выполняем команду как есть
else
  exec "$@"
fi
