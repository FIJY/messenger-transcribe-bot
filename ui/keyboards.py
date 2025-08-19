# ui/keyboards.py - ПОЛНЫЕ ОБНОВЛЕННЫЕ клавиатуры с отслеживанием выбранных опций
from typing import Dict, Set
from config import SUBSCRIPTION_PLANS, QUICK_FORMATS, PROCESSING_CATEGORIES, EXPORT_FORMATS
from ui.localization import LocalizationService


def create_post_transcription_keyboard(transcription_id: str, user_balance_minutes: int) -> Dict:
    """
    ГЛАВНАЯ клавиатура после транскрипции.
    ВСЕ форматы обработки БЕСПЛАТНЫ
    """
    return create_post_transcription_keyboard_with_selections(transcription_id, user_balance_minutes, set())


def create_post_transcription_keyboard_with_selections(transcription_id: str, user_balance_minutes: int,
                                                       selected_formats: Set[str]) -> Dict:
    """
    ГЛАВНАЯ клавиатура с отметками выбранных форматов
    """
    keyboard = []

    # Первый ряд: показываем текст транскрипции
    keyboard.append([
        {"text": "📝 Показать полный текст", "callback_data": f"show_text:{transcription_id}"}
    ])

    # Популярные форматы с отметками ✅ для выбранных
    popular_row_1 = []
    popular_row_2 = []

    for i, (format_key, format_info) in enumerate(QUICK_FORMATS.items()):
        # Добавляем ✅ если формат уже выбран
        check_mark = "✅ " if format_key in selected_formats else ""
        button_text = f"{check_mark}{format_info['emoji']} {format_info['name']}"
        callback_data = f"process:{transcription_id}:{format_key}"

        button = {"text": button_text, "callback_data": callback_data}

        # Распределяем по рядам (2 кнопки в ряд)
        if i < 2:
            popular_row_1.append(button)
        else:
            popular_row_2.append(button)

    keyboard.append(popular_row_1)
    if popular_row_2:
        keyboard.append(popular_row_2)

    # Кнопка "Еще варианты"
    keyboard.append([
        {"text": "📄 Еще варианты...", "callback_data": f"categories:{transcription_id}"}
    ])

    # Экспорт форматы (тоже бесплатно!)
    keyboard.append([
        {"text": "💾 Скачать файлы", "callback_data": f"export:{transcription_id}"}
    ])

    # Кнопка очистки выбранных (если что-то выбрано)
    if selected_formats:
        keyboard.append([
            {"text": "🗑️ Очистить выбранное", "callback_data": f"clear_selections:{transcription_id}"}
        ])

    return {"inline_keyboard": keyboard}


def create_categories_keyboard(transcription_id: str, user_balance_minutes: int) -> Dict:
    """Клавиатура выбора категорий - все доступны бесплатно"""
    return create_categories_keyboard_with_selections(transcription_id, user_balance_minutes, set())


def create_categories_keyboard_with_selections(transcription_id: str, user_balance_minutes: int,
                                               selected_formats: Set[str]) -> Dict:
    """Клавиатура выбора категорий с отметками"""
    keyboard = []

    # Показываем все категории с отметками если в них есть выбранные форматы
    for category_key, category_info in PROCESSING_CATEGORIES.items():
        # Проверяем есть ли выбранные форматы в этой категории
        category_has_selected = False
        selected_count = 0

        for fmt in selected_formats:
            if fmt in category_info.get("formats", {}):
                category_has_selected = True
                selected_count += 1

        # Формируем текст кнопки с информацией о выбранных
        if category_has_selected:
            if selected_count == 1:
                check_mark = "✅ "
            else:
                check_mark = f"✅({selected_count}) "
        else:
            check_mark = ""

        button_text = f"{check_mark}{category_info['emoji']} {category_info['name']}"
        keyboard.append([
            {"text": button_text, "callback_data": f"category:{transcription_id}:{category_key}"}
        ])

    # Кнопка назад
    keyboard.append([
        {"text": "🔙 Назад", "callback_data": f"back_to_main:{transcription_id}"}
    ])

    return {"inline_keyboard": keyboard}


def create_category_formats_keyboard(transcription_id: str, category_key: str, user_balance_minutes: int) -> Dict:
    """Клавиатура форматов внутри категории - все доступны бесплатно"""
    return create_category_formats_keyboard_with_selections(transcription_id, category_key, user_balance_minutes, set())


