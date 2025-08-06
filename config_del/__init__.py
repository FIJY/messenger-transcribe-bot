# config/__init__.py

# Делаем основные переменные доступными напрямую из пакета config
from .settings import settings
from .constants import (
    START_MESSAGE,
    HELP_MESSAGE,
    PROCESSING_MESSAGE,
    FILE_READY_MESSAGE,
    ERROR_MESSAGE,
    SUCCESS_MESSAGE
)