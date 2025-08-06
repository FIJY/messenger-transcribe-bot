# ui/keyboards.py - UI компоненты клавиатур
from typing import Dict, List, Optional
from config_del import PROCESSING_CATEGORIES, QUICK_PACKS, PLANS


def create_main_menu_keyboard(lang: str) -> Dict:
    """Создает главное меню бота"""
    return {
        "inline_keyboard": [
            [
                {"text": "🔑 Подписка", "callback_data": "subscription:main"},
                {"text": "⚙️ Настройки", "callback_data": "settings:main"}
            ],
            [
                {"text": "❓ Помощь", "callback_data": "help:main"},
                {"text": "💰 Баланс", "callback_data": "balance:main"}
            ]
        ]
    }


def create_processing_menu_keyboard(audio_file_id: str, user_plan: str, lang: str,
                                    selected_options: Optional[List[str]] = None) -> Dict:
    """Создает меню выбора опций обработки"""
    if selected_options is None:
        selected_options = []

    plan_info = PLANS[user_plan]
    max_options = plan_info['processing_options']
    keyboard = []

    # Заголовок с информацией о лимитах
    keyboard.append([
        {"text": f"📋 Выбрано: {len(selected_options)} из {max_options}", "callback_data": "info:limits"}
    ])

    # Быстрые пакеты
    if len(QUICK_PACKS) > 0:
        keyboard.append([
            {"text": "🎯 БЫСТРЫЙ ВЫБОР", "callback_data": "info:quick_packs"}
        ])

        quick_row = []
        for pack_code, pack_info in QUICK_PACKS.items():
            if len(pack_info['options']) <= max_options:
                quick_row.append({
                    "text": f"⚡ {pack_info['label']}",
                    "callback_data": f"processing:quick_pack:{audio_file_id}:{pack_code}"
                })
                if len(quick_row) == 2:  # Максимум 2 кнопки в ряду
                    keyboard.append(quick_row)
                    quick_row = []

        if quick_row:
            keyboard.append(quick_row)

        # Разделитель
        keyboard.append([
            {"text": "─" * 25, "callback_data": "info:separator"}
        ])

    # Категории опций
    for category_code, category_info in PROCESSING_CATEGORIES.items():
        # Заголовок категории
        keyboard.append([
            {"text": f"🔸 {category_info['name']}", "callback_data": f"info:category:{category_code}"}
        ])

        # Опции в категории
        for option in category_info['options']:
            option_code = option['code']
            is_selected = option_code in selected_options
            is_disabled = len(selected_options) >= max_options and not is_selected

            if is_selected:
                button_text = f"✅ {option['name']}"
            elif is_disabled:
                button_text = f"🚫 {option['name']}"
            else:
                button_text = f"⭕ {option['name']}"

            keyboard.append([{
                "text": button_text,
                "callback_data": f"processing:toggle:{audio_file_id}:{option_code}"
            }])

    # Управляющие кнопки
    keyboard.append([
        {"text": "═" * 20, "callback_data": "info:separator"}
    ])

    control_row = []

    # Кнопка сброса
    if selected_options:
        control_row.append({
            "text": "🔄 Сброс",
            "callback_data": f"processing:reset:{audio_file_id}"
        })

    # Кнопка запуска обработки
    if selected_options:
        control_row.append({
            "text": f"🚀 Обработать ({len(selected_options)})",
            "callback_data": f"process_start:{audio_file_id}"
        })

    if control_row:
        keyboard.append(control_row)

    return {"inline_keyboard": keyboard}


def create_language_selection_keyboard() -> Dict:
    """Создает клавиатуру выбора языка"""
    languages = [
        ("🇷🇺", "Русский", "ru"),
        ("🇺🇸", "English", "en"),
        ("🇨🇳", "中文", "zh"),
        ("🇪🇸", "Español", "es"),
        ("🇫🇷", "Français", "fr"),
        ("🇩🇪", "Deutsch", "de"),
        ("🇯🇵", "日本語", "ja"),
        ("🇰🇷", "한국어", "ko"),
        ("🇦🇪", "العربية", "ar"),
        ("🇰🇭", "ខ្មែរ", "km")
    ]

    keyboard = []
    row = []

    for flag, name, code in languages:
        button_text = f"{flag} {name}"
        row.append({"text": button_text, "callback_data": f"language:{code}"})

        if len(row) == 2:  # 2 языка в ряду
            keyboard.append(row)
            row = []

    if row:  # Добавляем оставшиеся кнопки
        keyboard.append(row)

    # Кнопка "Назад"
    keyboard.append([
        {"text": "🔙 Назад", "callback_data": "settings:main"}
    ])

    return {"inline_keyboard": keyboard}


