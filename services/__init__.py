# services/__init__.py - ИСПРАВЛЕННАЯ ВЕРСИЯ

# ВРЕМЕННО УБИРАЕМ ВСЕ ИМПОРТЫ для решения проблемы с Celery
# Это позволит Celery запуститься без циклических импортов

# Пустой файл - сервисы будут импортироваться напрямую
# from services.transcription import TranscriptionService
# from services.smart_video_service import SmartVideoService

__all__ = []

# Для импорта используйте:
# from services.transcription import TranscriptionService
# from services.smart_video_service import SmartVideoService