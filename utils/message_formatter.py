# utils/message_formatter.py
from telegram_bot_sdk.telegram_objects.inline_keyboard import InlineKeyboardMarkup, InlineKeyboardButton


def create_options_keyboard(note_id: str, selected_options: set = None) -> InlineKeyboardMarkup:
    """Создает клавиатуру с опциями для обработки."""
    if selected_options is None:
        selected_options = set()

    options = {
        "summary": "📝 Краткое содержание",
        "keywords": "🔑 Ключевые слова",
        "action_items": "✅ Задачи (Action Items)"
    }

    keyboard = []
    for code, text in options.items():
        # Добавляем галочку, если опция выбрана
        button_text = f"✓ {text}" if code in selected_options else text

        # Собираем строку с текущими выбранными опциями для callback_data
        current_selection_str = ",".join(sorted(list(selected_options)))

        keyboard.append([
            InlineKeyboardButton(
                button_text,
                callback_data=f"{code}:{note_id}:{current_selection_str}"
            )
        ])

    # Кнопка "Готово"
    final_selection_str = ",".join(sorted(list(selected_options)))
    keyboard.append([
        InlineKeyboardButton(
            "🚀 Готово",
            callback_data=f"process:{note_id}:{final_selection_str}"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def format_processed_message(full_text: str, insights: dict) -> str:
    """Форматирует финальное сообщение с результатами обработки."""
    message = f"📜 *Полная транскрипция:*\n`{full_text}`\n\n"

    if insights.get("summary"):
        message += f"📝 *Краткое содержание:*\n{insights['summary']}\n\n"

    if insights.get("keywords"):
        keywords = ", ".join(insights['keywords'])
        message += f"🔑 *Ключевые слова:*\n{keywords}\n\n"

    # ... добавьте другие инсайты по аналогии

    return message