def create_subscription_keyboard(lang: str, current_plan: str) -> Dict:
    """Создает клавиатуру управления подпиской"""
    keyboard = []

    # Показываем доступные планы
    for plan_code, plan_info in PLANS.items():
        if plan_code == current_plan:
            button_text = f"✅ {plan_info['name']} (текущий)"
            callback_data = f"subscription:current:{plan_code}"
        else:
            price = {
                'basic': '$9.99/мес',
                'pro': '$19.99/мес'
            }.get(plan_code, 'Бесплатно')

            button_text = f"🔄 {plan_info['name']} - {price}"
            callback_data = f"subscription:change:{plan_code}"

        keyboard.append([{"text": button_text, "callback_data": callback_data}])

    # Дополнительные опции
    if current_plan != 'free':
        keyboard.append([
            {"text": "❌ Отменить подписку", "callback_data": "subscription:cancel"}
        ])

    keyboard.append([
        {"text": "💳 История платежей", "callback_data": "subscription:history"}
    ])

    keyboard.append([
        {"text": "🔙 Назад", "callback_data": "main_menu"}
    ])

    return {"inline_keyboard": keyboard}


def create_result_actions_keyboard(transcription_id: str, lang: str) -> Dict:
    """Создает клавиатуру действий с результатом транскрипции"""
    return {
        "inline_keyboard": [
            [
                {"text": "💬 Задать вопрос", "callback_data": f"chat:start:{transcription_id}"},
                {"text": "🔄 Другая обработка", "callback_data": f"processing:new:{transcription_id}"}
            ],
            [
                {"text": "📤 Поделиться", "callback_data": f"share:{transcription_id}"},
                {"text": "🗑️ Удалить", "callback_data": f"delete:{transcription_id}"}
            ],
            [
                {"text": "🏠 Главное меню", "callback_data": "main_menu"}
            ]
        ]
    }


def create_balance_topup_keyboard(lang: str) -> Dict:
    """Создает клавиатуру пополнения баланса"""
    return {
        "inline_keyboard": [
            [
                {"text": "💎 5 часов - $9.99", "callback_data": "payment:topup:5h:999"},
                {"text": "💎 15 часов - $19.99", "callback_data": "payment:topup:15h:1999"}
            ],
            [
                {"text": "💎 50 часов - $49.99", "callback_data": "payment:topup:50h:4999"},
                {"text": "💎 100 часов - $79.99", "callback_data": "payment:topup:100h:7999"}
            ],
            [
                {"text": "🔙 Назад", "callback_data": "balance:main"}
            ]
        ]
    }


def create_payment_methods_keyboard(package: str, amount: str, lang: str) -> Dict:
    """Создает клавиатуру выбора способа оплаты"""
    return {
        "inline_keyboard": [
            [
                {"text": "💳 Банковская карта", "callback_data": f"payment:card:{package}:{amount}"},
                {"text": "🅿️ PayPal", "callback_data": f"payment:paypal:{package}:{amount}"}
            ],
            [
                {"text": "₿ Криптовалюта", "callback_data": f"payment:crypto:{package}:{amount}"},
                {"text": "🏦 Банковский перевод", "callback_data": f"payment:transfer:{package}:{amount}"}
            ],
            [
                {"text": "🔙 Назад к пакетам", "callback_data": "balance:topup"}
            ]
        ]
    }


def create_confirmation_keyboard(action: str, item_id: str, lang: str) -> Dict:
    """Создает клавиатуру подтверждения действия"""
    if action == "delete":
        confirm_text = "🗑️ Да, удалить"
        cancel_text = "❌ Отмена"
    elif action == "cancel_subscription":
        confirm_text = "✅ Да, отменить"
        cancel_text = "❌ Не отменять"
    else:
        confirm_text = "✅ Подтвердить"
        cancel_text = "❌ Отмена"

    return {
        "inline_keyboard": [
            [
                {"text": confirm_text, "callback_data": f"confirm:{action}:{item_id}"},
                {"text": cancel_text, "callback_data": f"cancel:{action}:{item_id}"}
            ]
        ]
    }