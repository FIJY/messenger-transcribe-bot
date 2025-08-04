# utils/message_formatter.py
import json


def create_options_keyboard(note_id: str, selected_options: set = None) -> str:
    """Создает JSON-строку с inline-клавиатурой для Telegram."""
    if selected_options is None:
        selected_options = set()

    # Опции, которые мы предлагаем пользователю
    options = {
        "summary": "📝 Краткое содержание",
        "keywords": "🔑 Ключевые слова",
    }

    keyboard_buttons = []
    # Создаем кнопки для каждой опции
    for code, text in options.items():
        button_text = f"✓ {text}" if code in selected_options else text
        callback_data = f"{code}:{note_id}:{','.join(sorted(list(selected_options)))}"
        keyboard_buttons.append([{"text": button_text, "callback_data": callback_data}])

    # Добавляем финальную кнопку "Готово"
    final_selection_str = ",".join(sorted(list(selected_options)))
    keyboard_buttons.append([
        {"text": "🚀 Готово к обработке", "callback_data": f"process:{note_id}:{final_selection_str}"}
    ])

    reply_markup = {"inline_keyboard": keyboard_buttons}
    # Конвертируем словарь в JSON-строку
    return json.dumps(reply_markup)