def create_category_formats_keyboard_with_selections(transcription_id: str, category_key: str,
                                                     user_balance_minutes: int, selected_formats: Set[str]) -> Dict:
    """Клавиатура форматов внутри категории с отметками"""
    keyboard = []

    category_info = PROCESSING_CATEGORIES.get(category_key, {})
    formats = category_info.get("formats", {})

    for format_key, format_info in formats.items():
        # Добавляем ✅ если формат уже выбран
        check_mark = "✅ " if format_key in selected_formats else ""
        button_text = f"{check_mark}{format_info['name']}"
        callback_data = f"process:{transcription_id}:{format_key}"

        keyboard.append([
            {"text": button_text, "callback_data": callback_data}
        ])

    # Кнопки навигации
    keyboard.append([
        {"text": "🔙 К категориям", "callback_data": f"categories:{transcription_id}"},
        {"text": "🏠 В главное меню", "callback_data": f"back_to_main:{transcription_id}"}
    ])

    return {"inline_keyboard": keyboard}


def create_processing_result_keyboard(transcription_id: str) -> Dict:
    """ОБНОВЛЕННАЯ клавиатура после получения результата обработки"""
    return {
        "inline_keyboard": [
            [
                {"text": "🔄 Другой формат", "callback_data": f"categories:{transcription_id}"},
                {"text": "💾 Скачать файлы", "callback_data": f"export:{transcription_id}"}
            ],
            [
                {"text": "📝 Показать текст", "callback_data": f"show_text:{transcription_id}"},
                {"text": "🎯 Главные форматы", "callback_data": f"back_to_main:{transcription_id}"}
            ],
            [{"text": "🏠 Главное меню", "callback_data": "start"}]
        ]
    }


def create_export_keyboard(transcription_id: str) -> Dict:
    """Клавиатура выбора формата экспорта - бесплатно"""
    keyboard = []

    # Основные форматы экспорта (2 в ряд)
    row1 = [
        {"text": "📄 .txt", "callback_data": f"export_format:{transcription_id}:txt"},
        {"text": "📋 .docx", "callback_data": f"export_format:{transcription_id}:docx"}
    ]
    row2 = [
        {"text": "📑 PDF", "callback_data": f"export_format:{transcription_id}:pdf"},
        {"text": "📜 .srt", "callback_data": f"export_format:{transcription_id}:srt"}
    ]

    keyboard.extend([row1, row2])

    # Все форматы сразу
    keyboard.append([
        {"text": "📦 Скачать все форматы", "callback_data": f"export_all:{transcription_id}"}
    ])

    # Назад
    keyboard.append([
        {"text": "🔙 Назад", "callback_data": f"back_to_main:{transcription_id}"}
    ])

    return {"inline_keyboard": keyboard}


def create_subscription_keyboard(current_plan: str, current_balance: int) -> Dict:
    """Клавиатура выбора подписки - АКЦЕНТ НА ТРАНСКРИПЦИИ"""
    keyboard = []

    for plan_key, plan_info in SUBSCRIPTION_PLANS.items():
        if plan_key == "trial":
            continue  # Триал не продаем

        # Помечаем текущий план
        if plan_key == current_plan:
            button_text = f"✅ {plan_info['name']} (текущий)"
            callback_data = f"current_plan:{plan_key}"
        else:
            # Акцент на минутах транскрипции
            button_text = f"{plan_info['name']} - {plan_info['minutes']}мин - {plan_info['price_rub']}₽"
            callback_data = f"buy_plan:{plan_key}"

        keyboard.append([
            {"text": button_text, "callback_data": callback_data}
        ])

    # Показать текущий баланс с пояснением
    balance_text = f"💰 Баланс транскрипции: {current_balance} мин"
    keyboard.append([
        {"text": balance_text, "callback_data": "show_balance"}
    ])

    # Пояснение что обработка бесплатна
    keyboard.append([
        {"text": "✨ Обработка текста всегда бесплатна!", "callback_data": "processing_info"}
    ])

    # Назад
    keyboard.append([
        {"text": "🔙 В главное меню", "callback_data": "start"}
    ])

    return {"inline_keyboard": keyboard}


def create_balance_keyboard(localization: LocalizationService, lang: str) -> Dict:
    """Клавиатура управления балансом - акцент на транскрипции"""
    return {
        "inline_keyboard": [
            [{"text": "💎 Купить минуты транскрипции", "callback_data": "subscription:main"}],
            [{"text": "📊 История использования", "callback_data": "balance:history"}],
            [{"text": "✨ Обработка всегда бесплатна", "callback_data": "processing_info"}],
            [{"text": "🔙 Назад", "callback_data": "start"}]
        ]
    }


def create_main_menu_keyboard(localization: LocalizationService, lang: str) -> Dict:
    """Главное меню бота - обновленное"""
    return {
        "inline_keyboard": [
            [
                {"text": "💰 Подписка", "callback_data": "subscription:main"},
                {"text": "⚙️ Настройки", "callback_data": "settings:main"}
            ],
            [
                {"text": "❓ Помощь", "callback_data": "help:main"},
                {"text": "📊 Мой баланс", "callback_data": "balance:main"}
            ],
            [
                {"text": "✨ Обработка бесплатна!", "callback_data": "processing_info"}
            ]
        ]
    }


