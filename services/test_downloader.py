# services/test_downloader_ytdlp.py
import os
import sys
from pathlib import Path

# Добавляем путь к модулям
sys.path.append(str(Path(__file__).parent))

from downloader_service import DownloaderService


def test_youtube_download():
    print("=== ТЕСТ СКАЧИВАНИЯ С YOUTUBE ===")

    # Тестовые URL (короткие видео)
    test_urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # Rick Roll
        "https://youtu.be/dQw4w9WgXcQ",  # Короткая версия
        # "https://www.youtube.com/watch?v=9bZkp7q19f0",  # Другое тестовое видео
    ]

    downloader = DownloaderService()

    for i, url in enumerate(test_urls, 1):
        print(f"\n--- Тест {i}: {url} ---")

        file_path, error = downloader.download_audio(url)

        if file_path:
            print(f"✅ УСПЕХ!")
            print(f"   Файл: {file_path}")

            # Проверяем размер файла
            if Path(file_path).exists():
                size_mb = Path(file_path).stat().st_size / (1024 * 1024)
                print(f"   Размер: {size_mb:.2f} MB")

            # Предлагаем удалить тестовый файл
            response = input("   Удалить тестовый файл? (y/n): ")
            if response.lower() == 'y':
                try:
                    Path(file_path).unlink()
                    print("   Файл удален.")
                except:
                    print("   Ошибка при удалении.")
        else:
            print(f"❌ ОШИБКА: {error}")


if __name__ == "__main__":
    # Устанавливаем yt-dlp если нужно
    try:
        import yt_dlp

        print("yt-dlp найден ✅")
    except ImportError:
        print("❌ yt-dlp не найден!")
        print("Установите: pip install yt-dlp")
        sys.exit(1)

    test_youtube_download()
    print("\n=== ТЕСТ ЗАВЕРШЕН ===")