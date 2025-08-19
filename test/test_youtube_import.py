# test_youtube_import.py - Тест корректности импорта YouTube API
import sys

print("🔍 Проверка импорта youtube-transcript-api...")

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

    print("✅ Основной импорт успешен")
except ImportError as e:
    print(f"❌ Основной импорт не удался: {e}")
    try:
        from youtube_transcript_api.youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api.youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled

        print("✅ Альтернативный импорт успешен")
    except ImportError as e2:
        print(f"❌ Альтернативный импорт не удался: {e2}")
        print("💡 Установите: pip install youtube-transcript-api")
        sys.exit(1)

# Проверяем наличие нужных методов
print("🔍 Проверка методов...")

if hasattr(YouTubeTranscriptApi, 'list_transcripts'):
    print("✅ YouTubeTranscriptApi.list_transcripts найден")
else:
    print("❌ YouTubeTranscriptApi.list_transcripts НЕ найден")
    print("💡 Возможно, установлена неправильная версия библиотеки")

if hasattr(YouTubeTranscriptApi, 'get_transcript'):
    print("✅ YouTubeTranscriptApi.get_transcript найден")
else:
    print("❌ YouTubeTranscriptApi.get_transcript НЕ найден")

# Проверяем yt-dlp
print("\n🔍 Проверка yt-dlp...")
try:
    import yt_dlp

    print("✅ yt-dlp импортирован успешно")
except ImportError:
    print("❌ yt-dlp не найден")
    print("💡 Установите: pip install yt-dlp")

# Пробный тест с YouTube видео
print("\n🎬 Тестирование с реальным видео...")
try:
    # Используем публичное видео от YouTube
    test_video_id = "jNQXAC9IVRw"  # "Me at the zoo" - первое видео на YouTube

    transcript_list = YouTubeTranscriptApi.list_transcripts(test_video_id)
    print(f"✅ Получен список субтитров для видео {test_video_id}")

    # Показываем доступные языки
    available_languages = []
    for transcript in transcript_list:
        available_languages.append(transcript.language_code)

    print(f"📄 Доступные языки субтитров: {', '.join(available_languages[:5])}")

    # Пытаемся получить английские субтитры
    try:
        transcript = transcript_list.find_transcript(['en'])
        subtitle_data = transcript.fetch()

        if subtitle_data:
            total_text = ' '.join([item['text'] for item in subtitle_data[:3]])
            print(f"✅ Получены субтитры: {total_text[:100]}...")
        else:
            print("❌ Субтитры пустые")

    except NoTranscriptFound:
        print("❌ Английские субтитры не найдены")

except Exception as e:
    print(f"❌ Ошибка тестирования: {e}")
    print(f"Тип ошибки: {type(e).__name__}")

print("\n🎉 Тест завершен!")
print("\n💡 Если есть ошибки, попробуйте:")
print("   pip uninstall youtube-transcript-api")
print("   pip install youtube-transcript-api>=0.6.0")