def create_settings_keyboard(localization: LocalizationService, lang: str) -> Dict:
    """Клавиатура настроек"""
    return {
        "inline_keyboard": [
            [{"text": "🌍 Сменить язык", "callback_data": "settings:language"}],
            [{"text": "💬 Уведомления", "callback_data": "settings:notifications"}],
            [{"text": "🔙 Назад", "callback_data": "start"}]
        ]
    }


def create_language_selection_keyboard(localization: LocalizationService, lang: str) -> Dict:
    """Клавиатура выбора языка"""
    keyboard = [
        [
            {"text": "🇷🇺 Русский", "callback_data": "settings:set_lang:ru"},
            {"text": "🇺🇸 English", "callback_data": "settings:set_lang:en"}
        ],
        [{"text": "🔙 Назад", "callback_data": "settings:main"}]
    ]
    return {"inline_keyboard": keyboard}


def create_insufficient_balance_keyboard(required_minutes: int) -> Dict:
    """Клавиатура когда не хватает баланса ДЛЯ ТРАНСКРИПЦИИ"""
    return {
        "inline_keyboard": [
            [{"text": f"💎 Купить {required_minutes}+ минут", "callback_data": "subscription:main"}],
            [{"text": "✨ А обработка бесплатна!", "callback_data": "processing_info"}],
            [{"text": "🔙 Назад", "callback_data": "back"}]
        ]
    }


# ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ УДОБСТВА

def create_selection_status_text(selected_formats: Set[str]) -> str:
    """Создает текст статуса выбранных форматов"""
    if not selected_formats:
        return ""

    format_names = []
    for fmt in selected_formats:
        if fmt in QUICK_FORMATS:
            format_names.append(QUICK_FORMATS[fmt]['name'])
        else:
            # Ищем в категориях
            for category in PROCESSING_CATEGORIES.values():
                if fmt in category.get('formats', {}):
                    format_names.append(category['formats'][fmt]['name'])
                    break

    if len(format_names) <= 3:
        return f"\n\n✅ Выбрано: {', '.join(format_names)}"
    else:
        return f"\n\n✅ Выбрано: {', '.join(format_names[:2])}, +{len(format_names) - 2} еще"


def get_format_name(format_key: str) -> str:
    """Получает название формата по его ключу"""
    if format_key in QUICK_FORMATS:
        return QUICK_FORMATS[format_key]['name']

    # Ищем в категориях
    for category in PROCESSING_CATEGORIES.values():
        if format_key in category.get('formats', {}):
            return category['formats'][format_key]['name']

    return format_key  # Fallback


def create_keyboard_with_persistent_menu(base_keyboard: Dict, transcription_id: str,
                                         action_text: str = None) -> Dict:
    """
    Создает клавиатуру с постоянным меню внизу

    Args:
        base_keyboard: Основная клавиатура
        transcription_id: ID транскрипции
        action_text: Дополнительный текст для отображения
    """
    keyboard_rows = base_keyboard["inline_keyboard"].copy()

    # Добавляем разделитель
    keyboard_rows.append([
        {"text": "─────────────", "callback_data": "separator"}
    ])

    # Добавляем постоянное меню
    persistent_menu = [
        [
            {"text": "🎯 Главное меню", "callback_data": f"back_to_main:{transcription_id}"},
            {"text": "📝 Показать текст", "callback_data": f"show_text:{transcription_id}"}
        ],
        [
            {"text": "💾 Экспорт", "callback_data": f"export:{transcription_id}"},
            {"text": "📊 Форматы", "callback_data": f"categories:{transcription_id}"}
        ]
    ]

    keyboard_rows.extend(persistent_menu)

    return {"inline_keyboard": keyboard_rows}


def create_compact_selection_indicator(selected_formats: Set[str], max_display: int = 2) -> str:
    """Создает компактный индикатор выбранных форматов для кнопок"""
    if not selected_formats:
        return ""

    count = len(selected_formats)
    if count == 1:
        return "✅ "
    elif count <= max_display:
        return f"✅({count}) "
    else:
        return f"✅({count}+) "


def get_category_selection_count(category_key: str, selected_formats: Set[str]) -> int:
    """Возвращает количество выбранных форматов в категории"""
    category_info = PROCESSING_CATEGORIES.get(category_key, {})
    category_formats = category_info.get("formats", {})

    count = 0
    for fmt in selected_formats:
        if fmt in category_formats:
            count += 1

    return count


