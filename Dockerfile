# Используем официальный образ Python
FROM python:3.11-slim

# Устанавливаем переменные окружения
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PATH="/app/.venv/bin:$PATH"

# Устанавливаем системные зависимости
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg build-essential && \
    rm -rf /var/lib/apt/lists/*

# Создаем рабочую директорию
WORKDIR /app

# Копируем все файлы проекта
COPY . .

# !!! --- ВАЖНОЕ ИЗМЕНЕНИЕ --- !!!
# Делаем скрипт исполняемым, ПОКА МЫ ЕЩЕ ROOT
RUN chmod +x entrypoint.sh

# Создаем пользователя без root-прав и делаем его владельцем файлов
RUN adduser --system --group appuser
RUN chown -R appuser:appuser /app

# Теперь переключаемся на пользователя без прав root
USER appuser

# Создаем виртуальное окружение и устанавливаем зависимости
RUN python -m venv /app/.venv
# Обратите внимание, что requirements.txt уже скопирован вместе со всем остальным
RUN . /app/.venv/bin/activate && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Указываем, что все команды должны запускаться через этот скрипт
ENTRYPOINT ["./entrypoint.sh"]