# ui/keyboards.py - UI компоненты клавиатур
from typing import Dict
from config import PLANS, PROCESSING_TYPES
from ui.localization import LocalizationService


def create_main_menu_keyboard(localization: LocalizationService, lang: str) -> Dict:
    """Создает главное меню бота."""
    return {
        "inline_keyboard": [
            [
                {"text": localization.get_text("btn_subscription", lang), "callback_data": "subscription:main"},
                {"text": localization.get_text("btn_settings", lang), "callback_data": "settings:main"}
            ],
            [
                {"text": localization.get_text("btn_help", lang), "callback_data": "help:main"},
                {"text": localization.get_text("btn_balance", lang), "callback_data": "balance:main"}
            ]
        ]
    }


def create_settings_keyboard(localization: LocalizationService, lang: str) -> Dict:
    """Создает клавиатуру настроек."""
    return {
        "inline_keyboard": [
            [{"text": localization.get_text("btn_change_lang", lang), "callback_data": "settings:language"}],
            [{"text": localization.get_text("btn_manage_subscription", lang), "callback_data": "subscription:main"}],
            [{"text": localization.get_text("btn_back", lang), "callback_data": "start"}]
        ]
    }


def create_language_selection_keyboard(localization: LocalizationService, lang: str) -> Dict:
    """Создает клавиатуру выбора языка."""
    keyboard = [
        [
            {"text": "🇷🇺 Русский", "callback_data": "settings:set_lang:ru"},
            {"text": "🇺🇸 English", "callback_data": "settings:set_lang:en"}
        ],
        [{"text": localization.get_text("btn_back", lang), "callback_data": "settings:main"}]
    ]
    return {"inline_keyboard": keyboard}


def create_balance_keyboard(localization: LocalizationService, lang: str) -> Dict:
    """Создает клавиатуру управления балансом."""
    return {
        "inline_keyboard": [
            [{"text": localization.get_text("btn_top_up_balance", lang), "callback_data": "balance:topup"}],
            [{"text": localization.get_text("btn_usage_history", lang), "callback_data": "balance:history"}],
            [{"text": localization.get_text("btn_back", lang), "callback_data": "start"}]
        ]
    }


def create_subscription_keyboard(lang: str, current_plan: str) -> Dict:
    """Создает клавиатуру управления подпиской."""
    keyboard = []
    for plan_code, plan_info in PLANS.items():
        if plan_code == current_plan:
            button_text = f"✅ {plan_info['name']} (текущий)"
        else:
            price = {
                'basic': '$9.99/мес',
                'pro': '$19.99/мес'
            }.get(plan_code, 'Бесплатно')
            button_text = f"🔄 {plan_info['name']} - {price}"

        keyboard.append([{"text": button_text, "callback_data": f"subscription:change:{plan_code}"}])

    keyboard.append([{"text": "🔙 Назад", "callback_data": "start"}])
    return {"inline_keyboard": keyboard}


def create_processing_keyboard(transcription_id: str) -> Dict:
    """Создает клавиатуру выбора опций обработки после транскрипции."""
    keyboard = [
        [
            {"text": PROCESSING_TYPES["summary"]["name"], "callback_data": f"process:{transcription_id}:summary"},
            {"text": PROCESSING_TYPES["keypoints"]["name"], "callback_data": f"process:{transcription_id}:keypoints"}
        ],
        [
            {"text": PROCESSING_TYPES["business"]["name"], "callback_data": f"process:{transcription_id}:business"},
            {"text": PROCESSING_TYPES["translate_en"]["name"],
             "callback_data": f"process:{transcription_id}:translate_en"}
        ]
    ]
    return {"inline_keyboard": keyboard}