def create_smart_navigation_keyboard(transcription_id: str, current_location: str,
                                     selected_formats: Set[str]) -> Dict:
    """
    Создает умную навигационную клавиатуру в зависимости от текущего местоположения

    Args:
        transcription_id: ID транскрипции
        current_location: Текущее местоположение ('main', 'categories', 'category', 'export')
        selected_formats: Выбранные форматы
    """
    keyboard = []

    if current_location == 'categories':
        keyboard.append([
            {"text": "🎯 К главному меню", "callback_data": f"back_to_main:{transcription_id}"}
        ])
    elif current_location == 'category':
        keyboard.append([
            {"text": "🔙 К категориям", "callback_data": f"categories:{transcription_id}"},
            {"text": "🎯 Главное меню", "callback_data": f"back_to_main:{transcription_id}"}
        ])
    elif current_location == 'export':
        keyboard.append([
            {"text": "🔙 К форматам", "callback_data": f"back_to_main:{transcription_id}"}
        ])

    # Добавляем быстрые действия если есть выбранные форматы
    if selected_formats:
        quick_actions = []

        if len(selected_formats) > 1:
            quick_actions.append({
                "text": f"🗑️ Очистить ({len(selected_formats)})",
                "callback_data": f"clear_selections:{transcription_id}"
            })

        quick_actions.append({
            "text": "💾 Экспорт",
            "callback_data": f"export:{transcription_id}"
        })

        if quick_actions:
            keyboard.append(quick_actions)

    return {"inline_keyboard": keyboard}


def create_adaptive_format_keyboard(transcription_id: str, category_key: str,
                                    selected_formats: Set[str], max_per_row: int = 2) -> Dict:
    """
    Создает адаптивную клавиатуру форматов с оптимальным распределением кнопок

    Args:
        transcription_id: ID транскрипции
        category_key: Ключ категории
        selected_formats: Выбранные форматы
        max_per_row: Максимум кнопок в ряду
    """
    keyboard = []

    category_info = PROCESSING_CATEGORIES.get(category_key, {})
    formats = category_info.get("formats", {})

    # Группируем форматы по рядам
    current_row = []
    for format_key, format_info in formats.items():
        check_mark = "✅ " if format_key in selected_formats else ""
        button_text = f"{check_mark}{format_info['name']}"

        # Сокращаем длинные названия для лучшего отображения
        if len(button_text) > 25:
            button_text = button_text[:22] + "..."

        button = {
            "text": button_text,
            "callback_data": f"process:{transcription_id}:{format_key}"
        }

        current_row.append(button)

        # Если ряд заполнен или это последний элемент
        if len(current_row) >= max_per_row:
            keyboard.append(current_row)
            current_row = []

    # Добавляем последний неполный ряд
    if current_row:
        keyboard.append(current_row)

    # Навигационные кнопки
    nav_keyboard = create_smart_navigation_keyboard(transcription_id, 'category', selected_formats)
    keyboard.extend(nav_keyboard["inline_keyboard"])

    return {"inline_keyboard": keyboard}


def create_progress_indicator(completed_formats: Set[str], total_available: int) -> str:
    """Создает индикатор прогресса выполнения"""
    completed = len(completed_formats)

    if completed == 0:
        return ""
    elif completed == total_available:
        return f"🎉 Все готово ({completed}/{total_available})"
    else:
        percentage = int((completed / total_available) * 100)
        return f"📊 Прогресс: {completed}/{total_available} ({percentage}%)"


def create_summary_keyboard(transcription_id: str, selected_formats: Set[str],
                            available_exports: Dict[str, bool]) -> Dict:
    """
    Создает итоговую клавиатуру с обзором всех доступных действий

    Args:
        transcription_id: ID транскрипции
        selected_formats: Выбранные форматы для обработки
        available_exports: Доступные форматы экспорта
    """
    keyboard = []

    # Основные действия
    main_actions = [
        {"text": "📝 Показать текст", "callback_data": f"show_text:{transcription_id}"},
        {"text": "🔄 Еще форматы", "callback_data": f"categories:{transcription_id}"}
    ]
    keyboard.append(main_actions)

    # Экспорт если доступен
    export_count = sum(1 for available in available_exports.values() if available)
    if export_count > 0:
        keyboard.append([
            {"text": f"💾 Экспорт ({export_count} форматов)", "callback_data": f"export:{transcription_id}"}
        ])

    # Управление выбранными форматами
    if selected_formats:
        selection_actions = []

        if len(selected_formats) > 3:
            selection_actions.append({
                "text": f"📋 Список ({len(selected_formats)})",
                "callback_data": f"show_selections:{transcription_id}"
            })

        selection_actions.append({
            "text": "🗑️ Очистить выбранное",
            "callback_data": f"clear_selections:{transcription_id}"
        })

        keyboard.append(selection_actions)

    # Дополнительные опции
    keyboard.append([
        {"text": "⚙️ Настройки", "callback_data": "settings:main"},
        {"text": "💰 Подписка", "callback_data": "subscription:main"}
    ])

    return {"inline_keyboard": keyboard}